"""Ratio-based reliability indicators (SLIs).

Implements the mathematics specified in docs/SLO_SEMANTICS.md and
ADR-0002: given counts of ``EvaluationOutcome.PASS`` /
``FAIL`` / ``UNKNOWN`` observations and an explicit ``UnknownPolicy``,
compute the fraction of considered observations that passed.

``PASS`` always means "good" (docs/DOMAIN_MODEL.md) — this module never
reinterprets that meaning based on SLO direction. Direction-sensitive
behavior lives entirely in ``slo.py`` and ``error_budget.py``, which
consume ``RatioResult.fail_ratio`` alongside an ``Slo``'s
``allowed_bad_fraction``.

All ratio arithmetic uses ``fractions.Fraction`` — exact, no ambient
precision context, no binary-rounding surprises at threshold boundaries.
See ADR-0002 for the full rationale.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction
from typing import assert_never

from agent_reliability.domain.evaluation import EvaluationOutcome

__all__ = ["ObservationCounts", "RatioResult", "UnknownPolicy", "compute_ratio"]


class UnknownPolicy(enum.Enum):
    """How ``UNKNOWN`` observations affect a ratio SLI's denominator.

    There is no project-wide default (docs/SLO_SEMANTICS.md) — every
    call site that computes a ``RatioResult`` must choose one
    explicitly, because the choice materially changes the reported
    number (a worked example in SLO_SEMANTICS.md shows a 0.3 percentage
    point swing from the same raw data).

    ``TREAT_AS_GOOD`` is included for completeness but is rarely
    appropriate: it lets missing evidence artificially improve the
    reported SLI. Choosing it should be a deliberate, justified decision
    for a specific low-stakes SLI, never a convenient default.
    """

    EXCLUDE = "exclude"
    TREAT_AS_BAD = "treat_as_bad"
    TREAT_AS_GOOD = "treat_as_good"


@dataclass(frozen=True)
class ObservationCounts:
    """Raw counts of evaluation outcomes, before any ``UnknownPolicy``
    is applied.

    A plain aggregate: construct it directly if you already maintain
    counts (e.g. from a counting query) — there is no requirement to
    materialize individual ``EvaluationOutcome`` values to use it. Use
    ``from_outcomes`` only when you have (or can cheaply stream)
    individual outcomes.
    """

    pass_count: int
    fail_count: int
    unknown_count: int

    def __post_init__(self) -> None:
        for field_name, value in (
            ("pass_count", self.pass_count),
            ("fail_count", self.fail_count),
            ("unknown_count", self.unknown_count),
        ):
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(
                    f"ObservationCounts.{field_name} must be an int, got "
                    f"{type(value).__name__}"
                )
            if value < 0:
                raise ValueError(
                    f"ObservationCounts.{field_name} must be >= 0, got {value}"
                )

    @property
    def total_count(self) -> int:
        return self.pass_count + self.fail_count + self.unknown_count

    @classmethod
    def from_outcomes(cls, outcomes: Iterable[EvaluationOutcome]) -> ObservationCounts:
        """Aggregate an iterable of outcomes in O(1) memory.

        Consumes ``outcomes`` exactly once via a single streaming pass —
        does not materialize a list, so this scales to arbitrarily many
        outcomes without holding them all in memory at once.
        """
        pass_count = fail_count = unknown_count = 0
        for outcome in outcomes:
            match outcome:
                case EvaluationOutcome.PASS:
                    pass_count += 1
                case EvaluationOutcome.FAIL:
                    fail_count += 1
                case EvaluationOutcome.UNKNOWN:
                    unknown_count += 1
                case _:  # pragma: no cover - exhaustiveness guard
                    assert_never(outcome)
        return cls(
            pass_count=pass_count, fail_count=fail_count, unknown_count=unknown_count
        )


@dataclass(frozen=True)
class RatioResult:
    """The result of applying an ``UnknownPolicy`` to ``ObservationCounts``.

    Stores only the raw counts and the chosen policy; every derived
    quantity (``considered_pass_count``, ``considered_fail_count``,
    ``considered_count``, ``pass_ratio``, ``fail_ratio``) is a computed
    property, not redundant stored state — there is exactly one source
    of truth per value.

    ``pass_ratio`` and ``fail_ratio`` are ``None`` if and only if
    ``considered_count == 0`` (no eligible data) — never ``0.0`` or
    ``1.0``, which would falsely claim total unreliability or total
    reliability from an empty sample (docs/SLO_SEMANTICS.md).
    """

    pass_count: int
    fail_count: int
    unknown_count: int
    unknown_policy: UnknownPolicy

    def __post_init__(self) -> None:
        for field_name, value in (
            ("pass_count", self.pass_count),
            ("fail_count", self.fail_count),
            ("unknown_count", self.unknown_count),
        ):
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(
                    f"RatioResult.{field_name} must be an int, got "
                    f"{type(value).__name__}"
                )
            if value < 0:
                raise ValueError(f"RatioResult.{field_name} must be >= 0, got {value}")
        if not isinstance(self.unknown_policy, UnknownPolicy):
            raise TypeError(
                "RatioResult.unknown_policy must be an UnknownPolicy, got "
                f"{type(self.unknown_policy).__name__}"
            )

    @property
    def considered_pass_count(self) -> int:
        """Observations counted as good in the denominator, per policy."""
        match self.unknown_policy:
            case UnknownPolicy.EXCLUDE | UnknownPolicy.TREAT_AS_BAD:
                return self.pass_count
            case UnknownPolicy.TREAT_AS_GOOD:
                return self.pass_count + self.unknown_count
            case _:  # pragma: no cover - exhaustiveness guard
                assert_never(self.unknown_policy)

    @property
    def considered_fail_count(self) -> int:
        """Observations counted as bad in the denominator, per policy."""
        match self.unknown_policy:
            case UnknownPolicy.EXCLUDE | UnknownPolicy.TREAT_AS_GOOD:
                return self.fail_count
            case UnknownPolicy.TREAT_AS_BAD:
                return self.fail_count + self.unknown_count
            case _:  # pragma: no cover - exhaustiveness guard
                assert_never(self.unknown_policy)

    @property
    def considered_count(self) -> int:
        """The ratio's denominator: how many observations counted at all."""
        return self.considered_pass_count + self.considered_fail_count

    @property
    def pass_ratio(self) -> Fraction | None:
        """Fraction of considered observations that are good.

        ``None`` iff ``considered_count == 0`` — see ADR-0002.
        """
        denominator = self.considered_count
        if denominator == 0:
            return None
        return Fraction(self.considered_pass_count, denominator)

    @property
    def fail_ratio(self) -> Fraction | None:
        """Fraction of considered observations that are bad.

        Computed directly from ``considered_fail_count`` (not as
        ``1 - pass_ratio``) so that ``pass_ratio`` and ``fail_ratio``
        can never disagree due to independent rounding — though with
        exact ``Fraction`` arithmetic they are always exactly
        complementary in any case. ``None`` iff ``considered_count == 0``.
        """
        denominator = self.considered_count
        if denominator == 0:
            return None
        return Fraction(self.considered_fail_count, denominator)


def compute_ratio(
    outcomes: Iterable[EvaluationOutcome], *, unknown_policy: UnknownPolicy
) -> RatioResult:
    """Convenience: aggregate outcomes and apply ``unknown_policy`` in one call.

    Streams ``outcomes`` in O(1) memory (see ``ObservationCounts.from_outcomes``).
    If you already hold aggregate counts, construct ``RatioResult`` directly
    instead of materializing individual outcomes just to call this function.
    """
    counts = ObservationCounts.from_outcomes(outcomes)
    return RatioResult(
        pass_count=counts.pass_count,
        fail_count=counts.fail_count,
        unknown_count=counts.unknown_count,
        unknown_policy=unknown_policy,
    )

"""SLO definitions and evaluation.

Implements the direction-unified comparison specified in
docs/SLO_SEMANTICS.md and ADR-0002: an SLO is evaluated by comparing the
*observed bad fraction* (``RatioResult.fail_ratio``) against the SLO's
*allowed bad fraction* (``Slo.allowed_bad_fraction``, derived from
``target`` and ``direction``). This one comparison covers both
``AT_LEAST`` and ``AT_MOST`` objectives — see ``Slo.allowed_bad_fraction``
for the derivation and why this does not change ``AT_LEAST`` behavior.

Observation windows are intentionally not modeled here — see
docs/SLO_SEMANTICS.md and docs/ARCHITECTURE.md's deferred decisions.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from fractions import Fraction
from typing import assert_never

from agent_reliability.domain.sli import RatioResult

__all__ = ["ObjectiveDirection", "Slo", "SloEvaluation", "SloStatus", "evaluate_slo"]


class ObjectiveDirection(enum.Enum):
    """Which direction is "good" for an SLO's target.

    ``AT_LEAST``: the ratio SLI (a "good" fraction, e.g. task success)
    must be at or above ``target`` — e.g. ``task_success >= 0.995``.

    ``AT_MOST``: the *bad* fraction (e.g. a hallucination rate) must be
    at or below ``target`` — e.g. ``hallucination_rate <= 0.001``. This
    does not require a differently-defined SLI; the underlying evaluator
    still reports ``PASS`` for "no hallucination" and ``FAIL`` for
    "hallucination detected," so ``RatioResult.fail_ratio`` is directly
    the hallucination rate. See ``Slo.allowed_bad_fraction``.
    """

    AT_LEAST = "at_least"
    AT_MOST = "at_most"


@dataclass(frozen=True)
class Slo:
    """An immutable SLO definition: a named target and its direction.

    ``target`` must be a ``fractions.Fraction`` in ``[0, 1]`` — never a
    bare ``float`` literal. Construct it as ``Fraction(995, 1000)`` or
    ``Fraction("0.995")``, not ``Fraction(0.995)``: the latter first
    rounds ``0.995`` to its nearest binary ``float`` representation and
    then captures *that* value exactly, silently reintroducing the
    rounding error this kernel exists to avoid at threshold boundaries.
    A runtime check below rejects non-``Fraction`` input rather than
    relying on type hints alone, because this is the single highest-risk
    construction site for that mistake (see ADR-0002).

    Observation windows are not modeled here; see module docstring.
    """

    name: str
    target: Fraction
    direction: ObjectiveDirection

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Slo.name must not be empty")
        if not isinstance(self.target, Fraction):
            raise TypeError(
                "Slo.target must be a fractions.Fraction, got "
                f"{type(self.target).__name__}. Construct it as "
                "Fraction(995, 1000) or Fraction('0.995') — never from a "
                "bare float literal such as Fraction(0.995), which "
                "silently captures binary floating-point rounding error "
                "instead of the exact decimal value (see ADR-0002)."
            )
        if not (Fraction(0) <= self.target <= Fraction(1)):
            raise ValueError(f"Slo.target must be within [0, 1], got {self.target}")
        if not isinstance(self.direction, ObjectiveDirection):
            raise TypeError(
                "Slo.direction must be an ObjectiveDirection, got "
                f"{type(self.direction).__name__}"
            )

    @property
    def allowed_bad_fraction(self) -> Fraction:
        """The fraction of considered observations permitted to be bad.

        ``AT_LEAST``: ``1 - target`` (e.g. a 99.5% success target
        permits a 0.5% bad fraction).

        ``AT_MOST``: ``target`` itself (the target already names the
        maximum tolerable bad fraction directly, e.g. a 0.1%
        hallucination-rate target permits exactly that fraction).

        Always well-defined (including ``0`` for a 100% ``AT_LEAST`` or
        0% ``AT_MOST`` target) — the *division* by this value elsewhere
        (error budget, burn rate) is what requires zero-tolerance
        handling, not this property itself.
        """
        match self.direction:
            case ObjectiveDirection.AT_LEAST:
                return Fraction(1) - self.target
            case ObjectiveDirection.AT_MOST:
                return self.target
            case _:  # pragma: no cover - exhaustiveness guard
                assert_never(self.direction)


class SloStatus(enum.Enum):
    """The result of comparing an observed ratio against an ``Slo``.

    Never a ``bool``: undefined SLI data (no eligible observations)
    cannot be truthfully represented as met or breached, so it is its
    own outcome, ``UNKNOWN`` — consistent with ``EvaluationOutcome``
    never collapsing missing evidence into ``PASS``/``FAIL``.
    """

    MET = "met"
    BREACHED = "breached"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SloEvaluation:
    """The typed result of evaluating an ``Slo`` against a ``RatioResult``."""

    slo: Slo
    ratio: RatioResult
    status: SloStatus


def evaluate_slo(slo: Slo, ratio: RatioResult) -> SloEvaluation:
    """Evaluate ``ratio`` against ``slo``.

    ``status`` is ``UNKNOWN`` if ``ratio`` has no considered observations
    (``ratio.fail_ratio is None``). Otherwise, ``MET`` iff
    ``ratio.fail_ratio <= slo.allowed_bad_fraction`` — the boundary is
    inclusive in both directions (an exact-target ratio counts as
    ``MET``), which this single comparison satisfies for both
    ``AT_LEAST`` and ``AT_MOST`` (see ``Slo.allowed_bad_fraction`` and
    ADR-0002 for why one formula covers both).
    """
    observed_bad_fraction = ratio.fail_ratio
    if observed_bad_fraction is None:
        status = SloStatus.UNKNOWN
    elif observed_bad_fraction <= slo.allowed_bad_fraction:
        status = SloStatus.MET
    else:
        status = SloStatus.BREACHED
    return SloEvaluation(slo=slo, ratio=ratio, status=status)

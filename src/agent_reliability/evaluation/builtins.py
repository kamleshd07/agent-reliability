"""Minimal deterministic/local evaluators proving the M4 protocols.

The additional evaluators below (``ContainsEvaluator``, ``RegexMatchEvaluator``,
``LatencyThresholdEvaluator``, ``ToolCalledEvaluator``, ``ToolNotCalledEvaluator``)
were added additively for developer-adoption ergonomics. Every one of them:

- is a frozen, immutable, hashable value object with structural equality;
- declares its ``identity``/``deterministic`` exactly like the M4 evaluators
  above, so it plugs into ``EvaluatorRunner`` and the provenance/cohort
  machinery unchanged;
- raises ``TypeError``/``ValueError`` for programmer misuse (invalid
  configuration, wrong input type) instead of silently returning ``UNKNOWN``
  — misuse is a bug, not an indeterminate measurement;
- operates only on the explicit value passed to ``evaluate()``. None of them
  read files, environment variables, network state, or wall-clock time, and
  none of them retain the value they were called with after returning.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation.identity import EvaluatorIdentity
from agent_reliability.evaluation.result import EvaluationDecision

__all__ = [
    "ContainsEvaluator",
    "EqualityEvaluator",
    "LatencyThresholdEvaluator",
    "PredicateEvaluator",
    "RegexMatchEvaluator",
    "ToolCalledEvaluator",
    "ToolNotCalledEvaluator",
]

InputT = TypeVar("InputT")


@dataclass(frozen=True, slots=True)
class EqualityEvaluator(Generic[InputT]):
    """Evaluate equality without retaining the actual input."""

    identity: EvaluatorIdentity
    expected: InputT

    @property
    def deterministic(self) -> bool:
        """Expected reproducibility assumes the input's equality is stable."""
        return True

    def evaluate(self, value: InputT) -> EvaluationDecision:
        comparison = value == self.expected
        if not isinstance(comparison, bool):
            raise TypeError("equality comparison must return bool")
        if comparison:
            return EvaluationDecision(EvaluationOutcome.PASS, "equal")
        return EvaluationDecision(EvaluationOutcome.FAIL, "not_equal")


@dataclass(frozen=True, slots=True)
class PredicateEvaluator(Generic[InputT]):
    """Adapt a trusted typed predicate into an evaluator.

    The predicate returns ``True``/``False``/``None`` for
    ``PASS``/``FAIL``/``UNKNOWN``. It is trusted application code and is not
    serialized, registered, inspected, or sandboxed by the framework.
    """

    identity: EvaluatorIdentity
    predicate: Callable[[InputT], bool | None]
    deterministic: bool

    def __post_init__(self) -> None:
        if not callable(self.predicate):
            raise TypeError("predicate must be callable")
        if not isinstance(self.deterministic, bool):
            raise TypeError("deterministic must be a bool")

    def evaluate(self, value: InputT) -> EvaluationDecision:
        judgment = self.predicate(value)
        if judgment is True:
            return EvaluationDecision(EvaluationOutcome.PASS, "predicate_passed")
        if judgment is False:
            return EvaluationDecision(EvaluationOutcome.FAIL, "predicate_failed")
        if judgment is None:
            return EvaluationDecision(
                EvaluationOutcome.UNKNOWN, "insufficient_evidence"
            )
        raise TypeError("predicate must return bool or None")


@dataclass(frozen=True, slots=True)
class ContainsEvaluator:
    """PASS iff ``substring`` occurs within the supplied ``str`` value.

    ``case_sensitive`` defaults to ``True``; when ``False``, both the value
    and ``substring`` are compared using ``str.casefold()`` (correct for
    Unicode, e.g. German ``"ß"``/``"ss"`` and Turkish dotless ``"i"``
    families are handled the way Python's own case-insensitive comparisons
    are). An empty ``substring`` always passes, matching Python's own
    ``"" in value`` semantics — this is not special-cased.

    The value is not stored beyond the call: only ``identity``, ``substring``,
    and ``case_sensitive`` are retained as evaluator configuration.
    """

    identity: EvaluatorIdentity
    substring: str
    case_sensitive: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.substring, str):
            raise TypeError("substring must be a str")
        if not isinstance(self.case_sensitive, bool):
            raise TypeError("case_sensitive must be a bool")

    @property
    def deterministic(self) -> bool:
        return True

    def evaluate(self, value: str) -> EvaluationDecision:
        if not isinstance(value, str):
            raise TypeError("value must be a str")
        haystack, needle = value, self.substring
        if not self.case_sensitive:
            haystack, needle = haystack.casefold(), needle.casefold()
        if needle in haystack:
            return EvaluationDecision(EvaluationOutcome.PASS, "substring_found")
        return EvaluationDecision(EvaluationOutcome.FAIL, "substring_not_found")


@dataclass(frozen=True, slots=True)
class RegexMatchEvaluator:
    """PASS iff a stdlib ``re`` pattern matches the supplied ``str`` value.

    ``fullmatch=False`` (the default) uses ``re.Pattern.search`` — the
    pattern may match anywhere in the value. ``fullmatch=True`` uses
    ``re.Pattern.fullmatch`` — the entire value must match. ``flags`` accepts
    ordinary ``re.RegexFlag`` values (e.g. ``re.IGNORECASE``); it defaults to
    no flags.

    The pattern is compiled once, at construction time: a malformed pattern
    raises ``re.error`` immediately when the evaluator is built, never at
    evaluation time and never as ``UNKNOWN`` — a bad pattern is a
    configuration bug, not an indeterminate measurement. Only the pattern
    string, compiled pattern, mode, and flags are retained; the values passed
    to ``evaluate()`` are never stored.
    """

    identity: EvaluatorIdentity
    pattern: str
    fullmatch: bool = False
    flags: re.RegexFlag = field(default_factory=lambda: re.RegexFlag(0))
    _compiled: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.pattern, str):
            raise TypeError("pattern must be a str")
        if not isinstance(self.fullmatch, bool):
            raise TypeError("fullmatch must be a bool")
        if not isinstance(self.flags, re.RegexFlag):
            raise TypeError("flags must be a re.RegexFlag")
        try:
            compiled = re.compile(self.pattern, self.flags)
        except re.error as exc:
            raise ValueError(f"invalid regex pattern {self.pattern!r}: {exc}") from exc
        object.__setattr__(self, "_compiled", compiled)

    @property
    def deterministic(self) -> bool:
        return True

    def evaluate(self, value: str) -> EvaluationDecision:
        if not isinstance(value, str):
            raise TypeError("value must be a str")
        matcher = self._compiled.fullmatch if self.fullmatch else self._compiled.search
        if matcher(value) is not None:
            return EvaluationDecision(EvaluationOutcome.PASS, "pattern_matched")
        return EvaluationDecision(EvaluationOutcome.FAIL, "pattern_not_matched")


@dataclass(frozen=True, slots=True)
class LatencyThresholdEvaluator:
    """PASS iff an explicit, developer-supplied duration is within threshold.

    This evaluator never infers a duration from trace spans, wall-clock
    reads, or any other ambient source: ``evaluate()`` operates only on the
    ``duration_seconds`` value the caller passes in. Units are always
    seconds; convert before calling if your measurement uses another unit.

    ``threshold_seconds`` must be a non-negative, finite number; a negative
    threshold is rejected at construction as a configuration error.
    ``inclusive`` (default ``True``) controls whether a duration exactly
    equal to the threshold passes.

    A ``None`` value means "no measurement was captured for this run" — this
    is a legitimate, evaluator-completed-but-indeterminate case, so it
    produces ``UNKNOWN`` (reason ``"measurement_unavailable"``), never
    ``FAIL``. This reuses the existing ``EvaluationOutcome.UNKNOWN``
    semantics rather than inventing a new channel; if you also want to track
    *why* a measurement went missing at the run level, use the SDK's
    existing ``MeasurementHealth`` mechanism (``RunHandle.measurement_health``
    / ``record_evaluation_failure``) alongside this evaluator, not instead of
    it.
    """

    identity: EvaluatorIdentity
    threshold_seconds: float
    inclusive: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.threshold_seconds, bool) or not isinstance(
            self.threshold_seconds, int | float
        ):
            raise TypeError("threshold_seconds must be an int or float")
        if not _is_finite(self.threshold_seconds):
            raise ValueError("threshold_seconds must be a finite number")
        if self.threshold_seconds < 0:
            raise ValueError("threshold_seconds must be >= 0")
        if not isinstance(self.inclusive, bool):
            raise TypeError("inclusive must be a bool")

    @property
    def deterministic(self) -> bool:
        return True

    def evaluate(self, duration_seconds: float | None) -> EvaluationDecision:
        if duration_seconds is None:
            return EvaluationDecision(
                EvaluationOutcome.UNKNOWN, "measurement_unavailable"
            )
        if isinstance(duration_seconds, bool) or not isinstance(
            duration_seconds, int | float
        ):
            raise TypeError("duration_seconds must be an int, float, or None")
        if not _is_finite(duration_seconds):
            raise ValueError("duration_seconds must be a finite number")
        if duration_seconds < 0:
            raise ValueError("duration_seconds must be >= 0")
        within = (
            duration_seconds <= self.threshold_seconds
            if self.inclusive
            else duration_seconds < self.threshold_seconds
        )
        if within:
            return EvaluationDecision(EvaluationOutcome.PASS, "within_threshold")
        return EvaluationDecision(EvaluationOutcome.FAIL, "exceeded_threshold")


def _is_finite(value: float) -> bool:
    return math.isfinite(value)


@dataclass(frozen=True, slots=True)
class ToolCalledEvaluator:
    """PASS iff ``tool_name`` is present in a developer-supplied set of tools.

    Privacy boundary: ``evaluate()`` accepts only a bounded
    ``frozenset[str]`` of tool-name identifiers that the caller has already
    decided to disclose — for example ``frozenset({"refund", "lookup"})``.
    It never accepts, inspects, or stores tool call arguments, tool results,
    raw framework tool/call objects, or anything beyond the name strings
    supplied. Only ``identity`` and ``tool_name`` are retained as evaluator
    state; the set passed to ``evaluate()`` is read and discarded.
    """

    identity: EvaluatorIdentity
    tool_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, str) or not self.tool_name:
            raise ValueError("tool_name must be a non-empty str")

    @property
    def deterministic(self) -> bool:
        return True

    def evaluate(self, called_tools: frozenset[str]) -> EvaluationDecision:
        _validate_tool_names(called_tools)
        if self.tool_name in called_tools:
            return EvaluationDecision(EvaluationOutcome.PASS, "tool_called")
        return EvaluationDecision(EvaluationOutcome.FAIL, "tool_not_called")


@dataclass(frozen=True, slots=True)
class ToolNotCalledEvaluator:
    """PASS iff ``tool_name`` is absent from a developer-supplied set of tools.

    Same privacy boundary as ``ToolCalledEvaluator``: ``evaluate()`` accepts
    only a bounded ``frozenset[str]`` of tool-name identifiers, never
    arguments, results, or framework-specific tool objects.
    """

    identity: EvaluatorIdentity
    tool_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, str) or not self.tool_name:
            raise ValueError("tool_name must be a non-empty str")

    @property
    def deterministic(self) -> bool:
        return True

    def evaluate(self, called_tools: frozenset[str]) -> EvaluationDecision:
        _validate_tool_names(called_tools)
        if self.tool_name not in called_tools:
            return EvaluationDecision(EvaluationOutcome.PASS, "tool_not_called")
        return EvaluationDecision(EvaluationOutcome.FAIL, "tool_called")


def _validate_tool_names(called_tools: frozenset[str]) -> None:
    if not isinstance(called_tools, frozenset):
        raise TypeError("called_tools must be a frozenset[str] of tool names")
    if any(not isinstance(item, str) for item in called_tools):
        raise TypeError("called_tools must contain only str tool names")

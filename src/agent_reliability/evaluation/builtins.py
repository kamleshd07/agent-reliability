"""Minimal deterministic/local evaluators proving the M4 protocols."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation.identity import EvaluatorIdentity
from agent_reliability.evaluation.result import EvaluationDecision

__all__ = ["EqualityEvaluator", "PredicateEvaluator"]

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

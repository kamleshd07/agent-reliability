"""Immutable evaluation decisions, results, provenance, and failures."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import UTC, datetime

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation._validation import (
    validate_exception_type,
    validate_reason_code,
)
from agent_reliability.evaluation.identity import EvaluatorIdentity

__all__ = [
    "EvaluationDecision",
    "EvaluationExecutionFailure",
    "EvaluationFailureStage",
    "EvaluationProvenance",
    "EvaluationResult",
]


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    if value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class EvaluationDecision:
    """An evaluator's immediate categorical judgment, before attribution."""

    outcome: EvaluationOutcome
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, EvaluationOutcome):
            raise TypeError("outcome must be an EvaluationOutcome")
        validate_reason_code(self.reason_code)


@dataclass(frozen=True, slots=True)
class EvaluationProvenance:
    """Attribution for one successfully completed evaluation."""

    identity: EvaluatorIdentity
    evaluated_at: datetime
    deterministic: bool

    def __post_init__(self) -> None:
        if not isinstance(self.identity, EvaluatorIdentity):
            raise TypeError("identity must be an EvaluatorIdentity")
        if not isinstance(self.deterministic, bool):
            raise TypeError("deterministic must be a bool")
        object.__setattr__(
            self, "evaluated_at", _utc(self.evaluated_at, "evaluated_at")
        )


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """A completed outcome with immutable, mandatory provenance."""

    outcome: EvaluationOutcome
    provenance: EvaluationProvenance
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, EvaluationOutcome):
            raise TypeError("outcome must be an EvaluationOutcome")
        if not isinstance(self.provenance, EvaluationProvenance):
            raise TypeError("provenance must be EvaluationProvenance")
        validate_reason_code(self.reason_code)


class EvaluationFailureStage(enum.StrEnum):
    """Stage at which safe evaluator execution failed.

    ``EVALUATION`` means the evaluator raised. ``TIMESTAMP`` means provenance
    could not be completed because the runner's clock failed.
    """

    EVALUATION = "evaluation"
    TIMESTAMP = "timestamp"


@dataclass(frozen=True, slots=True)
class EvaluationExecutionFailure:
    """A safe-runner failure; categorically not an evaluation result.

    The raw exception is intentionally absent. It is delivered only through
    the existing ephemeral diagnostic channel.
    """

    identity: EvaluatorIdentity | None
    stage: EvaluationFailureStage
    exception_type: str

    def __post_init__(self) -> None:
        if self.identity is not None and not isinstance(
            self.identity, EvaluatorIdentity
        ):
            raise TypeError("identity must be EvaluatorIdentity or None")
        if not isinstance(self.stage, EvaluationFailureStage):
            raise TypeError("stage must be an EvaluationFailureStage")
        validate_exception_type(self.exception_type)

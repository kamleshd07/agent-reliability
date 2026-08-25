"""Immutable, behavior-oriented evaluator identity."""

from __future__ import annotations

from dataclasses import dataclass

from agent_reliability.evaluation._validation import (
    validate_evaluator_name,
    validate_opaque_id,
    validate_optional_opaque_id,
)

__all__ = ["EvaluatorIdentity"]


@dataclass(frozen=True, slots=True)
class EvaluatorIdentity:
    """Stable identity of evaluation behavior and configuration.

    ``version`` is opaque and is never parsed or ordered. The caller changes
    ``version`` or ``configuration_id`` whenever evaluation semantics change.
    ``configuration_id`` is a non-sensitive label, never raw configuration.
    """

    name: str
    version: str
    configuration_id: str | None = None

    def __post_init__(self) -> None:
        validate_evaluator_name(self.name)
        validate_opaque_id(self.version, "evaluator version")
        validate_optional_opaque_id(self.configuration_id, "evaluator configuration_id")

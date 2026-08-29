"""Immutable measurement/evidence health values."""

from __future__ import annotations

import enum
from dataclasses import dataclass

__all__ = [
    "MeasurementHealth",
    "MeasurementHealthReason",
    "MeasurementHealthReport",
]


class MeasurementHealth(enum.StrEnum):
    """Trustworthiness and completeness of reliability evidence."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class MeasurementHealthReason(enum.StrEnum):
    """Bounded, privacy-safe structural causes of unhealthy evidence."""

    RUN_INITIALIZATION_FAILURE = "run_initialization_failure"
    EVALUATOR_EXECUTION_FAILURE = "evaluator_execution_failure"
    EVALUATION_TIMESTAMP_FAILURE = "evaluation_timestamp_failure"
    EVIDENCE_TIMESTAMP_FAILURE = "evidence_timestamp_failure"
    EVENT_DELIVERY_FAILURE = "event_delivery_failure"
    PARTIAL_EVIDENCE = "partial_evidence"
    PROVENANCE_UNAVAILABLE = "provenance_unavailable"
    INCOMPATIBLE_EVIDENCE = "incompatible_evidence"


_UNAVAILABLE_REASONS = frozenset(
    {
        MeasurementHealthReason.RUN_INITIALIZATION_FAILURE,
        MeasurementHealthReason.EVALUATOR_EXECUTION_FAILURE,
        MeasurementHealthReason.EVALUATION_TIMESTAMP_FAILURE,
        MeasurementHealthReason.PROVENANCE_UNAVAILABLE,
        MeasurementHealthReason.INCOMPATIBLE_EVIDENCE,
    }
)


@dataclass(frozen=True, slots=True)
class MeasurementHealthReport:
    """One scoped health assessment with no payload or exception content.

    Reports compose by set union. The resulting health can only stay the same
    or worsen, making composition deterministic, associative, commutative, and
    idempotent.
    """

    health: MeasurementHealth = MeasurementHealth.HEALTHY
    reasons: frozenset[MeasurementHealthReason] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.health, MeasurementHealth):
            raise TypeError("health must be a MeasurementHealth")
        if not isinstance(self.reasons, frozenset):
            raise TypeError("reasons must be a frozenset")
        if any(
            not isinstance(reason, MeasurementHealthReason) for reason in self.reasons
        ):
            raise TypeError("every reason must be a MeasurementHealthReason")
        if self.health is not self._health_for(self.reasons):
            raise ValueError("health must match the supplied reasons")

    @classmethod
    def from_reasons(
        cls, reasons: frozenset[MeasurementHealthReason]
    ) -> MeasurementHealthReport:
        """Construct the canonical report for bounded structural reasons."""
        if not isinstance(reasons, frozenset):
            raise TypeError("reasons must be a frozenset")
        if any(not isinstance(reason, MeasurementHealthReason) for reason in reasons):
            raise TypeError("every reason must be a MeasurementHealthReason")
        return cls(health=cls._health_for(reasons), reasons=reasons)

    def combine(self, *others: MeasurementHealthReport) -> MeasurementHealthReport:
        """Return the monotonic composition of this report and ``others``."""
        reasons = set(self.reasons)
        for other in others:
            if not isinstance(other, MeasurementHealthReport):
                raise TypeError("others must contain MeasurementHealthReport values")
            reasons.update(other.reasons)
        return self.from_reasons(frozenset(reasons))

    @staticmethod
    def _health_for(
        reasons: frozenset[MeasurementHealthReason],
    ) -> MeasurementHealth:
        if reasons & _UNAVAILABLE_REASONS:
            return MeasurementHealth.UNAVAILABLE
        if reasons:
            return MeasurementHealth.DEGRADED
        return MeasurementHealth.HEALTHY

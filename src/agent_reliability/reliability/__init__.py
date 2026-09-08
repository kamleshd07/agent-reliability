"""Local, exact, provenance-safe reliability aggregation."""

from __future__ import annotations

from agent_reliability.reliability.engine import (
    AggregationConflictError,
    evaluate_reliability,
    evaluate_reliability_or_raise,
)
from agent_reliability.reliability.model import (
    AggregationConflict,
    AggregationConflictReason,
    ReliabilityCohort,
    ReliabilityObservation,
    ReliabilityReport,
)

__all__ = [
    "AggregationConflict",
    "AggregationConflictError",
    "AggregationConflictReason",
    "ReliabilityCohort",
    "ReliabilityObservation",
    "ReliabilityReport",
    "evaluate_reliability",
    "evaluate_reliability_or_raise",
]

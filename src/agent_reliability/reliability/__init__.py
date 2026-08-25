"""Local, exact, provenance-safe reliability aggregation."""

from __future__ import annotations

from agent_reliability.reliability.engine import evaluate_reliability
from agent_reliability.reliability.model import (
    AggregationConflict,
    AggregationConflictReason,
    ReliabilityCohort,
    ReliabilityObservation,
    ReliabilityReport,
)

__all__ = [
    "AggregationConflict",
    "AggregationConflictReason",
    "ReliabilityCohort",
    "ReliabilityObservation",
    "ReliabilityReport",
    "evaluate_reliability",
]

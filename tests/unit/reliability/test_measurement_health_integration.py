from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from fractions import Fraction

from agent_reliability.domain import (
    EvaluationOutcome,
    ObjectiveDirection,
    Slo,
    UnknownPolicy,
)
from agent_reliability.evaluation import EvaluationProvenance, EvaluatorIdentity
from agent_reliability.measurement import (
    MeasurementHealth,
    MeasurementHealthReason,
    MeasurementHealthReport,
)
from agent_reliability.reliability import (
    AggregationConflict,
    ReliabilityObservation,
    evaluate_reliability,
)


def _evaluate(observations: list[ReliabilityObservation]):
    return evaluate_reliability(
        indicator="task_success",
        observations=observations,
        slo=Slo("task-success", Fraction(9, 10), ObjectiveDirection.AT_LEAST),
        unknown_policy=UnknownPolicy.EXCLUDE,
    )


def _observation(version: str = "1") -> ReliabilityObservation:
    return ReliabilityObservation(
        indicator="task_success",
        outcome=EvaluationOutcome.PASS,
        provenance=EvaluationProvenance(
            EvaluatorIdentity("judge", version),
            datetime(2026, 1, 1, tzinfo=UTC),
            True,
        ),
    )


def test_report_exposes_health_without_changing_reliability_math() -> None:
    report = _evaluate([_observation()])
    assert not isinstance(report, AggregationConflict)
    degraded = replace(
        report,
        measurement_health=MeasurementHealthReport.from_reasons(
            frozenset({MeasurementHealthReason.PARTIAL_EVIDENCE})
        ),
    )
    assert degraded.ratio == report.ratio
    assert degraded.slo_evaluation == report.slo_evaluation
    assert degraded.measurement_health.health is MeasurementHealth.DEGRADED
    try:
        replace(report, measurement_health=object())
    except TypeError as error:
        assert "measurement_health" in str(error)
    else:
        raise AssertionError("invalid measurement health was accepted")


def test_provenance_conflict_remains_authoritative_and_health_is_unavailable() -> None:
    conflict = _evaluate([_observation("1"), _observation("2")])
    assert isinstance(conflict, AggregationConflict)
    assert conflict.measurement_health.health is MeasurementHealth.UNAVAILABLE
    assert conflict.measurement_health.reasons == frozenset(
        {MeasurementHealthReason.INCOMPATIBLE_EVIDENCE}
    )

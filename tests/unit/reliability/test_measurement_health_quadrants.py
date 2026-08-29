from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

from agent_reliability.domain import (
    EvaluationOutcome,
    ObjectiveDirection,
    Slo,
    SloStatus,
    UnknownPolicy,
)
from agent_reliability.measurement import (
    MeasurementHealth,
    MeasurementHealthReason,
    MeasurementHealthReport,
)
from agent_reliability.reliability import (
    AggregationConflict,
    ReliabilityObservation,
    ReliabilityReport,
    evaluate_reliability,
)

SLO = Slo("task-success", Fraction(9, 10), ObjectiveDirection.AT_LEAST)


def _report(outcomes: list[EvaluationOutcome]) -> ReliabilityReport:
    result = evaluate_reliability(
        indicator="task_success",
        observations=[
            ReliabilityObservation.manual(indicator="task_success", outcome=outcome)
            for outcome in outcomes
        ],
        slo=SLO,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    assert not isinstance(result, AggregationConflict)
    return result


def test_reliability_and_measurement_health_form_independent_quadrants() -> None:
    high_healthy = _report([EvaluationOutcome.PASS] * 10)
    high_degraded = replace(
        high_healthy,
        measurement_health=MeasurementHealthReport.from_reasons(
            frozenset({MeasurementHealthReason.PARTIAL_EVIDENCE})
        ),
    )
    low_healthy = _report([EvaluationOutcome.PASS] * 8 + [EvaluationOutcome.FAIL] * 2)
    no_evidence_unavailable = replace(
        _report([]),
        measurement_health=MeasurementHealthReport.from_reasons(
            frozenset({MeasurementHealthReason.PROVENANCE_UNAVAILABLE})
        ),
    )

    assert high_healthy.slo_evaluation.status is SloStatus.MET
    assert high_healthy.measurement_health.health is MeasurementHealth.HEALTHY
    assert high_degraded.ratio == high_healthy.ratio
    assert high_degraded.slo_evaluation == high_healthy.slo_evaluation
    assert high_degraded.measurement_health.health is MeasurementHealth.DEGRADED
    assert low_healthy.slo_evaluation.status is SloStatus.BREACHED
    assert low_healthy.measurement_health.health is MeasurementHealth.HEALTHY
    assert no_evidence_unavailable.ratio.pass_ratio is None
    assert no_evidence_unavailable.slo_evaluation.status is SloStatus.UNKNOWN
    assert (
        no_evidence_unavailable.measurement_health.health
        is MeasurementHealth.UNAVAILABLE
    )

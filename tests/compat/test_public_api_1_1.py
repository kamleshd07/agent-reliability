"""Regression snapshot for the public measurement-health API released in 1.1.0."""

from __future__ import annotations

import inspect

import agent_reliability.measurement as measurement
from agent_reliability.measurement import (
    MeasurementHealth,
    MeasurementHealthReason,
    MeasurementHealthReport,
    MeasurementPolicy,
)
from agent_reliability.reliability import AggregationConflict, ReliabilityReport
from agent_reliability.sdk import RunHandle


def test_exact_measurement_namespace_exports_for_1_1() -> None:
    assert measurement.__all__ == [
        "MeasurementHealth",
        "MeasurementHealthReason",
        "MeasurementHealthReport",
        "MeasurementPolicy",
    ]


def test_exact_measurement_enum_names_and_values_for_1_1() -> None:
    assert {item.name: item.value for item in MeasurementHealth} == {
        "HEALTHY": "healthy",
        "DEGRADED": "degraded",
        "UNAVAILABLE": "unavailable",
    }
    assert {item.name: item.value for item in MeasurementHealthReason} == {
        "RUN_INITIALIZATION_FAILURE": "run_initialization_failure",
        "EVALUATOR_EXECUTION_FAILURE": "evaluator_execution_failure",
        "EVALUATION_TIMESTAMP_FAILURE": "evaluation_timestamp_failure",
        "EVIDENCE_TIMESTAMP_FAILURE": "evidence_timestamp_failure",
        "EVENT_DELIVERY_FAILURE": "event_delivery_failure",
        "PARTIAL_EVIDENCE": "partial_evidence",
        "PROVENANCE_UNAVAILABLE": "provenance_unavailable",
        "INCOMPATIBLE_EVIDENCE": "incompatible_evidence",
    }


def test_exact_measurement_signatures_for_1_1() -> None:
    assert str(inspect.signature(MeasurementHealthReport)) == (
        "(health: 'MeasurementHealth' = <MeasurementHealth.HEALTHY: 'healthy'>, "
        "reasons: 'frozenset[MeasurementHealthReason]' = frozenset()) -> None"
    )
    assert str(inspect.signature(MeasurementHealthReport.from_reasons)) == (
        "(reasons: 'frozenset[MeasurementHealthReason]') -> 'MeasurementHealthReport'"
    )
    assert str(inspect.signature(MeasurementHealthReport.combine)) == (
        "(self, *others: 'MeasurementHealthReport') -> 'MeasurementHealthReport'"
    )
    assert str(inspect.signature(MeasurementPolicy.evaluate)) == (
        "(self, *, measurement_health: 'MeasurementHealthReport') -> 'PolicyResultT_co'"
    )
    assert str(inspect.signature(RunHandle.record_evaluation_failure)) == (
        "(self, *, failure: 'EvaluationExecutionFailure') -> 'None'"
    )
    assert str(inspect.signature(RunHandle.evaluate_measurement_policy)) == (
        "(self, policy: 'MeasurementPolicy[PolicyResultT]') -> 'PolicyResultT'"
    )
    assert str(inspect.signature(ReliabilityReport)) == (
        "(indicator: 'str', cohort: 'ReliabilityCohort | None', ratio: "
        "'RatioResult', slo_evaluation: 'SloEvaluation', error_budget: "
        "'ErrorBudget', burn_rate: 'BurnRate | None' = None, measurement_health: "
        "'MeasurementHealthReport' = <factory>) -> None"
    )
    assert isinstance(RunHandle.measurement_health, property)
    assert isinstance(AggregationConflict.measurement_health, property)

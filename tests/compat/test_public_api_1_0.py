"""Selective regression locks for the public 1.0 surface."""

from __future__ import annotations

import inspect
from importlib.metadata import version

import agent_reliability
import agent_reliability.adapters as adapters
import agent_reliability.adapters.otel as otel
import agent_reliability.domain as domain
import agent_reliability.evaluation as evaluation
import agent_reliability.ports as ports
import agent_reliability.reliability as reliability
import agent_reliability.sdk as sdk

EXPECTED_EXPORTS = {
    "agent_reliability": {"__version__"},
    "domain": {
        "AgentIdentity",
        "AgentRun",
        "BudgetStatus",
        "BurnRate",
        "ErrorBudget",
        "EvaluationOutcome",
        "ObjectiveDirection",
        "ObservationCounts",
        "RatioResult",
        "RunStatus",
        "Slo",
        "SloEvaluation",
        "SloStatus",
        "UnknownPolicy",
        "compute_burn_rate",
        "compute_error_budget",
        "compute_ratio",
        "evaluate_slo",
    },
    "sdk": {
        "AgentReliability",
        "DiagnosticHandler",
        "EvaluatorRunner",
        "LoggingDiagnosticHandler",
        "RunHandle",
        "SdkDiagnostic",
        "current_run",
    },
    "evaluation": {
        "AsyncEvaluator",
        "EqualityEvaluator",
        "EvaluationDecision",
        "EvaluationExecutionFailure",
        "EvaluationFailureStage",
        "EvaluationProvenance",
        "EvaluationResult",
        "EvaluatorIdentity",
        "PredicateEvaluator",
        "SyncEvaluator",
    },
    "reliability": {
        "AggregationConflict",
        "AggregationConflictReason",
        "ReliabilityCohort",
        "ReliabilityObservation",
        "ReliabilityReport",
        "evaluate_reliability",
    },
    "ports": {
        "Clock",
        "EvaluationRecorded",
        "EventSink",
        "InstrumentationEvent",
        "RunCompleted",
        "RunContextBridge",
        "RunContextScope",
        "RunFailed",
        "RunIdGenerator",
        "RunStarted",
    },
    "adapters": {
        "CompositeEventSink",
        "InMemoryEventSink",
        "NoOpEventSink",
        "SystemClock",
        "UuidRunIdGenerator",
    },
    "adapters.otel": {"OpenTelemetryRunContextBridge"},
}


def test_exact_public_exports_for_1_0() -> None:
    modules = {
        "agent_reliability": agent_reliability,
        "domain": domain,
        "sdk": sdk,
        "evaluation": evaluation,
        "reliability": reliability,
        "ports": ports,
        "adapters": adapters,
        "adapters.otel": otel,
    }
    assert {name: set(module.__all__) for name, module in modules.items()} == (
        EXPECTED_EXPORTS
    )


def test_stable_enum_names_and_values() -> None:
    enums = {
        domain.EvaluationOutcome: {
            "PASS": "pass",
            "FAIL": "fail",
            "UNKNOWN": "unknown",
        },
        domain.UnknownPolicy: {
            "EXCLUDE": "exclude",
            "TREAT_AS_BAD": "treat_as_bad",
            "TREAT_AS_GOOD": "treat_as_good",
        },
        domain.RunStatus: {
            "STARTED": "started",
            "COMPLETED": "completed",
            "FAILED": "failed",
            "CANCELLED": "cancelled",
        },
        domain.ObjectiveDirection: {"AT_LEAST": "at_least", "AT_MOST": "at_most"},
        domain.SloStatus: {
            "MET": "met",
            "BREACHED": "breached",
            "UNKNOWN": "unknown",
        },
        domain.BudgetStatus: {
            "MEASURED": "measured",
            "NO_DATA": "no_data",
            "ZERO_TOLERANCE_INTACT": "zero_tolerance_intact",
            "ZERO_TOLERANCE_EXCEEDED": "zero_tolerance_exceeded",
        },
        evaluation.EvaluationFailureStage: {
            "EVALUATION": "evaluation",
            "TIMESTAMP": "timestamp",
        },
        reliability.AggregationConflictReason: {
            "INDICATOR_MISMATCH": "indicator_mismatch",
            "MANUAL_EVALUATED_MIX": "manual_evaluated_mix",
            "EVALUATOR_NAME_MISMATCH": "evaluator_name_mismatch",
            "EVALUATOR_VERSION_MISMATCH": "evaluator_version_mismatch",
            "CONFIGURATION_ID_MISMATCH": "configuration_id_mismatch",
            "DETERMINISM_MISMATCH": "determinism_mismatch",
            "WINDOW_COHORT_MISMATCH": "window_cohort_mismatch",
        },
    }
    for enum_type, expected in enums.items():
        assert {item.name: item.value for item in enum_type} == expected


def test_high_value_callable_signatures() -> None:
    assert str(inspect.signature(sdk.AgentReliability)) == (
        "(*, sink: 'EventSink | None' = None, clock: 'Clock | None' = None, "
        "run_id_generator: 'RunIdGenerator | None' = None, "
        "diagnostic_handler: 'DiagnosticHandler | None' = None, "
        "run_context_bridge: 'RunContextBridge | None' = None) -> 'None'"
    )
    assert str(inspect.signature(domain.compute_ratio)) == (
        "(outcomes: 'Iterable[EvaluationOutcome]', *, unknown_policy: "
        "'UnknownPolicy') -> 'RatioResult'"
    )
    assert str(inspect.signature(reliability.evaluate_reliability)) == (
        "(*, indicator: 'str', observations: 'Iterable[ReliabilityObservation]', "
        "slo: 'Slo', unknown_policy: 'UnknownPolicy', burn_rate_lookback: "
        "'Iterable[ReliabilityObservation] | None' = None) -> "
        "'ReliabilityReport | AggregationConflict'"
    )


def test_distribution_and_runtime_version_have_one_value() -> None:
    assert version("agent-reliability") == agent_reliability.__version__

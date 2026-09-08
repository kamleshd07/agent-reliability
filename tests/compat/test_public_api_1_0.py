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

# Exact-locked: these five 1.0 namespaces were not touched by the DX-1
# (Developer Adoption) milestone. An unreviewed export addition here is very
# likely an accident (e.g. an internal helper leaking through `__all__`), so
# equality (`==`), not a subset check, is the right regression lock — see
# ``test_exact_lock_for_unchanged_1_0_namespaces`` below.
UNCHANGED_SINCE_1_0_EXPORTS = {
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

# Baseline-subset only: these two namespaces legitimately *grew* during the
# DX-1 (Developer Adoption) milestone (new built-in evaluators; the
# evaluate_reliability_or_raise/AggregationConflictError convenience API).
# A subset check (`<=`) here would silently stop protecting against a
# *removed* or *renamed* 1.0 export in every namespace if applied globally —
# which is exactly the regression this file fixes — so it is scoped to only
# these two grown namespaces, and their current, exact, non-1.0 export set is
# separately exact-locked (not left uncovered) by
# ``tests/unit/test_package.py::test_m4_evaluation_public_api_is_explicit``
# and ``test_m5_reliability_public_api_is_explicit``, which assert the full
# current ``__all__`` list with ``==``.
GROWN_SINCE_1_0_BASELINE_EXPORTS = {
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
}


def test_exact_lock_for_unchanged_1_0_namespaces() -> None:
    """Exact-lock (``==``) the five 1.0 namespaces DX-1 did not touch.

    Unlike ``evaluation``/``reliability`` (see
    ``test_1_0_baseline_is_a_subset_of_grown_namespaces`` below), nothing in
    this milestone added, removed, or renamed exports here. Exact equality
    means any *accidental* future export addition to one of these namespaces
    — not just a removal/rename — fails CI immediately, rather than silently
    passing under a permissive subset check.
    """
    modules = {
        "agent_reliability": agent_reliability,
        "domain": domain,
        "sdk": sdk,
        "ports": ports,
        "adapters": adapters,
        "adapters.otel": otel,
    }
    for name, expected in UNCHANGED_SINCE_1_0_EXPORTS.items():
        actual = set(modules[name].__all__)
        assert actual == expected, (
            f"unchanged-since-1.0 namespace {name} drifted: "
            f"added={actual - expected} removed={expected - actual}"
        )


def test_1_0_baseline_is_a_subset_of_grown_namespaces() -> None:
    """Every export present at 1.0 remains present and importable in the two
    namespaces DX-1 legitimately grew.

    This is a floor, not a ceiling, for exactly these two namespaces: SemVer
    minor releases (VERSIONING.md) may add new names to their ``__all__``
    without breaking this lock, so the comparison is "1.0 baseline is a
    subset of the current namespace," not exact equality. A *removed* or
    *renamed* 1.0 export still fails this test immediately. The current,
    exact export set (baseline plus DX-1 additions) is separately
    exact-locked in ``tests/unit/test_package.py`` — see that file's
    ``test_m4_evaluation_public_api_is_explicit`` and
    ``test_m5_reliability_public_api_is_explicit`` — so nothing here is left
    uncovered by an exact check.
    """
    modules = {
        "evaluation": evaluation,
        "reliability": reliability,
    }
    for name, expected in GROWN_SINCE_1_0_BASELINE_EXPORTS.items():
        current = set(modules[name].__all__)
        assert expected <= current, (
            f"1.0 export(s) missing from {name}: {expected - current}"
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

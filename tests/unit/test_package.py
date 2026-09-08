"""Smoke tests for versioning and deliberate public package surfaces."""

from __future__ import annotations

from importlib.metadata import version

import agent_reliability
import agent_reliability.evaluation
import agent_reliability.reliability


def test_runtime_version_matches_distribution_metadata() -> None:
    assert agent_reliability.__version__ == version("agent-reliability")


def test_public_api_is_minimal() -> None:
    # M0 intentionally exports nothing but __version__. Growing this
    # list is a deliberate, reviewed decision, not an accident.
    assert agent_reliability.__all__ == ["__version__"]


def test_m4_evaluation_public_api_is_explicit() -> None:
    # M8 (developer adoption) deliberately added ContainsEvaluator,
    # EvaluationOutcome (re-export), LatencyThresholdEvaluator,
    # RegexMatchEvaluator, ToolCalledEvaluator, and ToolNotCalledEvaluator.
    assert agent_reliability.evaluation.__all__ == [
        "AsyncEvaluator",
        "ContainsEvaluator",
        "EqualityEvaluator",
        "EvaluationDecision",
        "EvaluationExecutionFailure",
        "EvaluationFailureStage",
        "EvaluationOutcome",
        "EvaluationProvenance",
        "EvaluationResult",
        "EvaluatorIdentity",
        "LatencyThresholdEvaluator",
        "PredicateEvaluator",
        "RegexMatchEvaluator",
        "SyncEvaluator",
        "ToolCalledEvaluator",
        "ToolNotCalledEvaluator",
    ]


def test_m5_reliability_public_api_is_explicit() -> None:
    # M8 (developer adoption) deliberately added evaluate_reliability_or_raise
    # and AggregationConflictError as an additive convenience API.
    assert agent_reliability.reliability.__all__ == [
        "AggregationConflict",
        "AggregationConflictError",
        "AggregationConflictReason",
        "ReliabilityCohort",
        "ReliabilityObservation",
        "ReliabilityReport",
        "evaluate_reliability",
        "evaluate_reliability_or_raise",
    ]

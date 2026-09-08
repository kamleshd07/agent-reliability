"""M4 evaluator contracts and immutable provenance values.

This stable public namespace is provider-, framework-, runtime-, and
platform-neutral. Evaluators do not require an active SDK run. See
docs/GA_CONTRACT.md.
"""

from __future__ import annotations

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation.builtins import (
    ContainsEvaluator,
    EqualityEvaluator,
    LatencyThresholdEvaluator,
    PredicateEvaluator,
    RegexMatchEvaluator,
    ToolCalledEvaluator,
    ToolNotCalledEvaluator,
)
from agent_reliability.evaluation.identity import EvaluatorIdentity
from agent_reliability.evaluation.protocols import AsyncEvaluator, SyncEvaluator
from agent_reliability.evaluation.result import (
    EvaluationDecision,
    EvaluationExecutionFailure,
    EvaluationFailureStage,
    EvaluationProvenance,
    EvaluationResult,
)

__all__ = [
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

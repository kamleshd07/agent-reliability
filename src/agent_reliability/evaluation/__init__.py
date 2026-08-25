"""M4 evaluator contracts and immutable provenance values.

This stable public namespace is provider-, framework-, runtime-, and
platform-neutral. Evaluators do not require an active SDK run. See
docs/GA_CONTRACT.md.
"""

from __future__ import annotations

from agent_reliability.evaluation.builtins import (
    EqualityEvaluator,
    PredicateEvaluator,
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
    "EqualityEvaluator",
    "EvaluationDecision",
    "EvaluationExecutionFailure",
    "EvaluationFailureStage",
    "EvaluationProvenance",
    "EvaluationResult",
    "EvaluatorIdentity",
    "PredicateEvaluator",
    "SyncEvaluator",
]

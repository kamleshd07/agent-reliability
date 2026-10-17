"""EXPERIMENTAL: model-backed LLM-judge evaluators (P29 V1).

This namespace is explicitly Experimental (docs/VERSIONING.md, ADR-0010,
P29-D01): names, signatures, defaults, prompt template and vocabularies may
change in a minor release with release notes. It is stdlib-only, performs no
network I/O of its own, ships no provider, and reads no credentials or
environment. Raw evaluated content goes only to the customer's own provider
object and is never retained, logged, serialized or exported.
"""

from __future__ import annotations

from agent_reliability.experimental.judge.budget import BudgetTracker
from agent_reliability.experimental.judge.calibration import (
    CalibrationCase,
    CalibrationReport,
    FlippedCase,
    ReportComparison,
    compare_reports,
    load_cases,
    run_calibration,
    run_calibration_async,
)
from agent_reliability.experimental.judge.coordinator import (
    CoverageReport,
    EvaluationDisposition,
    EvaluationScope,
    IndicatorBinding,
    IndicatorCoverage,
    JudgeCoordinator,
    JudgeInvocationReport,
    JudgeObserver,
)
from agent_reliability.experimental.judge.errors import (
    FAILURE_CLASS_NAMES,
    JudgeBudgetExceededError,
    JudgeError,
    JudgeInputLimitError,
    JudgeInvalidOutputError,
    JudgeOutputTooLargeError,
    JudgeOverloadedError,
    JudgeProviderError,
    JudgeProviderRateLimitedError,
    JudgeProviderRefusedError,
    JudgeProviderUnavailableError,
    JudgeTimeoutError,
)
from agent_reliability.experimental.judge.executor import ExecutorSyncProvider
from agent_reliability.experimental.judge.identity import (
    TEMPLATE_ID,
    compose_configuration_id,
    compose_identity,
    validate_identity_value,
    validate_model_label,
)
from agent_reliability.experimental.judge.judge import LLMJudge
from agent_reliability.experimental.judge.provider import (
    CallableProvider,
    CallableSyncProvider,
    JudgeProvider,
    ProviderCall,
    ProviderFinish,
    ProviderReply,
    SyncJudgeProvider,
)
from agent_reliability.experimental.judge.reference import (
    REFERENCE_RUBRIC_IDS,
    load_reference_rubric,
)
from agent_reliability.experimental.judge.rubric import Criterion, ReasonCodes, Rubric
from agent_reliability.experimental.judge.structured import StructuredOutputEvaluator
from agent_reliability.experimental.judge.sync import SyncLLMJudge
from agent_reliability.experimental.judge.values import (
    Confidence,
    ContentPart,
    ContentRole,
    ContentTrust,
    EvaluationRequest,
    JudgeBudget,
    JudgeDimension,
    JudgeEvaluation,
    JudgeLimits,
    JudgePolicy,
    JudgeStats,
    SamplingPolicy,
)

__all__ = [
    "FAILURE_CLASS_NAMES",
    "REFERENCE_RUBRIC_IDS",
    "TEMPLATE_ID",
    "BudgetTracker",
    "CalibrationCase",
    "CalibrationReport",
    "CallableProvider",
    "CallableSyncProvider",
    "Confidence",
    "ContentPart",
    "ContentRole",
    "ContentTrust",
    "CoverageReport",
    "Criterion",
    "EvaluationDisposition",
    "EvaluationRequest",
    "EvaluationScope",
    "ExecutorSyncProvider",
    "FlippedCase",
    "IndicatorBinding",
    "IndicatorCoverage",
    "JudgeBudget",
    "JudgeBudgetExceededError",
    "JudgeCoordinator",
    "JudgeDimension",
    "JudgeError",
    "JudgeEvaluation",
    "JudgeInputLimitError",
    "JudgeInvalidOutputError",
    "JudgeInvocationReport",
    "JudgeLimits",
    "JudgeObserver",
    "JudgeOutputTooLargeError",
    "JudgeOverloadedError",
    "JudgePolicy",
    "JudgeProvider",
    "JudgeProviderError",
    "JudgeProviderRateLimitedError",
    "JudgeProviderRefusedError",
    "JudgeProviderUnavailableError",
    "JudgeStats",
    "JudgeTimeoutError",
    "LLMJudge",
    "ProviderCall",
    "ProviderFinish",
    "ProviderReply",
    "ReasonCodes",
    "ReportComparison",
    "Rubric",
    "SamplingPolicy",
    "StructuredOutputEvaluator",
    "SyncJudgeProvider",
    "SyncLLMJudge",
    "compare_reports",
    "compose_configuration_id",
    "compose_identity",
    "load_cases",
    "load_reference_rubric",
    "run_calibration",
    "run_calibration_async",
    "validate_identity_value",
    "validate_model_label",
]

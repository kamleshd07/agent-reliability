"""Snapshot of the EXPERIMENTAL ``agent_reliability.experimental.judge`` API (P29).

This namespace is Experimental (docs/VERSIONING.md, ADR-0010): it may change in
a minor release with release notes. This file makes any change visible. It is
a new snapshot; none of the existing ``test_public_api_1_*`` snapshots is
edited by P29 (checked below against the recorded workspace baseline).
"""

from __future__ import annotations

import enum
import hashlib
import inspect
import pathlib
import re
import tomllib
from typing import Any

import pytest

import agent_reliability.experimental as experimental
import agent_reliability.experimental.judge as judge
from tests.fakes.p29_baseline import load_baseline, load_runtime_revisions

pytestmark = pytest.mark.contract

ROOT = pathlib.Path(__file__).resolve().parents[2]

EXPECTED_ALL = [
    "UNGATED",
    "AdmissionVerdict",
    "EvidenceAdmission",
    "JudgeBehaviour",
    "template_digest",
    "wilson_interval",
    "BudgetTracker",
    "CallableProvider",
    "CallableSyncProvider",
    "Confidence",
    "ContentPart",
    "ContentRole",
    "ContentTrust",
    "Criterion",
    "run_calibration_async",
    "run_calibration",
    "load_cases",
    "compare_reports",
    "ReportComparison",
    "FlippedCase",
    "CalibrationReport",
    "CalibrationCase",
    "StructuredOutputEvaluator",
    "ExecutorSyncProvider",
    "load_reference_rubric",
    "REFERENCE_RUBRIC_IDS",
    "JudgeObserver",
    "JudgeInvocationReport",
    "JudgeCoordinator",
    "IndicatorCoverage",
    "IndicatorBinding",
    "EvaluationScope",
    "EvaluationDisposition",
    "CoverageReport",
    "EvaluationRequest",
    "FAILURE_CLASS_NAMES",
    "JudgeBudget",
    "JudgeBudgetExceededError",
    "JudgeDimension",
    "JudgeError",
    "JudgeEvaluation",
    "JudgeInputLimitError",
    "JudgeInvalidOutputError",
    "JudgeLimits",
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
    "Rubric",
    "SamplingPolicy",
    "SyncJudgeProvider",
    "SyncLLMJudge",
    "TEMPLATE_ID",
    "compose_configuration_id",
    "compose_identity",
    "validate_identity_value",
    "validate_model_label",
]


def test_exported_names_snapshot() -> None:
    assert sorted(judge.__all__) == sorted(EXPECTED_ALL)
    assert len(set(judge.__all__)) == len(judge.__all__)
    for name in judge.__all__:
        assert hasattr(judge, name)


def test_testing_helpers_are_not_exported_from_the_namespace_root() -> None:
    for name in ("FakeProvider", "FakeSyncProvider", "HANG", "judge_reply"):
        assert name not in judge.__all__
        assert not hasattr(judge, name)


def test_experimental_package_itself_still_exports_nothing() -> None:
    assert not hasattr(experimental, "__all__") or experimental.__all__ == []
    assert "judge" not in vars(experimental).get("__all__", [])


def test_enum_values_snapshot() -> None:
    def values(e: type[enum.Enum]) -> list[str]:
        return [m.value for m in e]

    assert values(judge.JudgeDimension) == [
        "answer-correctness",
        "groundedness",
        "instruction-adherence",
        "safety-policy",
        "task-completion-evidence",
    ]
    assert values(judge.ContentRole) == [
        "question",
        "answer",
        "reference",
        "context",
        "instructions",
        "policy",
        "task_evidence",
    ]
    assert values(judge.ContentTrust) == ["trusted", "untrusted"]
    assert values(judge.Confidence) == ["low", "medium", "high"]
    assert values(judge.ProviderFinish) == ["stop", "length", "filtered", "other"]
    assert judge.TEMPLATE_ID == "jp1"


def test_failure_taxonomy_snapshot() -> None:
    assert judge.FAILURE_CLASS_NAMES == (
        "JudgeTimeoutError",
        "JudgeProviderUnavailableError",
        "JudgeProviderRateLimitedError",
        "JudgeProviderRefusedError",
        "JudgeProviderError",
        "JudgeInvalidOutputError",
        "JudgeOutputTooLargeError",
        "JudgeInputLimitError",
        "JudgeBudgetExceededError",
        "JudgeOverloadedError",
    )
    for name in judge.FAILURE_CLASS_NAMES:
        cls = getattr(judge, name)
        assert issubclass(cls, judge.JudgeError)
        assert cls.__mro__[1] is judge.JudgeError
    assert issubclass(judge.JudgeError, Exception)
    assert not issubclass(judge.JudgeError, (TimeoutError, ValueError))


def test_signature_snapshot() -> None:
    assert str(inspect.signature(judge.LLMJudge.__init__)) == (
        "(self, *, rubric: 'Rubric', provider: 'JudgeProvider', model_label: 'str', "
        "policy: 'JudgePolicy | None' = None, limits: 'JudgeLimits | None' = None, "
        "budget: 'JudgeBudget | BudgetTracker | None' = None, "
        "retain_cause: 'bool' = False, "
        "nonce_source: 'Callable[[], str] | None' = None, "
        "jitter: 'Callable[[], float] | None' = None) -> 'None'"
    )
    sync_params = list(inspect.signature(judge.SyncLLMJudge.__init__).parameters)
    assert sync_params == [
        "self",
        "rubric",
        "provider",
        "model_label",
        "policy",
        "limits",
        "budget",
        "retain_cause",
        "nonce_source",
        "jitter",
        "monotonic",
        "sleep",
    ]
    assert inspect.iscoroutinefunction(judge.LLMJudge.evaluate)
    assert not inspect.iscoroutinefunction(judge.SyncLLMJudge.evaluate)
    assert str(inspect.signature(judge.compose_configuration_id)) == (
        "(*, model_label: 'str', min_confidence: 'Confidence', repeats: 'int', "
        "require_citations: 'bool', template_id: 'str' = 'jp1') -> 'str'"
    )


def _fields(cls: type) -> dict[str, Any]:
    import dataclasses

    return {
        f.name: f.default if f.default is not dataclasses.MISSING else "<required>"
        for f in dataclasses.fields(cls)
    }


def test_value_type_fields_and_defaults_snapshot() -> None:
    assert _fields(judge.JudgeLimits) == {
        "provider_timeout_seconds": 30.0,
        "evaluation_deadline_seconds": 60.0,
        "max_attempts": 2,
        "repair_attempts": 1,
        "max_input_chars": 32_000,
        "max_output_tokens": 256,
        "max_reply_chars": 4_096,
        "retry_backoff_cap_seconds": 2.0,
    }
    assert _fields(judge.JudgePolicy) == {
        "min_confidence": None,
        "repeats": 1,
        "capture_reason": False,
    }
    assert _fields(judge.JudgeBudget) == {
        "window_seconds": 3_600,
        "max_tokens_per_window": None,
        "max_cost_per_window": None,
        "input_price_per_1k_tokens": None,
        "output_price_per_1k_tokens": None,
    }
    assert _fields(judge.SamplingPolicy) == {"rate": 1.0, "salt": ""}
    assert _fields(judge.ContentPart) == {
        "role": "<required>",
        "text": "<required>",
        "trust": None,
    }
    assert _fields(judge.EvaluationRequest) == {
        "dimension": "<required>",
        "parts": "<required>",
        "correlation_id": None,
    }
    assert list(_fields(judge.ProviderCall)) == [
        "system",
        "user",
        "max_output_tokens",
        "temperature",
        "json_output",
        "deadline_seconds",
    ]
    assert _fields(judge.ProviderReply) == {
        "text": "<required>",
        "input_tokens": None,
        "output_tokens": None,
        "finish": judge.ProviderFinish.STOP,
    }


def test_identity_composition_snapshot() -> None:
    assert (
        judge.compose_configuration_id(
            model_label="local-llama3-8b-q4",
            min_confidence=judge.Confidence.MEDIUM,
            repeats=1,
            require_citations=False,
        )
        == "local-llama3-8b-q4.jp1.mc-medium.rp1.ct0"
    )


def test_core_dependencies_remain_empty_and_no_entry_points() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["dependencies"] == []
    assert "entry-points" not in project["project"]
    assert "scripts" not in project["project"]
    assert "judge" not in project["project"]["optional-dependencies"]


def _baseline() -> dict[str, str]:
    return load_baseline()


def test_existing_compat_snapshots_are_unchanged_by_p29() -> None:
    baseline = _baseline()
    for name in (
        "tests/compat/test_public_api_1_0.py",
        "tests/compat/test_public_api_1_1.py",
        "tests/compat/test_public_api_1_2.py",
        "tests/compat/test_semantic_1_0.py",
    ):
        digest = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        assert digest == baseline[name], name


def _normalized(name: str, data: bytes) -> bytes:
    """A release changes only the ``__version__`` literal of the package root.

    The baseline digest was recorded at version 1.2.1; the literal is normalised
    back to that value before hashing so a version bump is not mistaken for a
    source change, while every other byte of the file stays pinned.
    """
    if name == "src/agent_reliability/__init__.py":
        data = re.sub(rb'__version__ = "[^"]+"', b'__version__ = "1.2.1"', data)
    return data


def test_no_existing_source_module_is_modified_by_p29() -> None:
    """P29 adds files under experimental/judge/ only (plan section 4)."""
    baseline = _baseline()
    changed = []
    revisions = load_runtime_revisions()
    for name, digest in baseline.items():
        if not name.startswith("src/"):
            continue
        if name in revisions:
            # Recorded revision (fixtures/documentation/runtime-revisions.json):
            # baseline == its previous hash; the file == its pinned new hash.
            assert revisions[name]["previousSha256"] == digest, name
            digest = revisions[name]["sha256"]
        current = ROOT / name
        if (
            not current.exists()
            or hashlib.sha256(_normalized(name, current.read_bytes())).hexdigest()
            != digest
        ):
            changed.append(name)
    assert changed == []


def test_coordinator_admission_hook_shapes_snapshot() -> None:
    """Session 4 (P29 calibration) additions to the coordinator, all additive."""
    assert list(_fields(judge.IndicatorBinding)) == [
        "indicator",
        "evaluator",
        "sampling",
        "admission",
    ]
    assert [m.value for m in judge.EvaluationDisposition] == [
        "recorded_result",
        "recorded_failure",
        "skipped_unsampled",
        "skipped_run_not_recording",
        "skipped_by_admission",
    ]
    assert list(_fields(judge.IndicatorCoverage)) == [
        "indicator",
        "attempted",
        "passed",
        "failed",
        "unknown",
        "execution_failures",
        "failures_by_class",
        "unsampled",
        "skipped_run_not_recording",
        "cancelled",
        "late_discarded",
        "provider_calls",
        "admission_skipped",
        "ungated_model_backed",
        "explicitly_ungated",
    ]
    assert repr(judge.UNGATED) == "UNGATED"
    assert list(_fields(judge.AdmissionVerdict)) == ["allowed", "reason_code"]
    assert list(_fields(judge.JudgeBehaviour)) == [
        "limits",
        "limits_digest",
        "repeats",
        "min_confidence",
        "capture_reason",
        "require_citations",
        "template_id",
        "template_digest",
        "engine_revision",
    ]


def test_template_digest_is_pinned_to_the_golden_prompt_fixture() -> None:
    """A template edit that forgets to change TEMPLATE_ID changes this digest.

    The digest is computed at runtime from the real prompt builder (fixtures are not
    shipped in the wheel). The value below was recorded with template ``jp1``; the
    golden fixture test (``test_p29_s02_ac01``) pins the builder's bytes, so the two
    move together and a change to either one fails CI.
    """
    assert judge.template_digest() == (
        "9cabfba1017f99dba3cc20186e4e2d00793410437d4eafb9061096c5075f7d83"
    )

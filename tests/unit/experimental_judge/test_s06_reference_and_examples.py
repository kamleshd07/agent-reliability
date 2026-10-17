"""P29-S06: reference rubrics, example providers, runnable example, docs."""

from __future__ import annotations

import ast
import asyncio
import json
import pathlib
import subprocess
import sys
import tomllib
from typing import Any

import pytest
from examples import judge_providers as providers

import agent_reliability.experimental.judge as namespace
from agent_reliability.evaluation import (
    EvaluationExecutionFailure,
    EvaluationResult,
)
from agent_reliability.experimental.judge import (
    REFERENCE_RUBRIC_IDS,
    ContentPart,
    ContentRole,
    EvaluationRequest,
    JudgeDimension,
    JudgePolicy,
    LLMJudge,
    ProviderCall,
    ProviderFinish,
    Rubric,
    SyncLLMJudge,
    load_reference_rubric,
)
from agent_reliability.experimental.judge.testing import FakeProvider
from agent_reliability.sdk.evaluator_runner import EvaluatorRunner
from tests.fakes.p29_judge import load_fixture

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[3]
CASES = load_fixture("reference_rubric_cases.json")["cases"]
DOCS = (ROOT / "docs" / "EVALUATE.md").read_text(encoding="utf-8")
DIMENSIONS = {
    "judge-answer-correctness": "answer-correctness",
    "judge-groundedness": "groundedness",
    "judge-instruction-adherence": "instruction-adherence",
    "judge-safety-policy": "safety-policy",
    "judge-task-completion-evidence": "task-completion-evidence",
}


def test_p29_s06_ac01_five_reference_rubrics_validate_and_declare_contract() -> None:
    assert sorted(REFERENCE_RUBRIC_IDS) == sorted(DIMENSIONS)
    rubric_dir = pathlib.Path(namespace.__file__).parent / "rubrics"
    assert sorted(p.stem for p in rubric_dir.glob("*.json")) == sorted(DIMENSIONS)
    for rid, dimension in DIMENSIONS.items():
        rubric = load_reference_rubric(rid)
        assert rubric.rubric_id == rid and rubric.dimension.value == dimension
        assert ContentRole.ANSWER in rubric.inputs_required  # required inputs declared
        assert len(rubric.inputs_required) >= 2
        assert "low_confidence" in rubric.reason_codes.unknown  # closed codes
        assert "judge_disagreement" in rubric.reason_codes.unknown
        assert rubric.min_confidence.value == "medium"
        assert (
            rubric.fingerprint()
            == Rubric.from_json((rubric_dir / f"{rid}.json").read_text()).fingerprint()
        )
    with pytest.raises(ValueError):
        load_reference_rubric("judge-unknown")
    assert load_reference_rubric("judge-groundedness").require_citations is True


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_p29_s06_ac01_each_reference_rubric_passes_its_fixtures(
    case: dict[str, Any],
) -> None:
    spec = case["input"]
    provider = FakeProvider([spec["reply"]] * 3)
    judge = LLMJudge(
        rubric=load_reference_rubric(spec["rubric"]),
        provider=provider,
        model_label="fixture",
        jitter=lambda: 0.0,
    )
    request = EvaluationRequest(
        JudgeDimension(spec["dimension"]),
        tuple(ContentPart(ContentRole(p["role"]), p["text"]) for p in spec["parts"]),
    )
    outcome = asyncio.run(EvaluatorRunner().evaluate_async(judge, request))
    expected = case["expected"]
    if expected["outcome"] == "failure":
        assert isinstance(outcome, EvaluationExecutionFailure)
        assert outcome.exception_type == expected["reason_code"]
    else:
        assert isinstance(outcome, EvaluationResult)
        assert outcome.outcome.value == expected["outcome"]
        assert outcome.reason_code == expected["reason_code"]
    assert provider.call_count == expected["provider_calls"]


def test_p29_s06_ac02_every_rubric_states_pass_meaning_and_uncalibrated() -> None:
    for rid in REFERENCE_RUBRIC_IDS:
        rubric = load_reference_rubric(rid)
        assert rubric.description is not None
        assert rubric.description.startswith("UNCALIBRATED reference rubric")
        assert "PASS means" in rubric.description
        assert "accuracy claim" in rubric.description
        assert rid in DOCS  # documented per dimension
    task = load_reference_rubric("judge-task-completion-evidence")
    assert task.description is not None and "R1" in task.description
    assert "R1" in DOCS and "never an authoritative outcome" in DOCS
    assert "uncalibrated" in DOCS.lower()
    section = DOCS.split("Meaning of PASS per dimension", 1)[1][:3000]
    for dimension in DIMENSIONS.values():
        assert dimension in section


def test_p29_s06_ac03_fake_provider_example_runs_offline_and_shows_all_outcomes() -> (
    None
):
    completed = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "judge_fake_provider.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stderr == ""
    out = completed.stdout
    assert "recorded groundedness: pass groundedness.supported_by_context" in out
    assert (
        "recorded answer-correctness: fail answer-correctness.contradicts_reference"
        in out
    )
    assert "recorded instruction-adherence: unknown" in out
    assert "safety-policy: recorded_failure" in out  # an execution failure
    assert "run health: unavailable" in out
    assert "reliability n/a over 0 determinate of 1 attempted" in out  # coverage shown


def test_p29_s06_ac04_examples_are_not_imported_by_the_core_namespace() -> None:
    root = pathlib.Path(namespace.__file__).parent
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            if isinstance(node, ast.Import):
                modules.extend(a.name for a in node.names)
            assert not [m for m in modules if m.split(".")[0] in {"examples", "urllib"}]
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = project["project"]["optional-dependencies"]
    assert not [k for k in extras if "judge" in k or "openai" in k or "anthropic" in k]
    assert project["project"]["dependencies"] == []


def test_p29_s06_ac05_local_model_walkthrough_is_documented_and_marked_manual() -> None:
    assert "Local-model walkthrough" in DOCS
    walkthrough = DOCS.split("Local-model walkthrough", 1)[1]
    assert "manual" in walkthrough.lower() and "not a CI criterion" in walkthrough
    assert "Prerequisites" in walkthrough


# ----------------------------------------------------------- example providers


def _call() -> ProviderCall:
    return ProviderCall("SYS", "USR", 128, 0.0, True, 7.5)


def test_p29_s06_openai_compatible_example_shapes_and_error_mapping() -> None:
    seen: dict[str, Any] = {}

    def post(
        url: str, headers: dict[str, str], body: dict[str, Any], timeout: float
    ) -> Any:
        seen.update(url=url, headers=headers, body=body, timeout=timeout)
        return {
            "choices": [{"message": {"content": "{}"}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 3},
        }

    provider = providers.openai_compatible_provider(
        base_url="https://llm.example.invalid/v1/",
        model="m",
        api_key_provider=lambda: "tok",
        post_json=post,
    )
    reply = provider.complete(_call())
    assert seen["url"] == "https://llm.example.invalid/v1/chat/completions"
    assert seen["headers"] == {"Authorization": "Bearer tok"}
    assert seen["timeout"] == 7.5
    assert seen["body"]["messages"][0] == {"role": "system", "content": "SYS"}
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert (reply.input_tokens, reply.output_tokens) == (11, 3)
    assert reply.finish is ProviderFinish.LENGTH
    assert provider.reports_tokens is True  # type: ignore[attr-defined]
    assert "tok" not in repr(provider)


@pytest.mark.parametrize(
    "status,expected",
    [
        (429, "JudgeProviderRateLimitedError"),
        (500, "JudgeProviderUnavailableError"),
        (503, "JudgeProviderUnavailableError"),
        (504, "JudgeTimeoutError"),
        (408, "JudgeTimeoutError"),
        (401, "JudgeProviderError"),
        (400, "JudgeProviderError"),
    ],
)
def test_p29_s06_example_http_status_mapping(status: int, expected: str) -> None:
    def post(*args: Any) -> Any:
        raise providers.HttpStatusError(status, 2.5)

    provider = providers.openai_compatible_provider(
        base_url="https://llm.example.invalid/v1", model="m", post_json=post
    )
    with pytest.raises(Exception) as caught:
        provider.complete(_call())
    assert type(caught.value).__name__ == expected
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    if status == 429:
        assert caught.value.retry_after_seconds == 2.5  # type: ignore[attr-defined]


def test_p29_s06_example_transport_and_malformed_response_mapping() -> None:
    def make(exc: Exception | None, data: Any = None) -> Any:
        def post(*args: Any) -> Any:
            if exc is not None:
                raise exc
            return data

        return providers.openai_compatible_provider(
            base_url="https://llm.example.invalid/v1", model="m", post_json=post
        )

    for exc, name in (
        (TimeoutError("SECRET"), "JudgeTimeoutError"),
        (ConnectionResetError("SECRET"), "JudgeProviderUnavailableError"),
        (ValueError("SECRET"), "JudgeProviderError"),
    ):
        with pytest.raises(Exception) as caught:
            make(exc).complete(_call())
        assert type(caught.value).__name__ == name
        assert "SECRET" not in str(caught.value)
    with pytest.raises(Exception) as bad:
        make(None, {"choices": []}).complete(_call())
    assert type(bad.value).__name__ == "JudgeProviderError"


def test_p29_s06_anthropic_compatible_example_shape() -> None:
    seen: dict[str, Any] = {}

    def post(
        url: str, headers: dict[str, str], body: dict[str, Any], timeout: float
    ) -> Any:
        seen.update(url=url, headers=headers, body=body)
        return {
            "content": [{"type": "text", "text": "{"}, {"type": "text", "text": "}"}],
            "stop_reason": "refusal",
            "usage": {"input_tokens": 5, "output_tokens": 1},
        }

    provider = providers.anthropic_compatible_provider(
        base_url="https://api.example.invalid",
        model="m",
        api_key_provider=lambda: "k",
        post_json=post,
    )
    reply = provider.complete(_call())
    assert seen["url"] == "https://api.example.invalid/v1/messages"
    assert seen["headers"]["x-api-key"] == "k"
    assert seen["body"]["system"] == "SYS"
    assert seen["body"]["messages"] == [{"role": "user", "content": "USR"}]
    assert reply.text == "{}" and reply.finish is ProviderFinish.FILTERED


def test_p29_s06_local_runtime_example_and_url_rules() -> None:
    seen: dict[str, Any] = {}

    def post(
        url: str, headers: dict[str, str], body: dict[str, Any], timeout: float
    ) -> Any:
        seen["url"] = url
        return {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}]}

    provider = providers.local_runtime_provider(
        model="llama", port=8080, post_json=post
    )
    assert provider.complete(_call()).text == "x"
    assert seen["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    for bad in ("http://remote.example.invalid/v1", "ftp://x/v1", "llm/v1"):
        with pytest.raises(ValueError):
            providers.openai_compatible_provider(base_url=bad, model="m")


def test_p29_s06_example_provider_drives_a_judge_end_to_end() -> None:
    from tests.fakes.p29_judge import good_reply

    def post(*args: Any) -> Any:
        return {
            "choices": [
                {"message": {"content": good_reply()}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    provider = providers.openai_compatible_provider(
        base_url="https://llm.example.invalid/v1", model="m", post_json=post
    )
    from tests.fakes.p29_judge import grounded_request, named_rubrics

    sync_judge = SyncLLMJudge(
        rubric=named_rubrics()["gr-cit"], provider=provider, model_label="ex"
    )
    outcome = EvaluatorRunner().evaluate(sync_judge, grounded_request())
    assert isinstance(outcome, EvaluationResult)
    async_judge = LLMJudge(
        rubric=named_rubrics()["gr-cit"],
        provider=providers.as_async(provider),
        model_label="ex",
        policy=JudgePolicy(),
    )
    outcome = asyncio.run(
        EvaluatorRunner().evaluate_async(async_judge, grounded_request())
    )
    assert isinstance(outcome, EvaluationResult)


def test_p29_s06_customer_callable_example() -> None:
    from tests.fakes.p29_judge import good_reply, grounded_request, named_rubrics

    async def client(system: str, user: str, timeout: float) -> tuple[str, int, int]:
        assert "BEGIN" in user and timeout > 0
        return good_reply(), 10, 2

    judge = LLMJudge(
        rubric=named_rubrics()["gr-cit"],
        provider=providers.customer_callable_provider(client),
        model_label="ex",
    )
    result = asyncio.run(judge.evaluate_detailed(grounded_request()))
    assert (result.stats.input_tokens, result.stats.output_tokens) == (10, 2)


def test_p29_s06_fixture_file_is_valid_json() -> None:
    assert json.loads(
        (
            ROOT / "tests" / "fixtures" / "p29" / "reference_rubric_cases.json"
        ).read_text()
    )["cases"]

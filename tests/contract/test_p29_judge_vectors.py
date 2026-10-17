"""P29 data-only fixtures drive the sans-IO core and both drivers (P29-CON-15).

Covers P29-S01-AC01 (via the rubric vectors in the unit module), S02-AC01,
S02-AC02, S02-AC03, S02-AC05, S02-AC06, S03-AC02, S03-AC08 and S04-AC01.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

import pytest

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation import (
    EvaluationExecutionFailure,
    EvaluationFailureStage,
    EvaluationResult,
)
from agent_reliability.experimental.judge import (
    Confidence,
    JudgeInvalidOutputError,
    JudgeLimits,
    JudgePolicy,
    LLMJudge,
    Rubric,
    SyncLLMJudge,
)
from agent_reliability.experimental.judge.core import (
    ParsedOutput,
    aggregate_repeats,
    build_prompt,
    draw_nonce,
    map_verdict,
    parse_output,
    select_parts,
)
from agent_reliability.experimental.judge.testing import (
    FakeProvider,
    FakeSyncProvider,
    fixed_nonces,
)
from agent_reliability.sdk.evaluator_runner import EvaluatorRunner
from tests.fakes.p29_judge import (
    FIXTURE_DIR,
    load_fixture,
    request_from_document,
    steps_from_vector,
)

pytestmark = pytest.mark.contract


def test_p29_fixture_manifest_hashes_match() -> None:
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text())
    on_disk = {p.name for p in FIXTURE_DIR.glob("*.json")} - {"manifest.json"}
    assert set(manifest) == on_disk
    for name, entry in manifest.items():
        data = (FIXTURE_DIR / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], name
        assert json.loads(data)["schema"].startswith("gentlity.fixture.")
        assert entry["fixture_format_version"] == 1


def test_p29_fixtures_have_id_input_expected_note() -> None:
    for name in (
        "rubric_valid.json",
        "rubric_invalid.json",
        "judge_output_vectors.json",
        "mapping_vectors.json",
        "prompt_golden_jp1.json",
        "failure_mapping_vectors.json",
        "privacy_planted.json",
    ):
        cases = load_fixture(name)["cases"]
        ids = [c["id"] for c in cases]
        assert len(ids) == len(set(ids)), name
        if name != "privacy_planted.json":
            for case in cases:
                assert {"id", "input", "expected", "note"} <= set(case), (
                    name,
                    case["id"],
                )


# --------------------------------------------------------------- S02-AC02 / AC03

_OUT = load_fixture("judge_output_vectors.json")
_OUT_RUBRICS = {k: Rubric.from_dict(v) for k, v in _OUT["rubrics"].items()}


@pytest.mark.parametrize("case", _OUT["cases"], ids=[c["id"] for c in _OUT["cases"]])
def test_p29_s02_ac02_ac03_parser_vectors(case: dict[str, Any]) -> None:
    rubric = _OUT_RUBRICS[case["input"]["rubric"]]
    expected = case["expected"]
    if expected["ok"]:
        parsed = parse_output(
            case["input"]["reply"], rubric, case["input"]["context_count"]
        )
        document = expected["document"]
        assert parsed.verdict == document["verdict"]
        assert parsed.code == document["code"]
        assert parsed.confidence.value == document["confidence"]
        assert list(parsed.citations) == document["citations"]
        assert parsed.reason == document["reason"]
    else:
        with pytest.raises(JudgeInvalidOutputError) as caught:
            parse_output(case["input"]["reply"], rubric, case["input"]["context_count"])
        assert type(caught.value).__name__ == expected["failure"]
        assert caught.value.error_class == expected["error_class"]


# ------------------------------------------------------------------- S02-AC05

_MAP = load_fixture("mapping_vectors.json")


@pytest.mark.parametrize("case", _MAP["cases"], ids=[c["id"] for c in _MAP["cases"]])
def test_p29_s02_ac05_mapping_vectors(case: dict[str, Any]) -> None:
    spec = case["input"]
    min_confidence = Confidence(spec["min_confidence"])
    decisions = [
        map_verdict(
            ParsedOutput(
                verdict=r["verdict"],
                code=r["code"],
                confidence=Confidence(r["confidence"]),
                citations=(),
            ),
            spec["dimension"],
            min_confidence,
        )
        for r in spec["results"]
    ]
    final = (
        decisions[0]
        if len(decisions) == 1
        else aggregate_repeats(decisions, spec["dimension"])
    )
    assert final.outcome is EvaluationOutcome(case["expected"]["outcome"])
    assert final.reason_code == case["expected"]["reason_code"]


# ------------------------------------------------------------------- S02-AC01

_GOLD = load_fixture("prompt_golden_jp1.json")
_GOLD_RUBRICS = {k: Rubric.from_dict(v) for k, v in _GOLD["rubrics"].items()}


@pytest.mark.parametrize("case", _GOLD["cases"], ids=[c["id"] for c in _GOLD["cases"]])
def test_p29_s02_ac01_prompt_golden_byte_for_byte(case: dict[str, Any]) -> None:
    spec = case["input"]
    rubric = _GOLD_RUBRICS[spec["rubric"]]
    request = request_from_document(
        {
            "dimension": rubric.dimension.value,
            "parts": spec["parts"],
        }
    )
    selected = select_parts(rubric, request.parts)
    nonce = draw_nonce(selected, fixed_nonces(spec["nonce_sequence"]))
    prompt = build_prompt(
        rubric, selected, nonce=nonce, repair_error_class=spec["repair_error_class"]
    )
    assert nonce == case["expected"]["nonce"]
    assert prompt.system == case["expected"]["system"]
    assert prompt.user == case["expected"]["user"]
    assert _GOLD["template_id"] == "jp1"


# --------------------------------------------- S03-AC02 / S03-AC08 / S04-AC01 parity

_FAIL = load_fixture("failure_mapping_vectors.json")
_FAIL_RUBRICS = {k: Rubric.from_dict(v) for k, v in _FAIL["rubrics"].items()}


def _limits(spec: dict[str, Any]) -> JudgeLimits:
    return JudgeLimits(**spec["limits"])


def _check(
    outcome: EvaluationResult | EvaluationExecutionFailure, expected: dict[str, Any]
) -> None:
    if expected["kind"] == "result":
        assert isinstance(outcome, EvaluationResult)
        assert outcome.outcome is EvaluationOutcome(expected["outcome"])
        assert outcome.reason_code == expected["reason_code"]
        assert outcome.provenance.deterministic is False
    else:
        # I-P29-1: a fault never yields an EvaluationResult.
        assert isinstance(outcome, EvaluationExecutionFailure)
        assert outcome.stage is EvaluationFailureStage.EVALUATION
        assert outcome.exception_type == expected["exception_type"]
        assert outcome.identity is not None  # I-P29-3


def _async_judge(case: dict[str, Any]) -> tuple[LLMJudge, FakeProvider]:
    spec = case["input"]
    provider = FakeProvider(steps_from_vector(spec["script"]))
    judge = LLMJudge(
        rubric=_FAIL_RUBRICS[spec["rubric"]],
        provider=provider,
        model_label="fake-model",
        policy=JudgePolicy(repeats=spec["repeats"]),
        limits=_limits(spec),
        jitter=lambda: 0.0,
    )
    return judge, provider


def _sync_judge(case: dict[str, Any]) -> tuple[SyncLLMJudge, FakeSyncProvider]:
    spec = case["input"]
    provider = FakeSyncProvider(steps_from_vector(spec["script"]))
    judge = SyncLLMJudge(
        rubric=_FAIL_RUBRICS[spec["rubric"]],
        provider=provider,
        model_label="fake-model",
        policy=JudgePolicy(repeats=spec["repeats"]),
        limits=_limits(spec),
        jitter=lambda: 0.0,
        sleep=lambda _seconds: None,
    )
    return judge, provider


@pytest.mark.parametrize("case", _FAIL["cases"], ids=[c["id"] for c in _FAIL["cases"]])
def test_p29_s03_ac02_failure_matrix_through_runner_async(case: dict[str, Any]) -> None:
    judge, provider = _async_judge(case)
    request = request_from_document(_FAIL["requests"][case["input"]["request"]])
    outcome = asyncio.run(EvaluatorRunner().evaluate_async(judge, request))
    _check(outcome, case["expected"])
    assert provider.call_count == case["expected"]["provider_calls"]


@pytest.mark.parametrize("case", _FAIL["cases"], ids=[c["id"] for c in _FAIL["cases"]])
def test_p29_s04_ac01_sync_driver_parity_with_async(case: dict[str, Any]) -> None:
    judge, provider = _sync_judge(case)
    request = request_from_document(_FAIL["requests"][case["input"]["request"]])
    outcome = EvaluatorRunner().evaluate(judge, request)
    _check(outcome, case["expected"])
    assert provider.call_count == case["expected"]["provider_calls"]
    # Same decisions/classes as the async driver for the same script.
    a_judge, _ = _async_judge(case)
    a_outcome = asyncio.run(EvaluatorRunner().evaluate_async(a_judge, request))
    assert type(a_outcome) is type(outcome)
    if isinstance(outcome, EvaluationResult):
        assert isinstance(a_outcome, EvaluationResult)
        assert (a_outcome.outcome, a_outcome.reason_code) == (
            outcome.outcome,
            outcome.reason_code,
        )
    else:
        assert isinstance(a_outcome, EvaluationExecutionFailure)
        assert a_outcome.exception_type == outcome.exception_type


def test_p29_s04_ac01_parity_over_output_and_mapping_vectors() -> None:
    """Every judge-output vector yields the same decision/class in both drivers."""
    rubric = _OUT_RUBRICS["gr-cit"]
    request = request_from_document(_FAIL["requests"]["basic"])
    for case in _OUT["cases"]:
        if case["input"]["rubric"] != "gr-cit" or case["input"]["context_count"] != 2:
            continue
        reply = case["input"]["reply"]
        a = LLMJudge(
            rubric=rubric,
            provider=FakeProvider([reply, reply]),
            model_label="m",
            jitter=lambda: 0.0,
        )
        s = SyncLLMJudge(
            rubric=rubric,
            provider=FakeSyncProvider([reply, reply]),
            model_label="m",
            jitter=lambda: 0.0,
            sleep=lambda _s: None,
        )
        a_out = asyncio.run(EvaluatorRunner().evaluate_async(a, request))
        s_out = EvaluatorRunner().evaluate(s, request)
        assert type(a_out) is type(s_out), case["id"]
        if isinstance(a_out, EvaluationResult):
            assert isinstance(s_out, EvaluationResult)
            assert (a_out.outcome, a_out.reason_code) == (
                s_out.outcome,
                s_out.reason_code,
            )
        else:
            assert isinstance(s_out, EvaluationExecutionFailure)
            assert a_out.exception_type == s_out.exception_type
            assert case["expected"]["ok"] is False

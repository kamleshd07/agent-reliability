"""Hypothesis properties for the experimental judge (P29 S01-S04)."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_reliability.adapters import _http_delivery
from agent_reliability.evaluation import (
    EvaluationExecutionFailure,
    EvaluationResult,
)
from agent_reliability.evaluation._validation import _OPAQUE_ID as SDK_OPAQUE
from agent_reliability.experimental.judge import (
    FAILURE_CLASS_NAMES,
    ContentPart,
    ContentRole,
    EvaluationRequest,
    JudgeDimension,
    JudgeLimits,
    JudgePolicy,
    JudgeProviderRateLimitedError,
    JudgeProviderRefusedError,
    JudgeProviderUnavailableError,
    JudgeTimeoutError,
    SamplingPolicy,
    SyncLLMJudge,
    validate_identity_value,
)
from agent_reliability.experimental.judge.core import draw_nonce, parse_output
from agent_reliability.experimental.judge.testing import FakeSyncProvider, judge_reply
from agent_reliability.sdk.evaluator_runner import EvaluatorRunner
from tests.fakes.p29_judge import grounded_request, named_rubrics

pytestmark = pytest.mark.property

GR = named_rubrics()["gr-cit"]
WIRE = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9._:/-]{0,198}[A-Za-z0-9])?)$")
INTERSECTION = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")


@given(st.text(alphabet="abzAZ09._:/+- é", min_size=0, max_size=140))
def test_identity_accept_iff_intersection_and_implies_all_grammars(value: str) -> None:
    try:
        validate_identity_value(value, "v")
        accepted = True
    except ValueError:
        accepted = False
    assert accepted == (INTERSECTION.fullmatch(value) is not None)
    if accepted:
        assert SDK_OPAQUE.fullmatch(value)
        assert WIRE.fullmatch(value)
        assert _http_delivery._OPAQUE.fullmatch(value)
        assert len(value) <= 128


@given(st.integers(min_value=1, max_value=260))
def test_identity_length_boundary(length: int) -> None:
    value = "a" * length
    if length <= 128:
        assert validate_identity_value(value, "v") == value
    else:
        with pytest.raises(ValueError):
            validate_identity_value(value, "v")


_CANDIDATES = [f"{i:016x}" for i in range(6)]


@given(
    texts=st.lists(
        st.lists(st.sampled_from([*_CANDIDATES, "x", " ", "<<<END"]), max_size=6).map(
            "".join
        ),
        min_size=1,
        max_size=5,
    ),
    order=st.permutations(_CANDIDATES),
)
def test_nonce_never_appears_in_any_part(texts: list[str], order: list[str]) -> None:
    parts = [ContentPart(ContentRole.CONTEXT, t) for t in texts]
    source_values = iter([*order, "f" * 16])
    nonce = draw_nonce(parts, lambda: next(source_values))
    assert all(nonce not in t for t in texts)


@given(
    verdict=st.sampled_from(["pass", "fail", "unknown"]),
    confidence=st.sampled_from(["high", "medium", "low"]),
    citations=st.lists(st.integers(min_value=0, max_value=3), unique=True, max_size=4),
    reason=st.none()
    | st.text(alphabet=st.characters(blacklist_categories=("Cc", "Cs")), max_size=300)
    | st.text(alphabet="ab\n", max_size=300),
    wrap=st.sampled_from(["", "```json\n{}\n```", "```\n{}\n```", "  \n{}\r\n\t"]),
    code_index=st.integers(min_value=0, max_value=7),
)
def test_parse_round_trip(
    verdict: str,
    confidence: str,
    citations: list[int],
    reason: str | None,
    wrap: str,
    code_index: int,
) -> None:
    codes = GR.reason_codes.for_verdict(verdict)
    code = codes[code_index % len(codes)]
    if verdict == "pass" and not citations:
        citations = [0]
    doc: dict[str, Any] = {
        "schema": "gentlity.judge-output/1",
        "verdict": verdict,
        "code": code,
        "confidence": confidence,
        "citations": citations,
    }
    if reason is not None:
        doc["reason"] = reason
    text = json.dumps(doc, ensure_ascii=False)
    text = wrap.replace("{}", text) if wrap else text
    parsed = parse_output(text, GR, 4)
    assert (parsed.verdict, parsed.code, parsed.confidence.value) == (
        verdict,
        code,
        confidence,
    )
    assert list(parsed.citations) == citations
    assert parsed.reason == reason


@given(
    st.lists(
        st.text(min_size=6, max_size=40).map(lambda t: "☃☃" + t), min_size=1, max_size=5
    )
)
def test_request_repr_never_contains_generated_text(texts: list[str]) -> None:
    safe = [t.replace("\x00", "") for t in texts]
    parts = (
        *(ContentPart(ContentRole.CONTEXT, t) for t in safe[:-1]),
        ContentPart(ContentRole.ANSWER, safe[-1]),
    )
    request = EvaluationRequest(
        JudgeDimension.GROUNDEDNESS, parts, correlation_id=safe[0][:200]
    )
    for rendered in (repr(request), str(request), *(repr(p) for p in parts)):
        assert "☃" not in rendered


@given(
    run_id=st.text(max_size=40),
    low=st.floats(min_value=0, max_value=1),
    high=st.floats(min_value=0, max_value=1),
    salt=st.sampled_from(["", "s1", "salt.2"]),
)
def test_sampling_is_pure_and_monotonic_in_rate(
    run_id: str, low: float, high: float, salt: str
) -> None:
    low, high = min(low, high), max(low, high)
    a, b = SamplingPolicy(rate=low, salt=salt), SamplingPolicy(rate=high, salt=salt)
    assert a.decide(run_id) == a.decide(run_id)
    if a.decide(run_id):
        assert b.decide(run_id)
    assert SamplingPolicy(rate=0.0, salt=salt).decide(run_id) is False
    assert SamplingPolicy(rate=1.0, salt=salt).decide(run_id) is True


_STEPS = st.sampled_from(
    [
        "pass",
        "fail",
        "unknown",
        "invalid",
        "timeout",
        "unavailable",
        "rate_limited",
        "refused",
        "generic",
        "oversize",
    ]
)


def _step(kind: str) -> Any:
    return {
        "pass": judge_reply("pass", "supported_by_context", "high", [0]),
        "fail": judge_reply("fail", "unsupported_claim", "high", []),
        "unknown": judge_reply("unknown", "context_insufficient", "high", []),
        "invalid": "not json",
        "timeout": JudgeTimeoutError(),
        "unavailable": JudgeProviderUnavailableError(),
        "rate_limited": JudgeProviderRateLimitedError(0.0),
        "refused": JudgeProviderRefusedError(),
        "generic": RuntimeError("boom"),
        "oversize": "x" * 5000,
    }[kind]


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(
    kinds=st.lists(_STEPS, min_size=0, max_size=12),
    max_attempts=st.integers(min_value=1, max_value=5),
    repair_attempts=st.integers(min_value=0, max_value=2),
    repeats=st.integers(min_value=1, max_value=3),
)
def test_outcome_is_exactly_result_or_failure_and_never_from_a_failure(
    kinds: list[str], max_attempts: int, repair_attempts: int, repeats: int
) -> None:
    provider = FakeSyncProvider([_step(k) for k in kinds])
    judge = SyncLLMJudge(
        rubric=GR,
        provider=provider,
        model_label="prop",
        policy=JudgePolicy(repeats=repeats),
        limits=JudgeLimits(max_attempts=max_attempts, repair_attempts=repair_attempts),
        jitter=lambda: 0.0,
        sleep=lambda _s: None,
    )
    outcome = EvaluatorRunner().evaluate(judge, grounded_request())
    assert isinstance(outcome, (EvaluationResult, EvaluationExecutionFailure))
    assert provider.call_count <= repeats * (max_attempts + repair_attempts)
    consumed = kinds[: provider.call_count]
    if isinstance(outcome, EvaluationExecutionFailure):
        assert outcome.exception_type in FAILURE_CLASS_NAMES or (
            provider.call_count > len(kinds)  # script exhausted -> provider error
        )
        assert outcome.exception_type in FAILURE_CLASS_NAMES
    else:
        # A result is only ever produced from completed (valid) judgments.
        assert any(k in {"pass", "fail", "unknown"} for k in consumed)
        assert outcome.provenance.deterministic is False

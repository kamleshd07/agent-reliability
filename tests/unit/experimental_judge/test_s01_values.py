"""P29-S01-AC03 / AC04: request validation, config validation, redaction."""

from __future__ import annotations

import copy
import math
import pickle
from decimal import Decimal
from typing import Any

import pytest

from agent_reliability.experimental.judge import (
    Confidence,
    ContentPart,
    ContentRole,
    ContentTrust,
    EvaluationRequest,
    JudgeBudget,
    JudgeDimension,
    JudgeLimits,
    JudgePolicy,
    SamplingPolicy,
)

pytestmark = pytest.mark.unit

A = ContentPart(ContentRole.ANSWER, "answer text")
D = JudgeDimension.GROUNDEDNESS


def _req(*parts: ContentPart) -> EvaluationRequest:
    return EvaluationRequest(D, tuple(parts))


# ----------------------------------------------------------------- AC03: request


def test_p29_s01_ac03_minimal_request_and_empty_answer_allowed() -> None:
    assert _req(A).parts == (A,)
    assert _req(ContentPart(ContentRole.ANSWER, "")).parts[0].text == ""


def test_p29_s01_ac03_lists_are_normalized_to_tuple() -> None:
    request = EvaluationRequest(D, [A])  # type: ignore[arg-type]
    assert isinstance(request.parts, tuple)


@pytest.mark.parametrize(
    "parts",
    [
        (),
        (ContentPart(ContentRole.QUESTION, "q"),),
        (A, A),
        (
            A,
            ContentPart(ContentRole.QUESTION, "1"),
            ContentPart(ContentRole.QUESTION, "2"),
        ),
        (
            A,
            ContentPart(ContentRole.REFERENCE, "1"),
            ContentPart(ContentRole.REFERENCE, "2"),
        ),
        (
            A,
            ContentPart(ContentRole.INSTRUCTIONS, "1"),
            ContentPart(ContentRole.INSTRUCTIONS, "2"),
        ),
        (A, ContentPart(ContentRole.POLICY, "1"), ContentPart(ContentRole.POLICY, "2")),
        (A, *[ContentPart(ContentRole.CONTEXT, str(i)) for i in range(32)]),
    ],
)
def test_p29_s01_ac03_invalid_role_multiplicity_and_counts(
    parts: tuple[ContentPart, ...],
) -> None:
    with pytest.raises(ValueError):
        EvaluationRequest(D, parts)


def test_p29_s01_ac03_repeatable_roles_and_part_bound() -> None:
    contexts = tuple(ContentPart(ContentRole.CONTEXT, str(i)) for i in range(31))
    assert len(_req(A, *contexts).parts) == 32
    evidence = tuple(ContentPart(ContentRole.TASK_EVIDENCE, str(i)) for i in range(5))
    assert len(_req(A, *evidence).parts) == 6


def test_p29_s01_ac03_type_errors() -> None:
    with pytest.raises(TypeError):
        EvaluationRequest("groundedness", (A,))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        EvaluationRequest(D, "not parts")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        EvaluationRequest(D, (A, "text"))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ContentPart("answer", "x")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ContentPart(ContentRole.ANSWER, b"bytes")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ContentPart(ContentRole.ANSWER, "x", "trusted")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        EvaluationRequest(D, (A,), correlation_id=5)  # type: ignore[arg-type]


def test_p29_s01_ac03_nul_rejected_unicode_passed_through() -> None:
    with pytest.raises(ValueError):
        ContentPart(ContentRole.ANSWER, "a\x00b")
    text = "é \U0001f600 ‮"
    assert ContentPart(ContentRole.ANSWER, text).text == text  # no normalization
    with pytest.raises(ValueError):
        EvaluationRequest(D, (A,), correlation_id="x\x00")
    with pytest.raises(ValueError):
        EvaluationRequest(D, (A,), correlation_id="c" * 257)
    assert EvaluationRequest(D, (A,), correlation_id="c" * 256).correlation_id


@pytest.mark.parametrize(
    "role",
    [
        ContentRole.QUESTION,
        ContentRole.ANSWER,
        ContentRole.CONTEXT,
        ContentRole.TASK_EVIDENCE,
    ],
)
def test_p29_s01_ac03_trust_promotion_rejected(role: ContentRole) -> None:
    with pytest.raises(ValueError):
        ContentPart(role, "x", ContentTrust.TRUSTED)
    assert ContentPart(role, "x", ContentTrust.UNTRUSTED).effective_trust is (
        ContentTrust.UNTRUSTED
    )


@pytest.mark.parametrize(
    "role",
    [ContentRole.REFERENCE, ContentRole.INSTRUCTIONS, ContentRole.POLICY],
)
def test_p29_s01_ac03_operator_roles_trusted_by_default_demotable(
    role: ContentRole,
) -> None:
    assert ContentPart(role, "x").effective_trust is ContentTrust.TRUSTED
    assert ContentPart(role, "x", ContentTrust.TRUSTED).effective_trust is (
        ContentTrust.TRUSTED
    )
    assert ContentPart(role, "x", ContentTrust.UNTRUSTED).effective_trust is (
        ContentTrust.UNTRUSTED
    )


def test_p29_s01_ac03_default_trust_of_content_roles_is_untrusted() -> None:
    for role in (
        ContentRole.QUESTION,
        ContentRole.ANSWER,
        ContentRole.CONTEXT,
        ContentRole.TASK_EVIDENCE,
    ):
        assert ContentPart(role, "x").effective_trust is ContentTrust.UNTRUSTED


# ------------------------------------------------------- AC03: configuration types


@pytest.mark.parametrize(
    "kwargs",
    [
        {"provider_timeout_seconds": 0},
        {"provider_timeout_seconds": -1.0},
        {"provider_timeout_seconds": 600.1},
        {"provider_timeout_seconds": math.nan},
        {"provider_timeout_seconds": math.inf},
        {"provider_timeout_seconds": True},
        {"provider_timeout_seconds": "30"},
        {"evaluation_deadline_seconds": 0},
        {"evaluation_deadline_seconds": math.inf},
        {"provider_timeout_seconds": 20.0, "evaluation_deadline_seconds": 10.0},
        {"max_attempts": 0},
        {"max_attempts": 6},
        {"max_attempts": True},
        {"max_attempts": 2.0},
        {"repair_attempts": -1},
        {"repair_attempts": 3},
        {"max_input_chars": 0},
        {"max_input_chars": 1_000_001},
        {"max_output_tokens": 15},
        {"max_output_tokens": 4097},
        {"max_reply_chars": 255},
        {"max_reply_chars": 65_537},
        {"retry_backoff_cap_seconds": -0.1},
        {"retry_backoff_cap_seconds": math.nan},
    ],
)
def test_p29_s01_ac03_limits_reject_out_of_range(kwargs: dict[str, Any]) -> None:
    with pytest.raises((ValueError, TypeError)):
        JudgeLimits(**kwargs)


def test_p29_s01_ac03_limits_boundaries_accepted() -> None:
    limits = JudgeLimits(
        provider_timeout_seconds=600,
        evaluation_deadline_seconds=600,
        max_attempts=5,
        repair_attempts=2,
        max_input_chars=1_000_000,
        max_output_tokens=4096,
        max_reply_chars=65_536,
        retry_backoff_cap_seconds=0,
    )
    assert limits.provider_timeout_seconds == 600.0
    low = JudgeLimits(
        provider_timeout_seconds=0.001,
        evaluation_deadline_seconds=0.001,
        max_attempts=1,
        repair_attempts=0,
        max_input_chars=1,
        max_output_tokens=16,
        max_reply_chars=256,
    )
    assert low.max_attempts == 1
    assert JudgeLimits() == JudgeLimits()  # defaults of CON section 5
    assert JudgeLimits().max_input_chars == 32_000


@pytest.mark.parametrize(
    "kwargs",
    [
        {"repeats": 0},
        {"repeats": 4},
        {"repeats": True},
        {"repeats": 1.0},
        {"capture_reason": 1},
        {"min_confidence": "high"},
        {"min_confidence": 0.5},
    ],
)
def test_p29_s01_ac03_policy_rejects_invalid(kwargs: dict[str, Any]) -> None:
    with pytest.raises((ValueError, TypeError)):
        JudgePolicy(**kwargs)


def test_p29_s01_ac03_policy_defaults() -> None:
    policy = JudgePolicy()
    assert (policy.min_confidence, policy.repeats, policy.capture_reason) == (
        None,
        1,
        False,
    )
    assert JudgePolicy(min_confidence=Confidence.HIGH, repeats=3).repeats == 3


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_seconds": 0},
        {"window_seconds": True},
        {"window_seconds": 1.5},
        {"max_tokens_per_window": 0},
        {"max_tokens_per_window": True},
        {"max_tokens_per_window": 10.0},
        # CON-11: a monetary budget needs both prices.
        {"max_cost_per_window": Decimal("1")},
        {
            "max_cost_per_window": Decimal("1"),
            "input_price_per_1k_tokens": Decimal("1"),
        },
        {
            "max_cost_per_window": Decimal("1"),
            "output_price_per_1k_tokens": Decimal("1"),
        },
        {
            "max_cost_per_window": Decimal("0"),
            "input_price_per_1k_tokens": Decimal("1"),
            "output_price_per_1k_tokens": Decimal("1"),
        },
        {
            "max_cost_per_window": Decimal("NaN"),
            "input_price_per_1k_tokens": Decimal("1"),
            "output_price_per_1k_tokens": Decimal("1"),
        },
        {
            "max_cost_per_window": 1.0,
            "input_price_per_1k_tokens": Decimal("1"),
            "output_price_per_1k_tokens": Decimal("1"),
        },
        {"input_price_per_1k_tokens": Decimal("-1")},
        {"output_price_per_1k_tokens": Decimal("Infinity")},
        {"input_price_per_1k_tokens": 1},
    ],
)
def test_p29_s01_ac03_budget_rejects_invalid(kwargs: dict[str, Any]) -> None:
    with pytest.raises((ValueError, TypeError)):
        JudgeBudget(**kwargs)


def test_p29_s01_ac03_budget_valid_forms() -> None:
    assert JudgeBudget().enforces_anything is False
    assert JudgeBudget(max_tokens_per_window=1).enforces_anything is True
    priced = JudgeBudget(
        max_cost_per_window=Decimal("2.50"),
        input_price_per_1k_tokens=Decimal("0"),
        output_price_per_1k_tokens=Decimal("0.002"),
    )
    assert priced.enforces_anything is True


@pytest.mark.parametrize(
    "rate", [math.nan, -0.0001, 1.0001, math.inf, -math.inf, True, "1", None]
)
def test_p29_s01_ac03_sampling_rate_rejected(rate: Any) -> None:
    with pytest.raises((ValueError, TypeError)):
        SamplingPolicy(rate=rate)


def test_p29_s01_ac03_sampling_decide_is_pure_and_bounded() -> None:
    never, always = SamplingPolicy(rate=0.0), SamplingPolicy(rate=1.0)
    ids = [f"run-{i}" for i in range(2000)]
    assert not any(never.decide(i) for i in ids)
    assert all(always.decide(i) for i in ids)
    half = SamplingPolicy(rate=0.5, salt="s1")
    assert [half.decide(i) for i in ids] == [half.decide(i) for i in ids]
    observed = sum(half.decide(i) for i in ids) / len(ids)
    assert 0.45 < observed < 0.55  # loose sanity bound; S05 owns the statistical test
    other_salt = SamplingPolicy(rate=0.5, salt="s2")
    assert [half.decide(i) for i in ids] != [other_salt.decide(i) for i in ids]


# ------------------------------------------------------------------- AC04: redaction

SECRET = "PLANTED_SECRET_TEXT_9921"


def test_p29_s01_ac04_no_to_dict_and_repr_redacts() -> None:
    part = ContentPart(ContentRole.ANSWER, SECRET)
    request = EvaluationRequest(
        D, (part, ContentPart(ContentRole.CONTEXT, SECRET)), correlation_id=SECRET
    )
    for value in (part, request):
        assert not hasattr(value, "to_dict")
        for rendered in (repr(value), str(value), f"{value}", f"{value!s}"):
            assert SECRET not in rendered
    assert "chars=" in repr(part)
    assert "answer:" in repr(request)
    assert "correlation" not in repr(request)


def test_p29_s01_ac04_pickle_and_copy_refused() -> None:
    part = ContentPart(ContentRole.ANSWER, SECRET)
    request = _req(part)
    for value in (part, request):
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            with pytest.raises(TypeError):
                pickle.dumps(value, protocol)
        with pytest.raises(TypeError):
            copy.copy(value)
        with pytest.raises(TypeError):
            copy.deepcopy(value)
        with pytest.raises(TypeError):
            value.__reduce__()


def test_p29_s01_ac04_requests_are_frozen() -> None:
    request = _req(A)
    with pytest.raises(Exception, match="cannot assign"):
        request.dimension = JudgeDimension.SAFETY_POLICY  # type: ignore[misc]
    with pytest.raises(Exception, match="cannot assign"):
        A.text = "x"  # type: ignore[misc]

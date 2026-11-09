"""jp3: explicit verdict/code contract. jp1/jp2 unchanged; validation not relaxed."""

import hashlib
import json
import pathlib

import pytest

import agent_reliability.experimental.judge as j
from agent_reliability.experimental.judge import JudgePolicy
from agent_reliability.experimental.judge.behaviour import behaviour_of, template_digest
from agent_reliability.experimental.judge.core import build_prompt, parse_output
from agent_reliability.experimental.judge.errors import JudgeInvalidOutputError
from agent_reliability.experimental.judge.identity import compose_identity
from agent_reliability.experimental.judge.rubric import Rubric
from agent_reliability.experimental.judge.values import ContentPart, ContentRole

RUBRICS = pathlib.Path(j.__file__).parent / "rubrics"
NONCE = "0123456789abcdef"
QA = [ContentPart(ContentRole.QUESTION, "q"), ContentPart(ContentRole.ANSWER, "a")]
CTX = [*QA, ContentPart(ContentRole.CONTEXT, "c")]
ALL = sorted(p.stem for p in RUBRICS.glob("*.json"))


def _rubric(name):
    return Rubric.from_dict(json.loads((RUBRICS / f"{name}.json").read_text()))


def reply(verdict="pass", code="addresses_question", citations=()):
    return json.dumps(
        {
            "schema": "gentlity.judge-output/1",
            "verdict": verdict,
            "code": code,
            "confidence": "high",
            "citations": list(citations),
        }
    )


def _parse(rubric, text, n_ctx=0):
    return parse_output(text, rubric=rubric, context_count=n_ctx)


@pytest.mark.parametrize("name", ALL)
def test_every_rubric_lists_each_verdict_with_its_codes(name):
    r = _rubric(name)
    system = build_prompt(r, CTX, nonce=NONCE, template_id="jp3").system
    for verdict, codes in (
        ("pass", r.reason_codes.pass_),
        ("fail", r.reason_codes.fail),
        ("unknown", r.reason_codes.unknown),
    ):
        assert (
            f'- verdict "{verdict}": code must be one of {", ".join(codes)}' in system
        )
    assert "are NOT valid codes" in system


def test_missing_evidence_relevance_prompt_says_unestablished_facts_do_not_fail():
    r = _rubric("judge-answer-relevance")
    system = build_prompt(r, CTX, nonce=NONCE, template_id="jp3").system
    # relevance criteria do not require any context fact, so a fact missing from
    # the context is not a reason to fail or to answer unknown
    assert "A fact that none of the criteria requires is not a reason" in system
    assert '- verdict "pass": code must be one of addresses_question' in system


def test_no_context_keeps_the_jp2_empty_citation_rule():
    r = _rubric("judge-answer-relevance")
    s3 = build_prompt(r, QA, nonce=NONCE, template_id="jp3").system
    assert '"citations":[],' in s3 and "<context block indexes>" not in s3
    assert (
        'No context blocks are supplied in this evaluation: "citations" must be []'
        in s3
    )
    with_ctx = build_prompt(r, CTX, nonce=NONCE, template_id="jp3").system
    assert '"citations":[<context block indexes>],' in with_ctx


def test_jp1_and_jp2_text_are_unchanged():
    r = _rubric("judge-answer-relevance")
    for t in ("jp1", "jp2"):
        for parts in (QA, CTX):
            s = build_prompt(r, parts, nonce=NONCE, template_id=t).system
            assert "NOT valid codes" not in s and "Valid verdict/code pairs" not in s


def test_repair_text_only_for_jp3_invalid_code():
    r = _rubric("judge-answer-relevance")
    p3 = build_prompt(
        r, QA, nonce=NONCE, template_id="jp3", repair_error_class="invalid_code"
    )
    assert "verdicts, not codes" in p3.user
    for t, cls in (
        ("jp3", "invalid_json"),
        ("jp2", "invalid_code"),
        ("jp1", "invalid_code"),
    ):
        p = build_prompt(r, QA, nonce=NONCE, template_id=t, repair_error_class=cls)
        assert "verdicts, not codes" not in p.user


def test_verdict_echoed_as_code_is_still_rejected_not_corrected():
    r = _rubric("judge-answer-relevance")
    for code in ("pass", "fail", "unknown"):
        with pytest.raises(JudgeInvalidOutputError) as e:
            _parse(r, reply("pass", code))
        assert e.value.error_class == "invalid_code"


def test_verdict_code_mismatch_rejected():
    r = _rubric("judge-answer-relevance")
    with pytest.raises(JudgeInvalidOutputError) as e:
        _parse(r, reply("pass", "off_topic"))
    assert e.value.error_class == "invalid_code"
    with pytest.raises(JudgeInvalidOutputError):
        _parse(r, reply("fail", "addresses_question"))


def test_rubric_specific_code_selection_accepts_listed_pairs_only():
    for name in ALL:
        r = _rubric(name)
        n = 1
        for verdict, codes in (
            ("pass", r.reason_codes.pass_),
            ("fail", r.reason_codes.fail),
            ("unknown", r.reason_codes.unknown),
        ):
            for code in codes:
                cites = [0] if verdict == "pass" and r.require_citations else []
                out = _parse(r, reply(verdict, code, cites), n)
                assert out.verdict == verdict and out.code == code


def test_unknown_with_listed_code_parses_and_is_not_a_failure():
    r = _rubric("judge-answer-relevance")
    out = _parse(r, reply("unknown", "low_confidence"))
    assert out.verdict == "unknown"


def test_no_context_citation_still_strict_under_jp3():
    r = _rubric("judge-answer-relevance")
    with pytest.raises(JudgeInvalidOutputError) as e:
        _parse(r, reply(citations=[0]), 0)
    assert e.value.error_class == "invalid_citations"
    with pytest.raises(JudgeInvalidOutputError):
        _parse(r, reply(citations=[1]), 1)
    assert _parse(r, reply(citations=[]), 0).citations == ()


def test_prompt_version_reproducible_and_distinct():
    digests = {t: template_digest(t) for t in ("jp1", "jp2", "jp3")}
    assert len(set(digests.values())) == 3
    assert template_digest("jp3") == digests["jp3"]
    r = _rubric("judge-answer-relevance")
    a = build_prompt(r, CTX, nonce=NONCE, template_id="jp3")
    b = build_prompt(r, CTX, nonce=NONCE, template_id="jp3")
    assert a == b
    assert (
        hashlib.sha256(a.system.encode()).hexdigest()
        == hashlib.sha256(b.system.encode()).hexdigest()
    )


def test_identity_and_behaviour_record_jp3():
    r = _rubric("judge-answer-relevance")
    policy = JudgePolicy(prompt_template="jp3")
    ident = compose_identity(r, model_label="m", policy=policy)
    assert ".jp3." in ident.configuration_id
    default = compose_identity(r, model_label="m")
    assert ".jp1." in default.configuration_id
    b = behaviour_of(r, policy, None)
    assert b.template_id == "jp3" and b.template_digest == template_digest("jp3")


# --- review remediation (F1, F3, F4, F5) -----------------------------------

NEUTRAL = "Apply only the criteria above."


@pytest.mark.parametrize("name", ALL)
def test_scope_sentence_is_rubric_neutral_for_every_rubric(name):
    system = build_prompt(_rubric(name), CTX, nonce=NONCE, template_id="jp3").system
    assert NEUTRAL in system
    assert (
        "a fact that a criterion requires and the blocks do not establish is" in system
    )
    assert "even when the supplied blocks leave other" not in system


@pytest.mark.parametrize("name", ALL)
def test_no_context_pass_note_only_for_citation_requiring_rubrics(name):
    r = _rubric(name)
    note = 'a "pass" verdict cannot cite any'
    no_ctx = build_prompt(r, QA, nonce=NONCE, template_id="jp3").system
    with_ctx = build_prompt(r, CTX, nonce=NONCE, template_id="jp3").system
    assert (note in no_ctx) == r.require_citations
    assert note not in with_ctx


def test_citation_repair_text_for_jp3_only():
    r = _rubric("judge-answer-relevance")
    p = build_prompt(
        r, QA, nonce=NONCE, template_id="jp3", repair_error_class="invalid_citations"
    )
    assert "may only list indexes of context blocks that were supplied" in p.user
    p2 = build_prompt(
        r, QA, nonce=NONCE, template_id="jp2", repair_error_class="invalid_citations"
    )
    assert "may only list indexes" not in p2.user


def test_historical_template_digests_are_pinned():
    # Recorded at the commit before jp3 existed; jp1/jp2 identities must not move.
    assert template_digest("jp1") == (
        "9cabfba1017f99dba3cc20186e4e2d00793410437d4eafb9061096c5075f7d83"
    )
    assert template_digest("jp2") == (
        "43b12d0b3d55411d1bd19fc243bf173b3580278acee49667a8ddeae5482a8c0d"
    )


def test_jp3_digest_covers_the_repair_variants():
    # The digest must change if the jp3 repair text changes, so it renders them.
    r = _rubric("judge-answer-relevance")
    texts = {
        build_prompt(r, QA, nonce=NONCE, template_id="jp3", repair_error_class=c).user
        for c in (None, "invalid_code", "invalid_citations")
    }
    assert len(texts) == 3


def _relevance_request():
    from agent_reliability.experimental.judge.values import (
        EvaluationRequest,
        JudgeDimension,
    )

    return EvaluationRequest(JudgeDimension.ANSWER_RELEVANCE, tuple(QA))


def _judge(script):
    from agent_reliability.experimental.judge import JudgeLimits, LLMJudge
    from agent_reliability.experimental.judge.testing import FakeProvider

    provider = FakeProvider(script)
    judge = LLMJudge(
        rubric=_rubric("judge-answer-relevance"),
        provider=provider,
        model_label="t",
        policy=JudgePolicy(prompt_template="jp3"),
        limits=JudgeLimits(repair_attempts=1),
    )
    return judge, provider


def test_engine_sends_jp3_repair_text_on_the_second_call_and_recovers():
    import asyncio

    judge, provider = _judge(
        [reply("pass", "pass"), reply("pass", "addresses_question")]
    )
    decision = asyncio.run(judge.evaluate(_relevance_request()))
    assert provider.call_count == 2
    assert "verdicts, not codes" not in provider.calls[0].user
    assert "verdicts, not codes" in provider.calls[1].user
    assert provider.calls[0].system == provider.calls[1].system
    assert decision is not None


def test_engine_still_fails_when_the_code_stays_invalid():
    import asyncio

    judge, provider = _judge([reply("pass", "pass"), reply("pass", "pass")])
    with pytest.raises(JudgeInvalidOutputError) as e:
        asyncio.run(judge.evaluate(_relevance_request()))
    assert e.value.error_class == "invalid_code"
    assert provider.call_count == 2

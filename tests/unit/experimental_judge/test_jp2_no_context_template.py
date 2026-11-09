"""jp2: no-context citation text. jp1 is unchanged; validation is not relaxed."""

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


def _rubric(name):
    return Rubric.from_dict(json.loads((RUBRICS / f"{name}.json").read_text()))


QA = [ContentPart(ContentRole.QUESTION, "q"), ContentPart(ContentRole.ANSWER, "a")]
CTX = [*QA, ContentPart(ContentRole.CONTEXT, "c")]


def reply(citations):
    return json.dumps(
        {
            "schema": "gentlity.judge-output/1",
            "verdict": "pass",
            "code": "addresses_question",
            "confidence": "high",
            "citations": citations,
        }
    )


def test_jp1_prompt_is_unchanged_with_or_without_context():
    r = _rubric("judge-answer-relevance")
    for parts in (QA, CTX):
        default = build_prompt(r, parts, nonce=NONCE)
        explicit = build_prompt(r, parts, nonce=NONCE, template_id="jp1")
        assert default == explicit
        assert '"citations":[<context block indexes>]' in default.system
        assert "Each entry is the index of a context block" in default.system


def test_jp2_without_context_says_citations_must_be_empty():
    r = _rubric("judge-answer-relevance")
    p = build_prompt(r, QA, nonce=NONCE, template_id="jp2")
    assert '"citations":[],' in p.system and "<context block indexes>" not in p.system
    assert (
        'No context blocks are supplied in this evaluation: "citations" must be []'
        in p.system
    )
    assert "role=context" not in p.user


def test_jp2_with_context_is_identical_to_jp1():
    r = _rubric("judge-answer-relevance")
    assert build_prompt(r, CTX, nonce=NONCE, template_id="jp2") == build_prompt(
        r, CTX, nonce=NONCE
    )
    g = _rubric("judge-groundedness")
    parts = [
        ContentPart(ContentRole.CONTEXT, "c"),
        ContentPart(ContentRole.ANSWER, "a"),
    ]
    assert build_prompt(g, parts, nonce=NONCE, template_id="jp2") == build_prompt(
        g, parts, nonce=NONCE
    )


def test_unknown_template_is_rejected():
    with pytest.raises(ValueError):
        build_prompt(
            _rubric("judge-answer-relevance"), QA, nonce=NONCE, template_id="jp9"
        )
    with pytest.raises(ValueError):
        JudgePolicy(prompt_template="jp9")


def test_citation_validation_is_not_relaxed_by_jp2():
    r = _rubric("judge-answer-relevance")
    with pytest.raises(JudgeInvalidOutputError):
        parse_output(reply([0]), r, 0)  # nonexistent context block still rejected
    with pytest.raises(JudgeInvalidOutputError):
        parse_output(reply([1]), r, 1)
    assert parse_output(reply([]), r, 0).citations == ()


def test_identity_and_behaviour_record_the_template():
    r = _rubric("judge-answer-relevance")
    assert ".jp1." in compose_identity(r, model_label="m").configuration_id
    assert (
        ".jp2."
        in compose_identity(
            r, model_label="m", policy=JudgePolicy(prompt_template="jp2")
        ).configuration_id
    )
    b1, b2 = (
        behaviour_of(r, None, None),
        behaviour_of(r, JudgePolicy(prompt_template="jp2"), None),
    )
    assert (b1.template_id, b2.template_id) == ("jp1", "jp2")
    assert b1.template_digest != b2.template_digest
    assert template_digest() == template_digest("jp1") == b1.template_digest

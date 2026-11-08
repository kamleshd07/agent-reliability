"""Regression: relevance sends no context block, so a citation of index 0 stays invalid.

Found by the Qwen3-14B smoke diagnostic (docs/p29-calibration/human-calibration/qwen-relevance):
the model cited the question/answer ``index=0`` header. The strict validator is correct and
must not be relaxed; the local smoke rubric variant must load and keep it strict.
"""
import json
import pathlib

import pytest

from agent_reliability.experimental.judge.core import build_prompt, parse_output
from agent_reliability.experimental.judge.errors import JudgeInvalidOutputError
from agent_reliability.experimental.judge.rubric import Rubric
from agent_reliability.experimental.judge.values import ContentPart, ContentRole

VARIANT = (
    pathlib.Path(__file__).parents[3]
    / "docs/p29-calibration/human-calibration/qwen-relevance"
    / "judge-answer-relevance.no-context-note.json"
)


def _reply(citations):
    return json.dumps(
        {
            "schema": "gentlity.judge-output/1",
            "verdict": "pass",
            "code": "addresses_question",
            "confidence": "high",
            "citations": citations,
        }
    )


@pytest.fixture(scope="module")
def rubric():
    return Rubric.from_dict(json.loads(VARIANT.read_text()))


def test_variant_is_a_new_version_with_one_trusted_criterion(rubric):
    assert rubric.rubric_version == "2026-11.r1-smoke1"
    assert [c.id for c in rubric.criteria][-1] == "no-context-blocks"
    assert rubric.require_citations is False


def test_validator_still_rejects_citing_a_nonexistent_context_block(rubric):
    with pytest.raises(JudgeInvalidOutputError):
        parse_output(_reply([0]), rubric, 0)


def test_empty_citations_accepted_when_no_context_sent(rubric):
    assert parse_output(_reply([]), rubric, 0).citations == ()


def test_relevance_prompt_has_no_context_block_and_states_the_criterion(rubric):
    prompt = build_prompt(
        rubric,
        [ContentPart(ContentRole.QUESTION, "q"), ContentPart(ContentRole.ANSWER, "a")],
        nonce="0123456789abcdef",
    )
    assert "role=context" not in prompt.user
    assert "citations member must be []" in prompt.system

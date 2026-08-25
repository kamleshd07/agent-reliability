from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation import EqualityEvaluator, EvaluatorIdentity


@given(st.integers(), st.integers())
def test_equality_evaluator_matches_integer_equality(
    actual: int, expected: int
) -> None:
    evaluator = EqualityEvaluator(EvaluatorIdentity("integer-equality", "1"), expected)
    decision = evaluator.evaluate(actual)
    expected_outcome = (
        EvaluationOutcome.PASS if actual == expected else EvaluationOutcome.FAIL
    )
    assert decision.outcome is expected_outcome


@given(st.from_regex(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?", fullmatch=True))
def test_valid_evaluator_names_round_trip(name: str) -> None:
    assert EvaluatorIdentity(name, "1").name == name

from __future__ import annotations

from agent_reliability.domain import EvaluationOutcome


def test_three_distinct_values() -> None:
    assert {
        EvaluationOutcome.PASS,
        EvaluationOutcome.FAIL,
        EvaluationOutcome.UNKNOWN,
    } == set(EvaluationOutcome)


def test_is_not_boolean_like() -> None:
    # UNKNOWN must not be falsy/truthy-equivalent to FAIL/PASS.
    assert EvaluationOutcome.UNKNOWN != EvaluationOutcome.FAIL
    assert EvaluationOutcome.UNKNOWN != EvaluationOutcome.PASS
    assert EvaluationOutcome.UNKNOWN is not None

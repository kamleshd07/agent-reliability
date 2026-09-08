"""Adversarial privacy checks for the M8 built-in evaluators and reporting.

These duplicate a couple of assertions already made in the unit suite
deliberately: this file is the place a security reviewer looks first, and it
should not require cross-referencing unit tests to see the privacy
guarantees in one place.
"""

from __future__ import annotations

from agent_reliability.evaluation import ToolCalledEvaluator, ToolNotCalledEvaluator
from agent_reliability.evaluation.identity import EvaluatorIdentity


def test_tool_called_evaluator_state_is_exactly_two_fields() -> None:
    evaluator = ToolCalledEvaluator(EvaluatorIdentity("tool-called", "1"), "refund")
    assert evaluator.__slots__ == ("identity", "tool_name")


def test_tool_called_evaluator_does_not_absorb_extra_state_from_evaluate() -> None:
    evaluator = ToolCalledEvaluator(EvaluatorIdentity("tool-called", "1"), "refund")
    sensitive_tool_call_metadata = frozenset(
        {"refund", "charge_card:4111111111111111", "auth_token:super-secret"}
    )
    evaluator.evaluate(sensitive_tool_call_metadata)
    representation = repr(evaluator)
    assert "4111111111111111" not in representation
    assert "super-secret" not in representation
    # The frozenset itself is never retained on the instance.
    assert not any(
        isinstance(getattr(evaluator, slot), frozenset) for slot in evaluator.__slots__
    )


def test_tool_not_called_evaluator_state_is_exactly_two_fields() -> None:
    evaluator = ToolNotCalledEvaluator(
        EvaluatorIdentity("tool-not-called", "1"), "delete_account"
    )
    assert evaluator.__slots__ == ("identity", "tool_name")
    representation = repr(evaluator)
    assert "delete_account" in representation
    assert "tool_name='delete_account'" in representation


def test_tool_evaluators_never_expose_a_generic_call_arguments_field() -> None:
    """Structural guard against silently widening the privacy boundary: an
    evaluator that later grew an ``arguments``/``result``/``payload`` field
    would violate the documented privacy contract even if untested
    elsewhere."""
    forbidden = {"arguments", "args", "kwargs", "result", "results", "payload"}
    called = ToolCalledEvaluator(EvaluatorIdentity("tool-called", "1"), "x")
    not_called = ToolNotCalledEvaluator(EvaluatorIdentity("tool-not-called", "1"), "x")
    assert forbidden.isdisjoint(called.__slots__)
    assert forbidden.isdisjoint(not_called.__slots__)

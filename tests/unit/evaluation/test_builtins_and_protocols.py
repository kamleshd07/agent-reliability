from __future__ import annotations

import pytest

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation import (
    AsyncEvaluator,
    EqualityEvaluator,
    EvaluationDecision,
    EvaluatorIdentity,
    PredicateEvaluator,
    SyncEvaluator,
)


def test_equality_evaluator_exact_boundary_behavior() -> None:
    evaluator = EqualityEvaluator(EvaluatorIdentity("exact-result", "3"), 42)
    assert evaluator.evaluate(42) == EvaluationDecision(EvaluationOutcome.PASS, "equal")
    assert evaluator.evaluate(41) == EvaluationDecision(
        EvaluationOutcome.FAIL, "not_equal"
    )
    assert evaluator.deterministic is True


def test_predicate_maps_true_false_and_none_without_truthiness_magic() -> None:
    evaluator = PredicateEvaluator(
        identity=EvaluatorIdentity("positive-value", "1"),
        predicate=lambda value: None if value == 0 else value > 0,
        deterministic=True,
    )
    assert evaluator.evaluate(1).outcome is EvaluationOutcome.PASS
    assert evaluator.evaluate(-1).outcome is EvaluationOutcome.FAIL
    assert evaluator.evaluate(0).outcome is EvaluationOutcome.UNKNOWN


def test_custom_sync_evaluator_is_structurally_compatible() -> None:
    class CustomEvaluator:
        identity = EvaluatorIdentity("custom-rule", "2026-08-25")
        deterministic = True

        def evaluate(self, value: str) -> EvaluationDecision:
            return EvaluationDecision(
                EvaluationOutcome.PASS if value == "ok" else EvaluationOutcome.FAIL,
                "custom_rule",
            )

    evaluator: SyncEvaluator[str] = CustomEvaluator()
    assert evaluator.evaluate("ok").outcome is EvaluationOutcome.PASS


async def test_custom_async_evaluator_is_structurally_compatible() -> None:
    class CustomAsyncEvaluator:
        identity = EvaluatorIdentity("async-rule", "build-184")
        deterministic = False

        async def evaluate(self, value: str) -> EvaluationDecision:
            return EvaluationDecision(
                EvaluationOutcome.PASS if value else EvaluationOutcome.UNKNOWN
            )

    evaluator: AsyncEvaluator[str] = CustomAsyncEvaluator()
    assert (await evaluator.evaluate("ok")).outcome is EvaluationOutcome.PASS


def test_equality_rejects_non_boolean_comparison_protocols() -> None:
    class AmbiguousEquality:
        def __eq__(self, other: object) -> object:
            return object()

    evaluator = EqualityEvaluator(
        EvaluatorIdentity("ambiguous-equality", "1"), AmbiguousEquality()
    )
    with pytest.raises(TypeError, match="must return bool"):
        evaluator.evaluate(AmbiguousEquality())


def test_predicate_validates_configuration_and_return_type() -> None:
    with pytest.raises(TypeError, match="callable"):
        PredicateEvaluator(  # type: ignore[arg-type]
            EvaluatorIdentity("invalid-predicate", "1"), object(), True
        )
    with pytest.raises(TypeError, match="deterministic"):
        PredicateEvaluator(  # type: ignore[arg-type]
            EvaluatorIdentity("invalid-predicate", "1"), lambda _: True, 1
        )
    evaluator = PredicateEvaluator(
        EvaluatorIdentity("invalid-return", "1"),
        lambda _: 1,  # type: ignore[arg-type,return-value]
        True,
    )
    with pytest.raises(TypeError, match="bool or None"):
        evaluator.evaluate(object())

"""Regression snapshot for the unreleased M8 (developer-adoption) additions.

These names are not yet part of a tagged release. This file exists so that,
once they do ship, this becomes the same kind of frozen historical record as
``test_public_api_1_0.py``/``test_public_api_1_1.py`` — and so that, in the
meantime, any accidental signature/behavior drift while M8 is still being
built is caught immediately.
"""

from __future__ import annotations

import inspect

import agent_reliability.evaluation as evaluation
import agent_reliability.reliability as reliability
import agent_reliability.reporting as reporting
import agent_reliability.testing as testing
from agent_reliability.domain import EvaluationOutcome as DomainEvaluationOutcome
from agent_reliability.evaluation import (
    EvaluationOutcome as EvaluationEvaluationOutcome,
)


def test_evaluation_outcome_is_reexported_not_duplicated() -> None:
    """The friction bug this fixes: importing EvaluationOutcome from
    ``agent_reliability.evaluation`` used to raise ImportError even though
    every sibling evaluation type lives there. It must be the *same* object
    as ``agent_reliability.domain.EvaluationOutcome``, not a parallel enum.
    """
    assert EvaluationEvaluationOutcome is DomainEvaluationOutcome
    assert "EvaluationOutcome" in evaluation.__all__


def test_new_builtin_evaluator_names_are_exported() -> None:
    for name in (
        "ContainsEvaluator",
        "RegexMatchEvaluator",
        "LatencyThresholdEvaluator",
        "ToolCalledEvaluator",
        "ToolNotCalledEvaluator",
    ):
        assert name in evaluation.__all__
        assert hasattr(evaluation, name)


def test_reliability_convenience_api_is_exported() -> None:
    assert "evaluate_reliability_or_raise" in reliability.__all__
    assert "AggregationConflictError" in reliability.__all__
    assert issubclass(reliability.AggregationConflictError, RuntimeError)


def test_reporting_namespace_exports() -> None:
    assert reporting.__all__ == ["format_report", "report_to_dict"]


def test_testing_namespace_exports() -> None:
    assert testing.__all__ == ["assert_slo_met"]


def test_new_evaluator_signatures() -> None:
    assert str(inspect.signature(evaluation.ContainsEvaluator)) == (
        "(identity: 'EvaluatorIdentity', substring: 'str', "
        "case_sensitive: 'bool' = True) -> None"
    )
    assert str(inspect.signature(evaluation.LatencyThresholdEvaluator)) == (
        "(identity: 'EvaluatorIdentity', threshold_seconds: 'float', "
        "inclusive: 'bool' = True) -> None"
    )
    assert str(inspect.signature(evaluation.ToolCalledEvaluator)) == (
        "(identity: 'EvaluatorIdentity', tool_name: 'str') -> None"
    )
    assert str(inspect.signature(evaluation.ToolNotCalledEvaluator)) == (
        "(identity: 'EvaluatorIdentity', tool_name: 'str') -> None"
    )


def test_convenience_and_helper_signatures() -> None:
    assert str(inspect.signature(reliability.evaluate_reliability_or_raise)) == str(
        inspect.signature(reliability.evaluate_reliability)
    ).replace("-> 'ReliabilityReport | AggregationConflict'", "-> 'ReliabilityReport'")
    assert str(inspect.signature(testing.assert_slo_met)) == (
        "(report: 'ReliabilityReport | AggregationConflict', *, "
        "message: 'str | None' = None) -> 'None'"
    )
    assert str(inspect.signature(reporting.format_report)) == (
        "(report: 'ReliabilityReport') -> 'str'"
    )
    assert str(inspect.signature(reporting.report_to_dict)) == (
        "(report: 'ReliabilityReport') -> 'dict[str, Any]'"
    )

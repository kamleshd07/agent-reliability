"""Coverage for the M8 evaluate_reliability_or_raise convenience API."""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction

import pytest

from agent_reliability.domain import (
    EvaluationOutcome,
    ObjectiveDirection,
    Slo,
    UnknownPolicy,
)
from agent_reliability.evaluation import EvaluationProvenance, EvaluatorIdentity
from agent_reliability.reliability import (
    AggregationConflictError,
    ReliabilityObservation,
    ReliabilityReport,
    evaluate_reliability,
    evaluate_reliability_or_raise,
)

_SLO = Slo("task-success", Fraction(3, 4), ObjectiveDirection.AT_LEAST)


def _observation(
    outcome: EvaluationOutcome, version: str = "1"
) -> ReliabilityObservation:
    return ReliabilityObservation(
        indicator="task_success",
        outcome=outcome,
        provenance=EvaluationProvenance(
            EvaluatorIdentity("judge", version),
            datetime(2026, 1, 1, tzinfo=UTC),
            True,
        ),
    )


def test_or_raise_returns_the_same_report_as_the_explicit_api() -> None:
    observations = [_observation(EvaluationOutcome.PASS)] * 3 + [
        _observation(EvaluationOutcome.FAIL)
    ]
    explicit = evaluate_reliability(
        indicator="task_success",
        observations=observations,
        slo=_SLO,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    convenience = evaluate_reliability_or_raise(
        indicator="task_success",
        observations=observations,
        slo=_SLO,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    assert isinstance(explicit, ReliabilityReport)
    assert explicit == convenience


def test_or_raise_raises_on_genuine_conflict_carrying_the_original_conflict() -> None:
    observations = [
        _observation(EvaluationOutcome.PASS, version="1"),
        _observation(EvaluationOutcome.PASS, version="2"),
    ]
    with pytest.raises(AggregationConflictError) as excinfo:
        evaluate_reliability_or_raise(
            indicator="task_success",
            observations=observations,
            slo=_SLO,
            unknown_policy=UnknownPolicy.EXCLUDE,
        )
    conflict = excinfo.value.conflict
    reasons = {reason.value for reason in conflict.reasons}
    assert "evaluator_version_mismatch" in reasons
    # The exception message names the conflict; it does not fabricate a number.
    assert "not one comparable cohort" in str(excinfo.value)


def test_or_raise_does_not_resolve_or_hide_the_conflict() -> None:
    """The convenience API must raise, not silently pick a winner."""
    observations = [
        _observation(EvaluationOutcome.PASS, version="a"),
        _observation(EvaluationOutcome.PASS, version="b"),
    ]
    explicit = evaluate_reliability(
        indicator="task_success",
        observations=observations,
        slo=_SLO,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    assert not isinstance(explicit, ReliabilityReport)
    with pytest.raises(AggregationConflictError):
        evaluate_reliability_or_raise(
            indicator="task_success",
            observations=observations,
            slo=_SLO,
            unknown_policy=UnknownPolicy.EXCLUDE,
        )


def test_or_raise_propagates_ordinary_argument_errors_unchanged() -> None:
    with pytest.raises(TypeError, match="slo must be an Slo"):
        evaluate_reliability_or_raise(
            indicator="task_success",
            observations=[],
            slo=object(),  # type: ignore[arg-type]
            unknown_policy=UnknownPolicy.EXCLUDE,
        )

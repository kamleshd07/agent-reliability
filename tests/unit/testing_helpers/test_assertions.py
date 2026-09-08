"""Coverage for agent_reliability.testing.assert_slo_met."""

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
from agent_reliability.reliability import ReliabilityObservation, evaluate_reliability
from agent_reliability.testing import assert_slo_met

_MET_SLO = Slo("task-success", Fraction(1, 2), ObjectiveDirection.AT_LEAST)
_BREACHED_SLO = Slo("task-success", Fraction(99, 100), ObjectiveDirection.AT_LEAST)


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


def _report(observations, slo):
    return evaluate_reliability(
        indicator="task_success",
        observations=observations,
        slo=slo,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )


def test_met_slo_does_not_raise() -> None:
    report = _report(
        [_observation(EvaluationOutcome.PASS)] * 3
        + [_observation(EvaluationOutcome.FAIL)],
        _MET_SLO,
    )
    assert_slo_met(report)  # must not raise


def test_breached_slo_raises_with_observed_and_target() -> None:
    report = _report(
        [_observation(EvaluationOutcome.PASS)] * 3
        + [_observation(EvaluationOutcome.FAIL)],
        _BREACHED_SLO,
    )
    with pytest.raises(AssertionError) as excinfo:
        assert_slo_met(report)
    message = str(excinfo.value)
    assert "BREACHED" in message
    assert "75.00%" in message  # observed
    assert "99.00%" in message  # target
    assert "pass=3, fail=1, unknown=0" in message


def test_no_data_is_never_treated_as_passing() -> None:
    report = _report([], _MET_SLO)
    with pytest.raises(AssertionError, match="NO DATA"):
        assert_slo_met(report)


def test_aggregation_conflict_is_not_swallowed_silently() -> None:
    conflict = _report(
        [
            _observation(EvaluationOutcome.PASS, version="1"),
            _observation(EvaluationOutcome.PASS, version="2"),
        ],
        _MET_SLO,
    )
    with pytest.raises(AssertionError, match="not one comparable cohort"):
        assert_slo_met(conflict)


def test_custom_message_is_prefixed() -> None:
    report = _report([], _MET_SLO)
    with pytest.raises(AssertionError, match=r"^nightly regression run: "):
        assert_slo_met(report, message="nightly regression run")


def test_rejects_wrong_type() -> None:
    with pytest.raises(TypeError, match="ReliabilityReport or AggregationConflict"):
        assert_slo_met(object())  # type: ignore[arg-type]


def test_message_does_not_leak_arbitrary_payloads() -> None:
    """The message must only ever contain bounded, structural fields."""
    report = _report(
        [_observation(EvaluationOutcome.PASS)] * 3
        + [_observation(EvaluationOutcome.FAIL)],
        _BREACHED_SLO,
    )
    with pytest.raises(AssertionError) as excinfo:
        assert_slo_met(report)
    message = str(excinfo.value)
    for forbidden in ("prompt", "response", "secret", "api_key", "password"):
        assert forbidden not in message.lower()

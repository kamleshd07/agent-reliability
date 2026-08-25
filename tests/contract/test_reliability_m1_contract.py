from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction

import pytest

from agent_reliability.domain import (
    EvaluationOutcome,
    ObjectiveDirection,
    Slo,
    UnknownPolicy,
    compute_burn_rate,
    compute_error_budget,
    compute_ratio,
    evaluate_slo,
)
from agent_reliability.evaluation import EvaluationProvenance, EvaluatorIdentity
from agent_reliability.reliability import (
    ReliabilityObservation,
    ReliabilityReport,
    evaluate_reliability,
)

pytestmark = pytest.mark.contract


def test_report_components_are_exact_m1_outputs() -> None:
    provenance = EvaluationProvenance(
        EvaluatorIdentity("contract-check", "v1"),
        datetime(2026, 1, 1, tzinfo=UTC),
        True,
    )
    outcomes = [
        EvaluationOutcome.PASS,
        EvaluationOutcome.FAIL,
        EvaluationOutcome.UNKNOWN,
    ]
    observations = [
        ReliabilityObservation("contract", outcome, provenance) for outcome in outcomes
    ]
    slo = Slo("contract", Fraction(3, 4), ObjectiveDirection.AT_LEAST)
    policy = UnknownPolicy.TREAT_AS_BAD
    report = evaluate_reliability(
        indicator="contract",
        observations=observations,
        slo=slo,
        unknown_policy=policy,
        burn_rate_lookback=observations,
    )
    assert isinstance(report, ReliabilityReport)
    ratio = compute_ratio(outcomes, unknown_policy=policy)
    assert report.ratio == ratio
    assert report.slo_evaluation == evaluate_slo(slo, ratio)
    assert report.error_budget == compute_error_budget(slo, ratio)
    assert report.burn_rate == compute_burn_rate(slo, ratio)

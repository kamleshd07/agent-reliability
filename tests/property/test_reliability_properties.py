from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction

from hypothesis import given
from hypothesis import strategies as st

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
    AggregationConflict,
    ReliabilityObservation,
    ReliabilityReport,
    evaluate_reliability,
)

OUTCOMES = st.lists(st.sampled_from(list(EvaluationOutcome)), max_size=100)
POLICIES = st.sampled_from(list(UnknownPolicy))
SLO = Slo("task", Fraction(9, 10), ObjectiveDirection.AT_LEAST)
PROVENANCE = EvaluationProvenance(
    EvaluatorIdentity("exact-check", "v1"),
    datetime(2026, 1, 1, tzinfo=UTC),
    True,
)


def _observations(outcomes: list[EvaluationOutcome]) -> list[ReliabilityObservation]:
    return [
        ReliabilityObservation("task_success", outcome, PROVENANCE)
        for outcome in outcomes
    ]


@given(OUTCOMES, POLICIES)
def test_order_does_not_change_report(
    outcomes: list[EvaluationOutcome], policy: UnknownPolicy
) -> None:
    observations = _observations(outcomes)
    forward = evaluate_reliability(
        indicator="task_success",
        observations=observations,
        slo=SLO,
        unknown_policy=policy,
    )
    backward = evaluate_reliability(
        indicator="task_success",
        observations=reversed(observations),
        slo=SLO,
        unknown_policy=policy,
    )
    assert forward == backward


@given(OUTCOMES, POLICIES)
def test_m5_results_equal_direct_m1_results(
    outcomes: list[EvaluationOutcome], policy: UnknownPolicy
) -> None:
    result = evaluate_reliability(
        indicator="task_success",
        observations=_observations(outcomes),
        slo=SLO,
        unknown_policy=policy,
    )
    assert isinstance(result, ReliabilityReport)
    ratio = compute_ratio(outcomes, unknown_policy=policy)
    assert result.ratio == ratio
    assert result.slo_evaluation == evaluate_slo(SLO, ratio)
    assert result.error_budget == compute_error_budget(SLO, ratio)
    assert (
        result.ratio.pass_count + result.ratio.fail_count + result.ratio.unknown_count
        == len(outcomes)
    )


@given(OUTCOMES, OUTCOMES, POLICIES)
def test_compatible_partition_preserves_counts(
    left: list[EvaluationOutcome],
    right: list[EvaluationOutcome],
    policy: UnknownPolicy,
) -> None:
    combined = evaluate_reliability(
        indicator="task_success",
        observations=_observations(left + right),
        slo=SLO,
        unknown_policy=policy,
    )
    assert isinstance(combined, ReliabilityReport)
    assert combined.ratio.pass_count == (left + right).count(EvaluationOutcome.PASS)
    assert combined.ratio.fail_count == (left + right).count(EvaluationOutcome.FAIL)
    assert combined.ratio.unknown_count == (left + right).count(
        EvaluationOutcome.UNKNOWN
    )


@given(OUTCOMES, POLICIES)
def test_burn_rate_equals_direct_m1(
    lookback: list[EvaluationOutcome], policy: UnknownPolicy
) -> None:
    full = _observations([EvaluationOutcome.PASS])
    result = evaluate_reliability(
        indicator="task_success",
        observations=full,
        slo=SLO,
        unknown_policy=policy,
        burn_rate_lookback=_observations(lookback),
    )
    assert isinstance(result, ReliabilityReport)
    expected_ratio = compute_ratio(lookback, unknown_policy=policy)
    assert result.burn_rate == compute_burn_rate(SLO, expected_ratio)


@given(
    st.from_regex(
        r"[A-Za-z0-9](?:[A-Za-z0-9._+-]{0,18}[A-Za-z0-9])?", fullmatch=True
    ).filter(lambda value: value != "v1")
)
def test_different_version_never_produces_report(version: str) -> None:
    identity = EvaluatorIdentity("exact-check", version)
    different = EvaluationProvenance(identity, datetime(2026, 1, 2, tzinfo=UTC), True)
    result = evaluate_reliability(
        indicator="task_success",
        observations=[
            ReliabilityObservation("task_success", EvaluationOutcome.PASS, PROVENANCE),
            ReliabilityObservation("task_success", EvaluationOutcome.PASS, different),
        ],
        slo=SLO,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    assert isinstance(result, AggregationConflict)

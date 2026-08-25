"""GA golden cases for meaning, not implementation shape."""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction

from agent_reliability.domain import (
    BudgetStatus,
    EvaluationOutcome,
    ObjectiveDirection,
    Slo,
    SloStatus,
    UnknownPolicy,
)
from agent_reliability.evaluation import EvaluationProvenance, EvaluatorIdentity
from agent_reliability.reliability import (
    AggregationConflict,
    AggregationConflictReason,
    ReliabilityObservation,
    ReliabilityReport,
    evaluate_reliability,
)

SLO = Slo("task-success", Fraction(3, 4), ObjectiveDirection.AT_LEAST)
PROVENANCE = EvaluationProvenance(
    EvaluatorIdentity("ga-rule", "1", "strict"),
    datetime(2026, 1, 1, tzinfo=UTC),
    True,
)


def _observation(
    outcome: EvaluationOutcome,
    *,
    indicator: str = "task_success",
    provenance: EvaluationProvenance | None = PROVENANCE,
) -> ReliabilityObservation:
    return ReliabilityObservation(indicator, outcome, provenance)


def _report(
    observations: object, policy: UnknownPolicy = UnknownPolicy.EXCLUDE
) -> ReliabilityReport | AggregationConflict:
    return evaluate_reliability(
        indicator="task_success",
        observations=observations,  # type: ignore[arg-type]
        slo=SLO,
        unknown_policy=policy,
    )


def test_unknown_policy_is_explicit_and_changes_exact_denominator() -> None:
    values = [
        _observation(EvaluationOutcome.PASS),
        _observation(EvaluationOutcome.FAIL),
        _observation(EvaluationOutcome.UNKNOWN),
    ]
    ratios = {}
    for policy in UnknownPolicy:
        result = _report(values, policy)
        assert isinstance(result, ReliabilityReport)
        ratios[policy] = result.ratio.pass_ratio
    assert ratios == {
        UnknownPolicy.EXCLUDE: Fraction(1, 2),
        UnknownPolicy.TREAT_AS_BAD: Fraction(1, 3),
        UnknownPolicy.TREAT_AS_GOOD: Fraction(2, 3),
    }


def test_empty_data_never_invents_reliability() -> None:
    result = _report([])
    assert isinstance(result, ReliabilityReport)
    assert result.ratio.pass_ratio is None
    assert result.slo_evaluation.status is SloStatus.UNKNOWN
    assert result.error_budget.status is BudgetStatus.NO_DATA


def test_exact_slo_boundary_is_met() -> None:
    result = _report(
        [
            _observation(EvaluationOutcome.PASS),
            _observation(EvaluationOutcome.PASS),
            _observation(EvaluationOutcome.PASS),
            _observation(EvaluationOutcome.FAIL),
        ]
    )
    assert isinstance(result, ReliabilityReport)
    assert result.ratio.pass_ratio == Fraction(3, 4)
    assert result.slo_evaluation.status is SloStatus.MET
    assert result.error_budget.remaining_fraction == Fraction(0)


def test_zero_tolerance_has_typed_non_float_states() -> None:
    zero = Slo("perfect", Fraction(1), ObjectiveDirection.AT_LEAST)
    intact = evaluate_reliability(
        indicator="task_success",
        observations=[_observation(EvaluationOutcome.PASS)],
        slo=zero,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    exceeded = evaluate_reliability(
        indicator="task_success",
        observations=[_observation(EvaluationOutcome.FAIL)],
        slo=zero,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    assert isinstance(intact, ReliabilityReport)
    assert isinstance(exceeded, ReliabilityReport)
    assert intact.error_budget.status is BudgetStatus.ZERO_TOLERANCE_INTACT
    assert intact.error_budget.consumption_ratio == Fraction(0)
    assert exceeded.error_budget.status is BudgetStatus.ZERO_TOLERANCE_EXCEEDED
    assert exceeded.error_budget.consumption_ratio is None


def test_each_supplied_observation_counts_once_and_order_does_not_matter() -> None:
    values = [
        _observation(EvaluationOutcome.PASS),
        _observation(EvaluationOutcome.PASS),
        _observation(EvaluationOutcome.FAIL),
    ]
    forward = _report(iter(values))
    backward = _report(reversed(values))
    assert forward == backward
    assert isinstance(forward, ReliabilityReport)
    assert forward.ratio.pass_count == 2
    assert forward.ratio.fail_count == 1


def test_methodology_and_manual_mixes_fail_closed_without_number() -> None:
    v2 = EvaluationProvenance(
        EvaluatorIdentity("ga-rule", "2", "strict"),
        datetime(2026, 1, 2, tzinfo=UTC),
        True,
    )
    version_conflict = _report(
        [
            _observation(EvaluationOutcome.PASS),
            _observation(EvaluationOutcome.PASS, provenance=v2),
        ]
    )
    manual_conflict = _report(
        [
            _observation(EvaluationOutcome.PASS),
            _observation(EvaluationOutcome.PASS, provenance=None),
        ]
    )
    assert version_conflict == AggregationConflict(
        frozenset({AggregationConflictReason.EVALUATOR_VERSION_MISMATCH})
    )
    assert manual_conflict == AggregationConflict(
        frozenset({AggregationConflictReason.MANUAL_EVALUATED_MIX})
    )
    assert not hasattr(version_conflict, "ratio")

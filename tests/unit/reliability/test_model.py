from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from fractions import Fraction

import pytest

from agent_reliability.domain import (
    BurnRate,
    ErrorBudget,
    EvaluationOutcome,
    ObjectiveDirection,
    Slo,
    UnknownPolicy,
    compute_burn_rate,
    compute_error_budget,
    compute_ratio,
    evaluate_slo,
)
from agent_reliability.evaluation import (
    EvaluationProvenance,
    EvaluationResult,
    EvaluatorIdentity,
)
from agent_reliability.reliability import (
    AggregationConflict,
    AggregationConflictReason,
    ReliabilityCohort,
    ReliabilityObservation,
    ReliabilityReport,
)


def _provenance(*, deterministic: bool = True) -> EvaluationProvenance:
    return EvaluationProvenance(
        identity=EvaluatorIdentity("exact-check", "v1", "strict"),
        evaluated_at=datetime(2026, 1, 1, tzinfo=UTC),
        deterministic=deterministic,
    )


@pytest.mark.parametrize(
    "indicator", ["task_success", "Task_Success", "task-success", "a", "a.b/c:1"]
)
def test_valid_indicator_is_preserved_exactly(indicator: str) -> None:
    observation = ReliabilityObservation.manual(
        indicator=indicator, outcome=EvaluationOutcome.PASS
    )
    assert observation.indicator == indicator


@pytest.mark.parametrize(
    "indicator",
    ["", "a" * 129, "task success", "task\nsuccess", "tásk", None, 4],
)
def test_invalid_indicator_is_rejected(indicator: object) -> None:
    expected = TypeError if not isinstance(indicator, str) else ValueError
    with pytest.raises(expected):
        ReliabilityObservation.manual(  # type: ignore[arg-type]
            indicator=indicator, outcome=EvaluationOutcome.PASS
        )


def test_observation_validates_outcome_and_provenance() -> None:
    with pytest.raises(TypeError, match="outcome"):
        ReliabilityObservation("task_success", "pass")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="provenance"):
        ReliabilityObservation(  # type: ignore[arg-type]
            "task_success", EvaluationOutcome.PASS, object()
        )


def test_evaluation_result_factory_keeps_only_outcome_and_provenance() -> None:
    provenance = _provenance()
    result = EvaluationResult(
        outcome=EvaluationOutcome.FAIL,
        provenance=provenance,
        reason_code="not_equal",
    )
    observation = ReliabilityObservation.from_evaluation(
        indicator="task_success", result=result
    )
    assert observation == ReliabilityObservation(
        "task_success", EvaluationOutcome.FAIL, provenance
    )
    assert not hasattr(observation, "reason_code")
    with pytest.raises(TypeError, match="result"):
        ReliabilityObservation.from_evaluation(  # type: ignore[arg-type]
            indicator="task_success", result=object()
        )


def test_manual_and_evaluated_cohort_projection() -> None:
    manual = ReliabilityObservation.manual(
        indicator="task_success", outcome=EvaluationOutcome.PASS
    )
    evaluated = ReliabilityObservation(
        "task_success", EvaluationOutcome.PASS, _provenance()
    )
    assert ReliabilityCohort.from_observation(manual) == ReliabilityCohort(
        "task_success", None, None
    )
    assert ReliabilityCohort.from_observation(evaluated) == ReliabilityCohort(
        "task_success", _provenance().identity, True
    )
    with pytest.raises(TypeError, match="observation"):
        ReliabilityCohort.from_observation(object())  # type: ignore[arg-type]


def test_cohort_invariants() -> None:
    identity = _provenance().identity
    with pytest.raises(ValueError, match="manual"):
        ReliabilityCohort("task_success", None, True)
    with pytest.raises(TypeError, match="evaluator_identity"):
        ReliabilityCohort("task_success", object(), True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="bool"):
        ReliabilityCohort("task_success", identity, None)


def test_conflict_invariants_and_immutability() -> None:
    reason = AggregationConflictReason.INDICATOR_MISMATCH
    conflict = AggregationConflict(frozenset({reason}))
    assert conflict.reasons == frozenset({reason})
    with pytest.raises(FrozenInstanceError):
        conflict.reasons = frozenset()  # type: ignore[misc]
    with pytest.raises(TypeError, match="frozenset"):
        AggregationConflict({reason})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="empty"):
        AggregationConflict(frozenset())
    with pytest.raises(TypeError, match="every reason"):
        AggregationConflict(frozenset({"indicator_mismatch"}))  # type: ignore[arg-type]


def test_observation_and_cohort_are_immutable() -> None:
    observation = ReliabilityObservation.manual(
        indicator="task_success", outcome=EvaluationOutcome.PASS
    )
    cohort = ReliabilityCohort.from_observation(observation)
    with pytest.raises(FrozenInstanceError):
        observation.outcome = EvaluationOutcome.FAIL  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        cohort.indicator = "other"  # type: ignore[misc]


def _valid_report() -> ReliabilityReport:
    slo = Slo("task-success", Fraction(9, 10), ObjectiveDirection.AT_LEAST)
    ratio = compute_ratio(
        [EvaluationOutcome.PASS], unknown_policy=UnknownPolicy.EXCLUDE
    )
    return ReliabilityReport(
        indicator="task_success",
        cohort=ReliabilityCohort("task_success", None, None),
        ratio=ratio,
        slo_evaluation=evaluate_slo(slo, ratio),
        error_budget=compute_error_budget(slo, ratio),
    )


def test_report_is_immutable_and_composes_m1_values() -> None:
    report = _valid_report()
    assert report.ratio.pass_ratio == 1
    assert report.slo_evaluation.ratio is report.ratio
    assert report.error_budget.ratio is report.ratio
    with pytest.raises(FrozenInstanceError):
        report.indicator = "other"  # type: ignore[misc]


def test_report_rejects_invalid_cohort_and_ratio_shapes() -> None:
    report = _valid_report()
    with pytest.raises(TypeError, match="cohort"):
        ReliabilityReport(  # type: ignore[arg-type]
            report.indicator,
            object(),
            report.ratio,
            report.slo_evaluation,
            report.error_budget,
        )
    with pytest.raises(ValueError, match="cohort indicator"):
        ReliabilityReport(
            report.indicator,
            ReliabilityCohort("other", None, None),
            report.ratio,
            report.slo_evaluation,
            report.error_budget,
        )
    with pytest.raises(TypeError, match="ratio"):
        ReliabilityReport(  # type: ignore[arg-type]
            report.indicator,
            report.cohort,
            object(),
            report.slo_evaluation,
            report.error_budget,
        )
    with pytest.raises(ValueError, match="non-empty"):
        ReliabilityReport(
            report.indicator,
            None,
            report.ratio,
            report.slo_evaluation,
            report.error_budget,
        )


def test_report_rejects_inconsistent_composed_m1_values() -> None:
    report = _valid_report()
    empty_ratio = compute_ratio([], unknown_policy=UnknownPolicy.EXCLUDE)
    other_ratio = compute_ratio(
        [EvaluationOutcome.FAIL], unknown_policy=UnknownPolicy.EXCLUDE
    )
    other_slo = Slo("other", Fraction(1, 2), ObjectiveDirection.AT_LEAST)

    with pytest.raises(ValueError, match="empty report"):
        ReliabilityReport(
            report.indicator,
            report.cohort,
            empty_ratio,
            evaluate_slo(report.slo_evaluation.slo, empty_ratio),
            compute_error_budget(report.slo_evaluation.slo, empty_ratio),
        )
    with pytest.raises(TypeError, match="slo_evaluation"):
        ReliabilityReport(  # type: ignore[arg-type]
            report.indicator,
            report.cohort,
            report.ratio,
            object(),
            report.error_budget,
        )
    with pytest.raises(ValueError, match="report ratio"):
        ReliabilityReport(
            report.indicator,
            report.cohort,
            report.ratio,
            evaluate_slo(report.slo_evaluation.slo, other_ratio),
            report.error_budget,
        )
    with pytest.raises(TypeError, match="error_budget"):
        ReliabilityReport(  # type: ignore[arg-type]
            report.indicator,
            report.cohort,
            report.ratio,
            report.slo_evaluation,
            object(),
        )
    with pytest.raises(ValueError, match="report ratio"):
        ReliabilityReport(
            report.indicator,
            report.cohort,
            report.ratio,
            report.slo_evaluation,
            compute_error_budget(report.slo_evaluation.slo, other_ratio),
        )
    mismatched_budget = compute_error_budget(other_slo, report.ratio)
    assert isinstance(mismatched_budget, ErrorBudget)
    with pytest.raises(ValueError, match="same SLO"):
        ReliabilityReport(
            report.indicator,
            report.cohort,
            report.ratio,
            report.slo_evaluation,
            mismatched_budget,
        )


def test_report_rejects_invalid_burn_rate_composition() -> None:
    report = _valid_report()
    with pytest.raises(TypeError, match="burn_rate"):
        ReliabilityReport(  # type: ignore[arg-type]
            report.indicator,
            report.cohort,
            report.ratio,
            report.slo_evaluation,
            report.error_budget,
            object(),
        )
    other_slo = Slo("other", Fraction(1, 2), ObjectiveDirection.AT_LEAST)
    wrong_slo_burn = compute_burn_rate(other_slo, report.ratio)
    assert isinstance(wrong_slo_burn, BurnRate)
    with pytest.raises(ValueError, match="same SLO"):
        ReliabilityReport(
            report.indicator,
            report.cohort,
            report.ratio,
            report.slo_evaluation,
            report.error_budget,
            wrong_slo_burn,
        )
    other_policy_ratio = compute_ratio(
        [EvaluationOutcome.PASS], unknown_policy=UnknownPolicy.TREAT_AS_BAD
    )
    wrong_policy_burn = compute_burn_rate(report.slo_evaluation.slo, other_policy_ratio)
    with pytest.raises(ValueError, match="UNKNOWN policy"):
        ReliabilityReport(
            report.indicator,
            report.cohort,
            report.ratio,
            report.slo_evaluation,
            report.error_budget,
            wrong_policy_burn,
        )

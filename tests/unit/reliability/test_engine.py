from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction

import pytest

from agent_reliability.domain import (
    BudgetStatus,
    EvaluationOutcome,
    ObjectiveDirection,
    Slo,
    SloStatus,
    UnknownPolicy,
    compute_burn_rate,
    compute_error_budget,
    compute_ratio,
    evaluate_slo,
)
from agent_reliability.evaluation import (
    EvaluationExecutionFailure,
    EvaluationFailureStage,
    EvaluationProvenance,
    EvaluatorIdentity,
)
from agent_reliability.reliability import (
    AggregationConflict,
    AggregationConflictReason,
    ReliabilityObservation,
    ReliabilityReport,
    evaluate_reliability,
)


def _slo(target: Fraction = Fraction(99, 100)) -> Slo:
    return Slo("task-success", target, ObjectiveDirection.AT_LEAST)


def _observation(
    outcome: EvaluationOutcome,
    *,
    indicator: str = "task_success",
    name: str = "exact-check",
    version: str = "v1",
    configuration_id: str | None = "strict",
    deterministic: bool = True,
    manual: bool = False,
) -> ReliabilityObservation:
    provenance = None
    if not manual:
        provenance = EvaluationProvenance(
            identity=EvaluatorIdentity(name, version, configuration_id),
            evaluated_at=datetime(2026, 1, 1, tzinfo=UTC),
            deterministic=deterministic,
        )
    return ReliabilityObservation(indicator, outcome, provenance)


def _evaluate(
    observations: object, **kwargs: object
) -> ReliabilityReport | AggregationConflict:
    return evaluate_reliability(
        indicator="task_success",
        observations=observations,  # type: ignore[arg-type]
        slo=kwargs.pop("slo", _slo()),  # type: ignore[arg-type]
        unknown_policy=kwargs.pop("unknown_policy", UnknownPolicy.EXCLUDE),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


def test_clean_cohort_delegates_all_math_to_m1() -> None:
    observations = [
        *[_observation(EvaluationOutcome.PASS) for _ in range(990)],
        *[_observation(EvaluationOutcome.FAIL) for _ in range(10)],
    ]
    report = _evaluate(observations)
    assert isinstance(report, ReliabilityReport)
    outcomes = [observation.outcome for observation in observations]
    expected_ratio = compute_ratio(outcomes, unknown_policy=UnknownPolicy.EXCLUDE)
    assert report.ratio == expected_ratio
    assert report.slo_evaluation == evaluate_slo(_slo(), expected_ratio)
    assert report.error_budget == compute_error_budget(_slo(), expected_ratio)
    assert report.ratio.pass_ratio == Fraction(99, 100)
    assert report.slo_evaluation.status is SloStatus.MET


@pytest.mark.parametrize(
    ("policy", "considered_pass", "considered_fail", "ratio"),
    [
        (UnknownPolicy.EXCLUDE, 90, 5, Fraction(18, 19)),
        (UnknownPolicy.TREAT_AS_BAD, 90, 10, Fraction(9, 10)),
        (UnknownPolicy.TREAT_AS_GOOD, 95, 5, Fraction(19, 20)),
    ],
)
def test_unknown_policy_matrix(
    policy: UnknownPolicy,
    considered_pass: int,
    considered_fail: int,
    ratio: Fraction,
) -> None:
    observations = [
        *[_observation(EvaluationOutcome.PASS) for _ in range(90)],
        *[_observation(EvaluationOutcome.FAIL) for _ in range(5)],
        *[_observation(EvaluationOutcome.UNKNOWN) for _ in range(5)],
    ]
    report = _evaluate(observations, unknown_policy=policy)
    assert isinstance(report, ReliabilityReport)
    assert report.ratio.considered_pass_count == considered_pass
    assert report.ratio.considered_fail_count == considered_fail
    assert report.ratio.pass_ratio == ratio


def test_empty_collection_preserves_no_data_semantics() -> None:
    report = _evaluate([])
    assert isinstance(report, ReliabilityReport)
    assert report.cohort is None
    assert report.ratio.pass_ratio is None
    assert report.ratio.fail_ratio is None
    assert report.slo_evaluation.status is SloStatus.UNKNOWN
    assert report.error_budget.status is BudgetStatus.NO_DATA


def test_one_unknown_is_not_empty_under_treat_as_bad() -> None:
    report = _evaluate(
        [_observation(EvaluationOutcome.UNKNOWN)],
        unknown_policy=UnknownPolicy.TREAT_AS_BAD,
    )
    assert isinstance(report, ReliabilityReport)
    assert report.ratio.fail_ratio == 1
    assert report.error_budget.observed_bad_events == 1


@pytest.mark.parametrize(
    ("changed", "reason"),
    [
        ({"name": "rule-check"}, AggregationConflictReason.EVALUATOR_NAME_MISMATCH),
        ({"version": "v2"}, AggregationConflictReason.EVALUATOR_VERSION_MISMATCH),
        (
            {"configuration_id": "relaxed"},
            AggregationConflictReason.CONFIGURATION_ID_MISMATCH,
        ),
        ({"deterministic": False}, AggregationConflictReason.DETERMINISM_MISMATCH),
    ],
)
def test_evaluator_provenance_conflicts(
    changed: dict[str, object], reason: AggregationConflictReason
) -> None:
    second = {
        "name": "exact-check",
        "version": "v1",
        "configuration_id": "strict",
        "deterministic": True,
        **changed,
    }
    result = _evaluate(
        [
            _observation(EvaluationOutcome.PASS),
            _observation(EvaluationOutcome.FAIL, **second),
        ]
    )
    assert isinstance(result, AggregationConflict)
    assert reason in result.reasons
    assert not hasattr(result, "ratio")


def test_all_conflict_reasons_are_order_independent() -> None:
    observations = [
        _observation(EvaluationOutcome.PASS),
        _observation(
            EvaluationOutcome.FAIL,
            name="other",
            version="v2",
            configuration_id=None,
            deterministic=False,
        ),
    ]
    forward = _evaluate(observations)
    backward = _evaluate(reversed(observations))
    assert forward == backward
    assert isinstance(forward, AggregationConflict)
    assert forward.reasons == frozenset(
        {
            AggregationConflictReason.EVALUATOR_NAME_MISMATCH,
            AggregationConflictReason.EVALUATOR_VERSION_MISMATCH,
            AggregationConflictReason.CONFIGURATION_ID_MISMATCH,
            AggregationConflictReason.DETERMINISM_MISMATCH,
        }
    )


def test_different_indicator_conflicts() -> None:
    result = _evaluate([_observation(EvaluationOutcome.PASS, indicator="other")])
    assert result == AggregationConflict(
        frozenset({AggregationConflictReason.INDICATOR_MISMATCH})
    )


def test_manual_observations_aggregate_but_mixed_source_conflicts() -> None:
    manual = [
        _observation(EvaluationOutcome.PASS, manual=True),
        _observation(EvaluationOutcome.FAIL, manual=True),
    ]
    report = _evaluate(manual)
    assert isinstance(report, ReliabilityReport)
    assert report.cohort is not None
    assert report.cohort.evaluator_identity is None

    mixed = _evaluate([manual[0], _observation(EvaluationOutcome.PASS)])
    assert mixed == AggregationConflict(
        frozenset({AggregationConflictReason.MANUAL_EVALUATED_MIX})
    )


def test_explicit_lookback_uses_m1_burn_rate() -> None:
    full = [_observation(EvaluationOutcome.PASS) for _ in range(100)]
    lookback = [
        *[_observation(EvaluationOutcome.PASS) for _ in range(97)],
        *[_observation(EvaluationOutcome.FAIL) for _ in range(3)],
    ]
    report = _evaluate(full, burn_rate_lookback=lookback)
    assert isinstance(report, ReliabilityReport)
    expected = compute_ratio(
        (observation.outcome for observation in lookback),
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    assert report.burn_rate == compute_burn_rate(_slo(), expected)
    assert report.burn_rate.value == 3


def test_empty_lookback_is_explicit_no_data() -> None:
    report = _evaluate([_observation(EvaluationOutcome.PASS)], burn_rate_lookback=[])
    assert isinstance(report, ReliabilityReport)
    assert report.burn_rate is not None
    assert report.burn_rate.status is BudgetStatus.NO_DATA


def test_absent_lookback_produces_no_burn_rate() -> None:
    report = _evaluate([_observation(EvaluationOutcome.PASS)])
    assert isinstance(report, ReliabilityReport)
    assert report.burn_rate is None


def test_cross_window_cohort_mismatch_conflicts() -> None:
    result = _evaluate(
        [_observation(EvaluationOutcome.PASS, version="v1")],
        burn_rate_lookback=[_observation(EvaluationOutcome.FAIL, version="v2")],
    )
    assert result == AggregationConflict(
        frozenset({AggregationConflictReason.WINDOW_COHORT_MISMATCH})
    )


def test_internally_conflicting_lookback_produces_no_report() -> None:
    result = _evaluate(
        [_observation(EvaluationOutcome.PASS)],
        burn_rate_lookback=[
            _observation(EvaluationOutcome.PASS, version="v1"),
            _observation(EvaluationOutcome.PASS, version="v2"),
        ],
    )
    assert isinstance(result, AggregationConflict)
    assert AggregationConflictReason.EVALUATOR_VERSION_MISMATCH in result.reasons


def test_nonempty_lookback_cannot_attach_to_empty_full_window() -> None:
    result = _evaluate([], burn_rate_lookback=[_observation(EvaluationOutcome.PASS)])
    assert isinstance(result, AggregationConflict)


def test_zero_tolerance_states_are_preserved() -> None:
    slo = _slo(Fraction(1))
    intact = _evaluate([_observation(EvaluationOutcome.PASS)], slo=slo)
    exceeded = _evaluate([_observation(EvaluationOutcome.FAIL)], slo=slo)
    assert isinstance(intact, ReliabilityReport)
    assert intact.error_budget.status is BudgetStatus.ZERO_TOLERANCE_INTACT
    assert intact.error_budget.consumption_ratio == 0
    assert isinstance(exceeded, ReliabilityReport)
    assert exceeded.error_budget.status is BudgetStatus.ZERO_TOLERANCE_EXCEEDED
    assert exceeded.error_budget.consumption_ratio is None


def test_single_pass_generator_is_consumed_once() -> None:
    calls = 0

    def observations():
        nonlocal calls
        calls += 1
        yield _observation(EvaluationOutcome.PASS)

    report = _evaluate(observations())
    assert isinstance(report, ReliabilityReport)
    assert calls == 1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"indicator": 1}, "indicator"),
        ({"observations": 1}, "observations"),
        ({"slo": object()}, "slo"),
        ({"unknown_policy": None}, "unknown_policy"),
        ({"burn_rate_lookback": 1}, "burn_rate_lookback"),
    ],
)
def test_invalid_direct_arguments_raise(
    kwargs: dict[str, object], message: str
) -> None:
    arguments: dict[str, object] = {
        "indicator": "task_success",
        "observations": [],
        "slo": _slo(),
        "unknown_policy": UnknownPolicy.EXCLUDE,
        **kwargs,
    }
    with pytest.raises((TypeError, ValueError), match=message):
        evaluate_reliability(**arguments)  # type: ignore[arg-type]


def test_unexpected_iterable_member_raises_without_rendering_it() -> None:
    secret = "customer-secret"

    class Unexpected:
        def __repr__(self) -> str:
            return secret

    with pytest.raises(TypeError) as caught:
        _evaluate([Unexpected()])
    assert secret not in str(caught.value)


def test_evaluation_execution_failure_cannot_enter_counts() -> None:
    failure = EvaluationExecutionFailure(
        identity=EvaluatorIdentity("exact-check", "v1"),
        stage=EvaluationFailureStage.EVALUATION,
        exception_type="RuntimeError",
    )
    with pytest.raises(TypeError, match="ReliabilityObservation"):
        _evaluate([failure])


def test_at_most_direction_is_delegated_to_m1() -> None:
    slo = Slo("hallucination", Fraction(1, 100), ObjectiveDirection.AT_MOST)
    observations = [
        *[_observation(EvaluationOutcome.PASS) for _ in range(99)],
        _observation(EvaluationOutcome.FAIL),
    ]
    report = _evaluate(observations, slo=slo)
    assert isinstance(report, ReliabilityReport)
    assert report.slo_evaluation.status is SloStatus.MET

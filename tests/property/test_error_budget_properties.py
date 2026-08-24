"""Property-based tests for SLO evaluation, error budget, and burn rate
(agent_reliability.domain.slo / error_budget).
"""

from __future__ import annotations

from fractions import Fraction

from hypothesis import given
from hypothesis import strategies as st

from agent_reliability.domain import (
    BudgetStatus,
    ObjectiveDirection,
    RatioResult,
    Slo,
    SloStatus,
    UnknownPolicy,
    compute_burn_rate,
    compute_error_budget,
    evaluate_slo,
)

small_counts = st.integers(min_value=0, max_value=500)
targets = st.integers(min_value=0, max_value=1000).map(lambda n: Fraction(n, 1000))
directions = st.sampled_from(list(ObjectiveDirection))


def _slo(target: Fraction, direction: ObjectiveDirection) -> Slo:
    return Slo(name="x", target=target, direction=direction)


def _ratio(pass_count: int, fail_count: int) -> RatioResult:
    return RatioResult(
        pass_count=pass_count,
        fail_count=fail_count,
        unknown_count=0,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )


@given(
    target=targets,
    direction=directions,
    pass_count=small_counts,
    fail_count=small_counts,
)
def test_evaluate_slo_status_matches_direct_direction_comparison(
    target: Fraction, direction: ObjectiveDirection, pass_count: int, fail_count: int
) -> None:
    """Cross-check the unified fail_ratio<=allowed_bad_fraction comparison
    against the "naive" per-direction comparison it is meant to be
    equivalent to (see ADR-0002)."""
    slo = _slo(target, direction)
    ratio = _ratio(pass_count, fail_count)
    result = evaluate_slo(slo, ratio)

    if ratio.pass_ratio is None:
        assert result.status is SloStatus.UNKNOWN
        return

    if direction is ObjectiveDirection.AT_LEAST:
        expected_met = ratio.pass_ratio >= target
    else:
        expected_met = ratio.fail_ratio is not None and ratio.fail_ratio <= target  # type: ignore[operator]

    assert (result.status is SloStatus.MET) == expected_met


@given(
    target=targets,
    direction=directions,
    pass_count=small_counts,
    fail_count=small_counts,
)
def test_error_budget_consumption_ratio_is_never_negative(
    target: Fraction, direction: ObjectiveDirection, pass_count: int, fail_count: int
) -> None:
    slo = _slo(target, direction)
    ratio = _ratio(pass_count, fail_count)
    budget = compute_error_budget(slo, ratio)
    if budget.consumption_ratio is not None:
        assert budget.consumption_ratio >= 0


@given(
    target=targets,
    direction=directions,
    pass_count=small_counts,
    fail_count=st.integers(min_value=1, max_value=500),
)
def test_remaining_budget_does_not_increase_as_failures_increase(
    target: Fraction, direction: ObjectiveDirection, pass_count: int, fail_count: int
) -> None:
    slo = _slo(target, direction)
    before = compute_error_budget(slo, _ratio(pass_count, fail_count))
    after = compute_error_budget(slo, _ratio(pass_count, fail_count + 1))

    if before.remaining_fraction is None or after.remaining_fraction is None:
        return
    assert after.remaining_fraction <= before.remaining_fraction


@given(
    target=targets,
    direction=directions,
    pass_count=small_counts,
    fail_count=small_counts,
)
def test_full_window_burn_rate_equals_error_budget_consumption_ratio(
    target: Fraction, direction: ObjectiveDirection, pass_count: int, fail_count: int
) -> None:
    slo = _slo(target, direction)
    ratio = _ratio(pass_count, fail_count)
    budget = compute_error_budget(slo, ratio)
    burn = compute_burn_rate(slo, ratio)
    assert budget.status == burn.status
    assert budget.consumption_ratio == burn.value


@given(
    target=targets,
    direction=directions,
    pass_count=small_counts,
    fail_count=small_counts,
)
def test_status_is_no_data_iff_considered_count_is_zero(
    target: Fraction, direction: ObjectiveDirection, pass_count: int, fail_count: int
) -> None:
    slo = _slo(target, direction)
    ratio = _ratio(pass_count, fail_count)
    budget = compute_error_budget(slo, ratio)
    assert (budget.status is BudgetStatus.NO_DATA) == (ratio.considered_count == 0)


@given(
    target=targets,
    direction=directions,
    pass_count=small_counts,
    fail_count=small_counts,
)
def test_identical_input_produces_identical_output(
    target: Fraction, direction: ObjectiveDirection, pass_count: int, fail_count: int
) -> None:
    slo = _slo(target, direction)
    ratio = _ratio(pass_count, fail_count)
    assert compute_error_budget(slo, ratio) == compute_error_budget(slo, ratio)
    assert compute_burn_rate(slo, ratio) == compute_burn_rate(slo, ratio)

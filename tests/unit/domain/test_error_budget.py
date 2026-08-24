from __future__ import annotations

from fractions import Fraction

from agent_reliability.domain import (
    BudgetStatus,
    ObjectiveDirection,
    RatioResult,
    Slo,
    UnknownPolicy,
    compute_burn_rate,
    compute_error_budget,
)


def _ratio(
    pass_count: int,
    fail_count: int,
    unknown_count: int = 0,
    policy: UnknownPolicy = UnknownPolicy.EXCLUDE,
) -> RatioResult:
    return RatioResult(
        pass_count=pass_count,
        fail_count=fail_count,
        unknown_count=unknown_count,
        unknown_policy=policy,
    )


class TestErrorBudgetGoldenExample:
    """docs/SLO_SEMANTICS.md worked example: target 99.5%, TREAT_AS_BAD,
    9,920 PASS / 50 FAIL / 30 UNKNOWN -> allowed=50 events, observed=80
    events, consumption_ratio=1.60, remaining_fraction=-0.60."""

    SLO = Slo(
        name="task_success",
        target=Fraction(995, 1000),
        direction=ObjectiveDirection.AT_LEAST,
    )

    def test_matches_documented_numbers_exactly(self) -> None:
        ratio = _ratio(9_920, 50, 30, UnknownPolicy.TREAT_AS_BAD)
        budget = compute_error_budget(self.SLO, ratio)

        assert budget.status is BudgetStatus.MEASURED
        assert budget.allowed_bad_fraction == Fraction(5, 1000)
        assert budget.allowed_bad_events == Fraction(50)
        assert budget.observed_bad_events == 80
        assert budget.consumption_ratio == Fraction(8, 5)  # 1.60
        assert budget.remaining_fraction == Fraction(-3, 5)  # -0.60


class TestBurnRateGoldenExample:
    """docs/SLO_SEMANTICS.md worked example: 30-day window at 99.5%,
    lookback of 200 runs with 3 bad events -> burn rate 3.0."""

    SLO = Slo(
        name="task_success",
        target=Fraction(995, 1000),
        direction=ObjectiveDirection.AT_LEAST,
    )

    def test_matches_documented_burn_rate(self) -> None:
        lookback = _ratio(pass_count=197, fail_count=3)
        burn = compute_burn_rate(self.SLO, lookback)
        assert burn.status is BudgetStatus.MEASURED
        assert burn.value == Fraction(3)


class TestNonIntegralAllowedBadEvents:
    def test_999_considered_events_half_percent_allowance(self) -> None:
        slo = Slo(
            name="x", target=Fraction(995, 1000), direction=ObjectiveDirection.AT_LEAST
        )
        ratio = _ratio(pass_count=999, fail_count=0)
        budget = compute_error_budget(slo, ratio)
        # 0.005 * 999 = 4.995, kept exact, not rounded.
        assert budget.allowed_bad_events == Fraction(4995, 1000)
        assert budget.allowed_bad_events == Fraction(999, 200)


class TestNoData:
    SLO = Slo(
        name="x", target=Fraction(995, 1000), direction=ObjectiveDirection.AT_LEAST
    )

    def test_error_budget_no_data(self) -> None:
        budget = compute_error_budget(self.SLO, _ratio(0, 0))
        assert budget.status is BudgetStatus.NO_DATA
        assert budget.consumption_ratio is None
        assert budget.remaining_fraction is None
        assert budget.observed_bad_events == 0  # a real, defined count of zero

    def test_burn_rate_no_data(self) -> None:
        burn = compute_burn_rate(self.SLO, _ratio(0, 0))
        assert burn.status is BudgetStatus.NO_DATA
        assert burn.value is None


class TestZeroToleranceAtLeast:
    SLO = Slo(name="x", target=Fraction(1), direction=ObjectiveDirection.AT_LEAST)

    def test_intact_with_zero_failures(self) -> None:
        ratio = _ratio(pass_count=1_000, fail_count=0)
        budget = compute_error_budget(self.SLO, ratio)
        assert budget.status is BudgetStatus.ZERO_TOLERANCE_INTACT
        assert budget.consumption_ratio == Fraction(0)
        assert budget.remaining_fraction == Fraction(1)

        burn = compute_burn_rate(self.SLO, ratio)
        assert burn.status is BudgetStatus.ZERO_TOLERANCE_INTACT
        assert burn.value == Fraction(0)

    def test_exceeded_by_a_single_failure(self) -> None:
        ratio = _ratio(pass_count=999, fail_count=1)
        budget = compute_error_budget(self.SLO, ratio)
        assert budget.status is BudgetStatus.ZERO_TOLERANCE_EXCEEDED
        assert budget.consumption_ratio is None
        assert budget.remaining_fraction is None
        assert budget.observed_bad_events == 1  # the count itself is still known

        burn = compute_burn_rate(self.SLO, ratio)
        assert burn.status is BudgetStatus.ZERO_TOLERANCE_EXCEEDED
        assert burn.value is None


class TestZeroToleranceAtMost:
    SLO = Slo(name="y", target=Fraction(0), direction=ObjectiveDirection.AT_MOST)

    def test_intact_with_zero_failures(self) -> None:
        ratio = _ratio(pass_count=1_000, fail_count=0)
        budget = compute_error_budget(self.SLO, ratio)
        assert budget.status is BudgetStatus.ZERO_TOLERANCE_INTACT
        assert budget.remaining_fraction == Fraction(1)

    def test_exceeded_by_a_single_failure(self) -> None:
        ratio = _ratio(pass_count=999, fail_count=1)
        budget = compute_error_budget(self.SLO, ratio)
        assert budget.status is BudgetStatus.ZERO_TOLERANCE_EXCEEDED
        assert budget.remaining_fraction is None


class TestErrorBudgetAndBurnRateAreTheSameFormula:
    def test_full_window_burn_rate_equals_error_budget_consumption_ratio(self) -> None:
        slo = Slo(
            name="x", target=Fraction(99, 100), direction=ObjectiveDirection.AT_LEAST
        )
        ratio = _ratio(pass_count=950, fail_count=50)
        budget = compute_error_budget(slo, ratio)
        burn = compute_burn_rate(slo, ratio)
        assert budget.consumption_ratio == burn.value

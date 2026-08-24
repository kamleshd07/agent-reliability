from __future__ import annotations

from fractions import Fraction

import pytest

from agent_reliability.domain import (
    ObjectiveDirection,
    RatioResult,
    Slo,
    SloStatus,
    UnknownPolicy,
    evaluate_slo,
)


def _ratio(pass_count: int, fail_count: int, unknown_count: int = 0) -> RatioResult:
    return RatioResult(
        pass_count=pass_count,
        fail_count=fail_count,
        unknown_count=unknown_count,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )


class TestSloConstruction:
    def test_valid_at_least(self) -> None:
        slo = Slo(
            name="task_success",
            target=Fraction(995, 1000),
            direction=ObjectiveDirection.AT_LEAST,
        )
        assert slo.allowed_bad_fraction == Fraction(5, 1000)

    def test_valid_at_most(self) -> None:
        slo = Slo(
            name="hallucination_rate",
            target=Fraction(1, 1000),
            direction=ObjectiveDirection.AT_MOST,
        )
        assert slo.allowed_bad_fraction == Fraction(1, 1000)

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            Slo(name="", target=Fraction(1, 2), direction=ObjectiveDirection.AT_LEAST)

    def test_rejects_float_target(self) -> None:
        with pytest.raises(TypeError, match="Fraction"):
            Slo(name="x", target=0.995, direction=ObjectiveDirection.AT_LEAST)  # type: ignore[arg-type]

    @pytest.mark.parametrize("target", [Fraction(-1, 100), Fraction(101, 100)])
    def test_rejects_target_outside_unit_interval(self, target: Fraction) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            Slo(name="x", target=target, direction=ObjectiveDirection.AT_LEAST)

    def test_target_zero_and_one_are_valid(self) -> None:
        Slo(name="x", target=Fraction(0), direction=ObjectiveDirection.AT_LEAST)
        Slo(name="y", target=Fraction(1), direction=ObjectiveDirection.AT_LEAST)

    def test_rejects_non_direction(self) -> None:
        with pytest.raises(TypeError, match="ObjectiveDirection"):
            Slo(name="x", target=Fraction(1, 2), direction="at_least")  # type: ignore[arg-type]


class TestEvaluateSloAtLeast:
    SLO = Slo(
        name="task_success",
        target=Fraction(995, 1000),
        direction=ObjectiveDirection.AT_LEAST,
    )

    def test_above_target_is_met(self) -> None:
        ratio = _ratio(pass_count=999, fail_count=1)  # 99.9% >= 99.5%
        assert evaluate_slo(self.SLO, ratio).status is SloStatus.MET

    def test_below_target_is_breached(self) -> None:
        ratio = _ratio(pass_count=98, fail_count=2)  # 98% < 99.5%
        assert evaluate_slo(self.SLO, ratio).status is SloStatus.BREACHED

    def test_exactly_at_target_is_met_inclusive_boundary(self) -> None:
        ratio = _ratio(pass_count=995, fail_count=5)  # exactly 99.5%
        assert ratio.pass_ratio == self.SLO.target
        assert evaluate_slo(self.SLO, ratio).status is SloStatus.MET

    def test_no_data_is_unknown(self) -> None:
        ratio = _ratio(pass_count=0, fail_count=0)
        assert evaluate_slo(self.SLO, ratio).status is SloStatus.UNKNOWN


class TestEvaluateSloAtMost:
    SLO = Slo(
        name="hallucination_rate",
        target=Fraction(1, 1000),
        direction=ObjectiveDirection.AT_MOST,
    )

    def test_below_target_is_met(self) -> None:
        # PASS means "no hallucination"; FAIL means "hallucination detected".
        ratio = _ratio(pass_count=9_999, fail_count=1)  # 0.01% <= 0.1%
        assert evaluate_slo(self.SLO, ratio).status is SloStatus.MET

    def test_above_target_is_breached(self) -> None:
        ratio = _ratio(pass_count=990, fail_count=10)  # 1% > 0.1%
        assert evaluate_slo(self.SLO, ratio).status is SloStatus.BREACHED

    def test_exactly_at_target_is_met_inclusive_boundary(self) -> None:
        ratio = _ratio(pass_count=999, fail_count=1)  # exactly 0.1%
        assert ratio.fail_ratio == self.SLO.target
        assert evaluate_slo(self.SLO, ratio).status is SloStatus.MET

    def test_no_data_is_unknown(self) -> None:
        ratio = _ratio(pass_count=0, fail_count=0)
        assert evaluate_slo(self.SLO, ratio).status is SloStatus.UNKNOWN


class TestHundredPercentSlo:
    AT_LEAST_100 = Slo(
        name="x", target=Fraction(1), direction=ObjectiveDirection.AT_LEAST
    )
    AT_MOST_0 = Slo(name="y", target=Fraction(0), direction=ObjectiveDirection.AT_MOST)

    def test_at_least_100_met_with_zero_failures(self) -> None:
        ratio = _ratio(pass_count=1_000, fail_count=0)
        assert evaluate_slo(self.AT_LEAST_100, ratio).status is SloStatus.MET

    def test_at_least_100_breached_by_a_single_failure(self) -> None:
        ratio = _ratio(pass_count=999, fail_count=1)
        assert evaluate_slo(self.AT_LEAST_100, ratio).status is SloStatus.BREACHED

    def test_at_most_0_met_with_zero_failures(self) -> None:
        ratio = _ratio(pass_count=1_000, fail_count=0)
        assert evaluate_slo(self.AT_MOST_0, ratio).status is SloStatus.MET

    def test_at_most_0_breached_by_a_single_failure(self) -> None:
        ratio = _ratio(pass_count=999, fail_count=1)
        assert evaluate_slo(self.AT_MOST_0, ratio).status is SloStatus.BREACHED

from __future__ import annotations

from fractions import Fraction

import pytest

from agent_reliability.domain import (
    EvaluationOutcome,
    ObservationCounts,
    RatioResult,
    UnknownPolicy,
    compute_ratio,
)


class TestObservationCounts:
    def test_from_outcomes_streams_and_aggregates(self) -> None:
        outcomes = [
            EvaluationOutcome.PASS,
            EvaluationOutcome.PASS,
            EvaluationOutcome.FAIL,
            EvaluationOutcome.UNKNOWN,
        ]
        counts = ObservationCounts.from_outcomes(iter(outcomes))
        assert counts == ObservationCounts(pass_count=2, fail_count=1, unknown_count=1)
        assert counts.total_count == 4

    def test_from_outcomes_empty(self) -> None:
        counts = ObservationCounts.from_outcomes([])
        assert counts.total_count == 0

    def test_rejects_negative_counts(self) -> None:
        with pytest.raises(ValueError, match="fail_count"):
            ObservationCounts(pass_count=1, fail_count=-1, unknown_count=0)

    def test_rejects_non_int_counts(self) -> None:
        with pytest.raises(TypeError):
            ObservationCounts(pass_count=1.5, fail_count=0, unknown_count=0)  # type: ignore[arg-type]

    def test_rejects_bool_as_count(self) -> None:
        # bool is a subclass of int in Python; explicitly rejected as a count.
        with pytest.raises(TypeError):
            ObservationCounts(pass_count=True, fail_count=0, unknown_count=0)  # type: ignore[arg-type]


class TestRatioResultUnknownPolicyGoldenExample:
    """Golden example from docs/SLO_SEMANTICS.md: 9,920 PASS, 50 FAIL,
    30 UNKNOWN, under each of the three UnknownPolicy values."""

    PASS_COUNT = 9_920
    FAIL_COUNT = 50
    UNKNOWN_COUNT = 30

    def _ratio(self, policy: UnknownPolicy) -> RatioResult:
        return RatioResult(
            pass_count=self.PASS_COUNT,
            fail_count=self.FAIL_COUNT,
            unknown_count=self.UNKNOWN_COUNT,
            unknown_policy=policy,
        )

    def test_exclude(self) -> None:
        ratio = self._ratio(UnknownPolicy.EXCLUDE)
        assert ratio.considered_count == 9_970
        assert ratio.pass_ratio == Fraction(9_920, 9_970)
        assert float(ratio.pass_ratio) == pytest.approx(0.99498, abs=1e-5)

    def test_treat_as_bad(self) -> None:
        ratio = self._ratio(UnknownPolicy.TREAT_AS_BAD)
        assert ratio.considered_count == 10_000
        assert ratio.considered_fail_count == 80
        assert ratio.pass_ratio == Fraction(9_920, 10_000)
        assert ratio.pass_ratio == Fraction(248, 250)

    def test_treat_as_good(self) -> None:
        ratio = self._ratio(UnknownPolicy.TREAT_AS_GOOD)
        assert ratio.considered_count == 10_000
        assert ratio.considered_pass_count == 9_950
        assert ratio.pass_ratio == Fraction(9_950, 10_000)
        assert ratio.pass_ratio == Fraction(199, 200)

    def test_the_three_policies_disagree_on_identical_raw_data(self) -> None:
        exclude = self._ratio(UnknownPolicy.EXCLUDE).pass_ratio
        treat_bad = self._ratio(UnknownPolicy.TREAT_AS_BAD).pass_ratio
        treat_good = self._ratio(UnknownPolicy.TREAT_AS_GOOD).pass_ratio
        assert len({exclude, treat_bad, treat_good}) == 3


class TestRatioResultZeroDenominator:
    def test_no_observations_is_undefined_not_zero_or_one(self) -> None:
        ratio = RatioResult(
            pass_count=0,
            fail_count=0,
            unknown_count=0,
            unknown_policy=UnknownPolicy.EXCLUDE,
        )
        assert ratio.pass_ratio is None
        assert ratio.fail_ratio is None
        assert ratio.considered_count == 0

    def test_all_unknown_under_exclude_is_undefined(self) -> None:
        ratio = RatioResult(
            pass_count=0,
            fail_count=0,
            unknown_count=5,
            unknown_policy=UnknownPolicy.EXCLUDE,
        )
        assert ratio.pass_ratio is None
        assert ratio.fail_ratio is None

    def test_all_unknown_under_treat_as_bad_is_defined_as_zero(self) -> None:
        ratio = RatioResult(
            pass_count=0,
            fail_count=0,
            unknown_count=5,
            unknown_policy=UnknownPolicy.TREAT_AS_BAD,
        )
        assert ratio.pass_ratio == Fraction(0)
        assert ratio.fail_ratio == Fraction(1)

    def test_all_unknown_under_treat_as_good_is_defined_as_one(self) -> None:
        ratio = RatioResult(
            pass_count=0,
            fail_count=0,
            unknown_count=5,
            unknown_policy=UnknownPolicy.TREAT_AS_GOOD,
        )
        assert ratio.pass_ratio == Fraction(1)
        assert ratio.fail_ratio == Fraction(0)


class TestRatioResultBoundaries:
    def test_single_pass(self) -> None:
        ratio = RatioResult(
            pass_count=1,
            fail_count=0,
            unknown_count=0,
            unknown_policy=UnknownPolicy.EXCLUDE,
        )
        assert ratio.pass_ratio == Fraction(1)

    def test_single_fail(self) -> None:
        ratio = RatioResult(
            pass_count=0,
            fail_count=1,
            unknown_count=0,
            unknown_policy=UnknownPolicy.EXCLUDE,
        )
        assert ratio.pass_ratio == Fraction(0)

    def test_single_unknown_under_exclude(self) -> None:
        ratio = RatioResult(
            pass_count=0,
            fail_count=0,
            unknown_count=1,
            unknown_policy=UnknownPolicy.EXCLUDE,
        )
        assert ratio.pass_ratio is None

    def test_very_large_counts_stay_exact(self) -> None:
        big = 10**12
        ratio = RatioResult(
            pass_count=big - 1,
            fail_count=1,
            unknown_count=0,
            unknown_policy=UnknownPolicy.EXCLUDE,
        )
        assert ratio.pass_ratio == Fraction(big - 1, big)

    def test_pass_and_fail_ratio_are_exact_complements_when_defined(self) -> None:
        ratio = RatioResult(
            pass_count=7,
            fail_count=3,
            unknown_count=0,
            unknown_policy=UnknownPolicy.EXCLUDE,
        )
        assert ratio.pass_ratio is not None
        assert ratio.fail_ratio is not None
        assert ratio.pass_ratio + ratio.fail_ratio == Fraction(1)

    def test_rejects_non_unknown_policy(self) -> None:
        with pytest.raises(TypeError):
            RatioResult(
                pass_count=1, fail_count=0, unknown_count=0, unknown_policy="exclude"
            )  # type: ignore[arg-type]

    def test_rejects_negative_count(self) -> None:
        with pytest.raises(ValueError, match="fail_count"):
            RatioResult(
                pass_count=1,
                fail_count=-1,
                unknown_count=0,
                unknown_policy=UnknownPolicy.EXCLUDE,
            )

    def test_rejects_non_int_count(self) -> None:
        with pytest.raises(TypeError, match="pass_count"):
            RatioResult(
                pass_count=1.5,  # type: ignore[arg-type]
                fail_count=0,
                unknown_count=0,
                unknown_policy=UnknownPolicy.EXCLUDE,
            )

    def test_rejects_bool_as_count(self) -> None:
        with pytest.raises(TypeError, match="unknown_count"):
            RatioResult(
                pass_count=1,
                fail_count=0,
                unknown_count=True,  # type: ignore[arg-type]
                unknown_policy=UnknownPolicy.EXCLUDE,
            )


class TestComputeRatio:
    def test_matches_direct_ratio_result_construction(self) -> None:
        outcomes = [EvaluationOutcome.PASS] * 9_920
        outcomes += [EvaluationOutcome.FAIL] * 50
        outcomes += [EvaluationOutcome.UNKNOWN] * 30
        via_compute = compute_ratio(outcomes, unknown_policy=UnknownPolicy.TREAT_AS_BAD)
        via_direct = RatioResult(
            pass_count=9_920,
            fail_count=50,
            unknown_count=30,
            unknown_policy=UnknownPolicy.TREAT_AS_BAD,
        )
        assert via_compute == via_direct

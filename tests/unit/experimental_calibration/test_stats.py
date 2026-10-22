"""Statistics: exact intervals, explicit undefined values, no silent division."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from agent_reliability.experimental.calibration import Proportion, Undefined
from agent_reliability.experimental.calibration._stats import (
    clopper_pearson,
    cohen_kappa,
    f1,
    mean,
    wilson,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("k", "n", "lower", "upper"),
    [  # exact binomial (independently computed by summing the binomial CDF)
        (0, 150, 0.0, 0.0243),
        (1, 150, 0.0002, 0.0366),
        (2, 150, 0.0016, 0.0473),
        (3, 150, 0.0041, 0.0573),
        (0, 400, 0.0, 0.0092),
        (7, 400, 0.0071, 0.0357),
        (0, 30, 0.0, 0.1157),
        (75, 150, 0.4174, 0.5826),
        (150, 150, 0.9757, 1.0),
    ],
)
def test_clopper_pearson_matches_independent_exact_values(
    k: int, n: int, lower: float, upper: float
) -> None:
    got = clopper_pearson(k, n)
    assert got is not None
    assert got[0] == pytest.approx(lower, abs=5e-5)
    assert got[1] == pytest.approx(upper, abs=5e-5)


def test_zero_trials_have_no_interval_and_a_zero_denominator_proportion_is_undefined() -> (
    None
):
    assert clopper_pearson(0, 0) is None
    assert wilson(0, 0) is None
    p = Proportion(0, 0)
    assert p.value == Undefined("zero_denominator")
    document = p.as_json()
    assert document["value"] is None
    assert document["undefined_reason"] == "zero_denominator"
    assert document["wilson_95"] is None and document["clopper_pearson_95"] is None


def test_invalid_counts_are_rejected() -> None:
    for bad in ((2, 1), (-1, 5), (0, -1)):
        with pytest.raises(ValueError):
            Proportion(*bad)
    with pytest.raises(ValueError):
        clopper_pearson(5, 3)
    with pytest.raises(ValueError):
        Undefined("because")


def _binomial_cdf(k: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


@given(
    st.integers(min_value=1, max_value=120).flatmap(
        lambda n: st.tuples(st.integers(min_value=0, max_value=n), st.just(n))
    )
)
def test_intervals_are_ordered_contain_the_estimate_and_satisfy_the_exact_equations(
    pair: tuple[int, int],
) -> None:
    k, n = pair
    lo, hi = clopper_pearson(k, n)  # type: ignore[misc]
    wl, wh = wilson(k, n)  # type: ignore[misc]
    assert 0.0 <= lo <= k / n <= hi <= 1.0
    assert 0.0 <= wl <= wh <= 1.0
    # Defining equations of the exact interval (independent binomial sums).
    if k < n:
        assert _binomial_cdf(k, n, hi) == pytest.approx(0.025, abs=1e-7)
    if k > 0:
        assert 1 - _binomial_cdf(k - 1, n, lo) == pytest.approx(0.025, abs=1e-7)


@given(st.integers(min_value=2, max_value=300), st.data())
def test_cp_upper_bound_is_monotone_in_the_error_count(
    n: int, data: st.DataObject
) -> None:
    k = data.draw(st.integers(min_value=0, max_value=n - 1))
    a = clopper_pearson(k, n)
    b = clopper_pearson(k + 1, n)
    assert a is not None and b is not None
    assert a[1] <= b[1] + 1e-12 and a[0] <= b[0] + 1e-12


def test_f1_is_zero_not_undefined_when_the_judge_is_always_wrong() -> None:
    assert f1(0, 3, 2) == 0.0
    assert f1(0, 0, 0) == Undefined("zero_denominator")
    assert f1(5, 0, 0) == 1.0
    assert f1(2, 1, 1) == pytest.approx(2 / 3)


def test_kappa_is_explicit_about_what_it_cannot_compute() -> None:
    cats = ("PASS", "FAIL", "UNKNOWN")
    assert cohen_kappa([], cats) == Undefined("no_judgments")
    assert cohen_kappa([("PASS", "PASS")] * 4, cats) == Undefined("single_class")
    perfect = [("PASS", "PASS"), ("FAIL", "FAIL"), ("PASS", "PASS"), ("FAIL", "FAIL")]
    assert cohen_kappa(perfect, cats) == pytest.approx(1.0)
    flipped = [("PASS", "FAIL"), ("FAIL", "PASS")] * 2
    assert cohen_kappa(flipped, cats) == pytest.approx(-1.0)


def test_mean_of_nothing_is_undefined() -> None:
    assert mean([]) == Undefined("zero_denominator")
    assert mean([0.5, 1.0]) == 0.75


def test_results_are_finite_and_deterministic() -> None:
    first = Proportion(7, 400).as_json()
    assert first == Proportion(7, 400).as_json()
    for value in (first["value"], *first["wilson_95"], *first["clopper_pearson_95"]):
        assert math.isfinite(value)

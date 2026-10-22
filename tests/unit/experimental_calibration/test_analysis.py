# ruff: noqa: E501 -- long assertion and data lines are kept readable.
"""Repeatability and judge-vs-judge disagreement: separate conditions, never merged."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_reliability.experimental.calibration import (
    DISAGREEMENT_CATEGORIES,
    Split,
    compare_judges,
    repeatability,
)
from tests.fakes.p29_calibration import case_doc, fingerprint, load, table

pytestmark = pytest.mark.unit


def _cases(tmp_path: Path, labels: dict[str, str]):  # type: ignore[no-untyped-def]
    docs = [case_doc(i, label) for i, label in labels.items()]
    return load(tmp_path, {"heldout": docs}).cases(Split.HELDOUT)


# ------------------------------------------------------------------ repeatability


def test_stable_and_unstable_cases_are_counted_with_flip_kinds(tmp_path: Path) -> None:
    cases = _cases(tmp_path, {"a": "pass", "b": "pass", "c": "fail", "d": "fail"})
    t = table(
        {
            "a": ["PASS", "PASS", "PASS"],
            "b": ["PASS", "FAIL", "PASS"],  # pass<->fail flip
            "c": ["FAIL", "UNKNOWN"],  # flip involving UNKNOWN
            "d": ["FAIL", "FAIL"],
        }
    )
    r = repeatability(cases, t)
    assert (r["cases_compared"], r["unstable"]) == (4, 2)
    assert r["flip_kinds"] == {"pass_fail": 1, "involving_unknown": 1}
    assert r["repetitions"] == 3
    assert r["excluded_for_failures"] == 0
    assert r["unstable_rate"]["numerator"] == 2


def test_failed_runs_are_excluded_but_counted_and_the_worst_case_treats_them_as_unstable(
    tmp_path: Path,
) -> None:
    cases = _cases(tmp_path, {"a": "pass", "b": "pass", "c": "pass"})
    t = table(
        {
            "a": ["PASS", "PASS"],
            "b": ["PASS", "FAILURE"],  # only one usable run: cannot be compared
            "c": ["FAILURE", "FAILURE", "PASS"],  # one usable run
        }
    )
    r = repeatability(cases, t)
    assert (r["cases_compared"], r["unstable"], r["excluded_for_failures"]) == (1, 0, 2)
    worst = r["unstable_rate_worst_case"]
    assert (worst["numerator"], worst["denominator"]) == (2, 3)


def test_a_failure_among_three_runs_does_not_hide_a_real_flip(tmp_path: Path) -> None:
    cases = _cases(tmp_path, {"a": "pass"})
    r = repeatability(cases, table({"a": ["PASS", "FAIL", "FAILURE"]}))
    assert (r["cases_compared"], r["unstable"]) == (1, 1)


def test_single_run_data_has_no_repeatability_and_says_so(tmp_path: Path) -> None:
    cases = _cases(tmp_path, {"a": "pass"})
    r = repeatability(cases, table({"a": "PASS"}))
    assert r["cases_compared"] == 0
    assert r["unstable_rate"]["undefined_reason"] == "zero_denominator"
    assert r["mean_pairwise_agreement"]["undefined_reason"] == "zero_denominator"


def test_indeterminate_cases_are_not_part_of_repeatability(tmp_path: Path) -> None:
    cases = _cases(tmp_path, {"a": "unknown"})
    assert repeatability(cases, table({"a": ["PASS", "FAIL"]}))["cases_compared"] == 0


def test_repeatability_warns_that_identical_calls_prove_little(tmp_path: Path) -> None:
    cases = _cases(tmp_path, {"a": "pass"})
    assert (
        "independent" in repeatability(cases, table({"a": ["PASS", "PASS"]}))["caveat"]
    )


# ---------------------------------------------------------------- compare_judges


def test_every_example_lands_in_exactly_one_ordered_category(tmp_path: Path) -> None:
    cases = _cases(
        tmp_path,
        {"agree": "pass", "dis": "pass", "mis": "fail", "bothu": "pass",
         "fail": "pass", "miss": "pass", "amb": "unknown", "both_wrong": "fail"},
    )  # fmt: skip
    a = table(
        {"agree": "PASS", "dis": "PASS", "mis": "FAIL", "bothu": "UNKNOWN",
         "fail": "FAILURE", "miss": "MISSING", "amb": "PASS", "both_wrong": "PASS"},
        fp=fingerprint("local-a"),
    )  # fmt: skip
    b = table(
        {"agree": "PASS", "dis": "FAIL", "mis": "UNKNOWN", "bothu": "UNKNOWN",
         "fail": "PASS", "miss": "PASS", "amb": "FAIL", "both_wrong": "PASS"},
        fp=fingerprint("local-b"),
    )  # fmt: skip
    report = compare_judges(cases, a, b)
    categories = report["categories"]
    assert set(categories) == set(DISAGREEMENT_CATEGORIES)
    assert categories == {
        "missing": 1, "evaluation_failure": 1, "indeterminate_ground_truth": 1,
        "judgment_disagreement": 1, "abstention_mismatch": 1, "both_abstain": 1,
        "agreement": 2,
    }  # fmt: skip
    assert sum(categories.values()) == len(cases)
    assert "disagreement_rate" not in report  # deliberately no combined rate
    assert report["shared_errors"] == 1  # both_wrong: equal wrong commits
    assert report["differing_components"]


def test_rates_have_their_own_denominators(tmp_path: Path) -> None:
    cases = _cases(tmp_path, {"a": "pass", "b": "pass", "c": "fail", "d": "fail"})
    first = table(
        {"a": "PASS", "b": "PASS", "c": "FAIL", "d": "UNKNOWN"}, fp=fingerprint("x1")
    )
    second = table(
        {"a": "FAIL", "b": "PASS", "c": "FAIL", "d": "FAIL"}, fp=fingerprint("x2")
    )
    report = compare_judges(cases, first, second)
    jd = report["judgment_disagreement_rate"]
    assert (jd["numerator"], jd["denominator"]) == (
        1,
        3,
    )  # a differs; d excluded (UNKNOWN)
    am = report["abstention_mismatch_rate"]
    assert (am["numerator"], am["denominator"]) == (1, 4)


def test_agreement_is_reported_beside_correctness_not_instead_of_it(
    tmp_path: Path,
) -> None:
    cases = _cases(tmp_path, {"a": "pass", "b": "fail"})
    wrong = {"a": "FAIL", "b": "PASS"}
    report = compare_judges(
        cases, table(wrong, fp=fingerprint("w1")), table(wrong, fp=fingerprint("w2"))
    )
    assert report["agreement_raw"]["value"] == 1.0  # they agree...
    assert (
        report["correct_against_human"]["first"]["value"] == 0.0
    )  # ...and are both wrong
    assert report["shared_errors"] == 2


def test_comparing_equivalent_fingerprints_is_refused(tmp_path: Path) -> None:
    cases = _cases(tmp_path, {"a": "pass"})
    t = table({"a": "PASS"})
    with pytest.raises(ValueError, match="repeatability"):
        compare_judges(cases, t, table({"a": "PASS"}))

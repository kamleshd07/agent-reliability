# ruff: noqa: E501 -- long assertion and data lines are kept readable.
"""Metrics are hand-computed; undefined values are explicit; strata stay separate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_reliability.experimental.calibration import Split, split_metrics
from tests.fakes.p29_calibration import case_doc, fingerprint, load, table

pytestmark = pytest.mark.unit


def _metrics(
    tmp_path: Path, docs: list[dict[str, Any]], outcomes: dict[str, Any]
) -> dict[str, Any]:
    ds = load(tmp_path, {"heldout": docs})
    return split_metrics(ds.cases(Split.HELDOUT), table(outcomes))


def _value(block: dict[str, Any]) -> float | None:
    return block["value"]


def _hand_example(tmp_path: Path) -> dict[str, Any]:
    docs = [case_doc(f"f{i}", "fail") for i in range(6)] + [
        case_doc(f"p{i}", "pass") for i in range(6)
    ]
    outcomes = {
        "f0": "FAIL", "f1": "FAIL", "f2": "FAIL", "f3": "PASS",
        "f4": "UNKNOWN", "f5": "FAILURE",
        "p0": "PASS", "p1": "PASS", "p2": "PASS", "p3": "FAIL",
        "p4": "UNKNOWN", "p5": "MISSING",
    }  # fmt: skip
    return _metrics(tmp_path, docs, outcomes)


def test_every_figure_matches_a_hand_computed_confusion(tmp_path: Path) -> None:
    head = _hand_example(tmp_path)["headline"]
    c, r = head["counts"], head["rates"]
    assert (c["tp"], c["fn"], c["fp"], c["tn"]) == (3, 1, 1, 3)
    assert (c["answered"], c["abstained"], c["failed"], c["missing"]) == (8, 2, 1, 1)
    assert (
        c["answered"] + c["abstained"] + c["failed"] + c["missing"]
        == head["n_labelled"]
    )
    assert (c["support_fail"], c["support_pass"], c["judged"]) == (6, 6, 10)
    expected = {
        "verdict_rate": (10, 12), "committed_coverage": (8, 12), "abstention_rate": (2, 10),
        "failure_rate": (1, 12), "missing_rate": (1, 12), "accuracy_conditional": (6, 8),
        "accuracy_effective": (6, 12), "fnr_conditional": (1, 4), "fnr_effective": (3, 6),
        "fpr_conditional": (1, 4), "fpr_effective": (1, 6), "precision_fail": (3, 4),
        "precision_pass": (3, 4), "recall_fail": (3, 4), "recall_pass": (3, 4),
    }  # fmt: skip
    for name, (num, den) in expected.items():
        assert (r[name]["numerator"], r[name]["denominator"]) == (num, den), name
    assert head["f1"]["fail"]["value"] == pytest.approx(0.75)
    assert head["f1"]["pass"]["value"] == pytest.approx(0.75)
    assert head["agreement_with_human"]["judged_pairs"] == 10
    assert head["agreement_with_human"]["kappa"]["value"] == pytest.approx(
        1 / 3, abs=1e-6
    )


def test_effective_miss_rate_is_never_below_the_conditional_one(tmp_path: Path) -> None:
    r = _hand_example(tmp_path)["headline"]["rates"]
    assert _value(r["fnr_effective"]) >= _value(r["fnr_conditional"])
    assert _value(r["recall_fail"]) == pytest.approx(1 - _value(r["fnr_conditional"]))


def test_perfect_judge(tmp_path: Path) -> None:
    docs = [case_doc(f"f{i}", "fail") for i in range(5)] + [
        case_doc(f"p{i}", "pass") for i in range(5)
    ]
    outcomes = {
        d["case_id"]: ("FAIL" if d["human_label"] == "fail" else "PASS") for d in docs
    }
    head = _metrics(tmp_path, docs, outcomes)["headline"]
    r = head["rates"]
    assert _value(r["accuracy_conditional"]) == 1.0 == _value(r["accuracy_effective"])
    assert _value(r["fnr_effective"]) == 0.0 == _value(r["fpr_conditional"])
    assert head["f1"]["fail"]["value"] == 1.0
    assert head["agreement_with_human"]["kappa"]["value"] == pytest.approx(1.0)


def test_always_wrong_judge_has_zero_f1_not_undefined(tmp_path: Path) -> None:
    docs = [case_doc(f"f{i}", "fail") for i in range(4)] + [
        case_doc(f"p{i}", "pass") for i in range(4)
    ]
    outcomes = {
        d["case_id"]: ("PASS" if d["human_label"] == "fail" else "FAIL") for d in docs
    }
    head = _metrics(tmp_path, docs, outcomes)["headline"]
    assert head["f1"]["fail"]["value"] == 0.0 and head["f1"]["pass"]["value"] == 0.0
    assert _value(head["rates"]["accuracy_conditional"]) == 0.0
    assert _value(head["rates"]["fnr_effective"]) == 1.0
    assert head["agreement_with_human"]["kappa"]["value"] == pytest.approx(-1.0)


def test_always_unknown_judge_has_full_verdict_rate_but_zero_committed_coverage(
    tmp_path: Path,
) -> None:
    docs = [case_doc(f"f{i}", "fail") for i in range(4)] + [
        case_doc(f"p{i}", "pass") for i in range(4)
    ]
    outcomes = {d["case_id"]: "UNKNOWN" for d in docs}
    head = _metrics(tmp_path, docs, outcomes)["headline"]
    r = head["rates"]
    assert _value(r["verdict_rate"]) == 1.0
    assert _value(r["committed_coverage"]) == 0.0
    assert _value(r["abstention_rate"]) == 1.0
    # Every defect was "not flagged": the SLO-relevant miss rate is 100%.
    assert _value(r["fnr_effective"]) == 1.0
    # Conditional metrics have no committed calls: explicitly undefined.
    assert r["fnr_conditional"]["undefined_reason"] == "zero_denominator"
    assert r["precision_fail"]["undefined_reason"] == "zero_denominator"
    assert head["f1"]["fail"]["undefined_reason"] == "zero_denominator"
    assert head["agreement_with_human"]["judged_pairs"] == 8  # all UNKNOWN verdicts


def test_single_class_dataset_marks_the_missing_class_undefined(tmp_path: Path) -> None:
    docs = [case_doc(f"p{i}", "pass") for i in range(5)]
    outcomes = {d["case_id"]: "PASS" for d in docs}
    head = _metrics(tmp_path, docs, outcomes)["headline"]
    r = head["rates"]
    assert head["counts"]["support_fail"] == 0
    assert r["fnr_effective"]["undefined_reason"] == "zero_denominator"
    assert r["recall_fail"]["undefined_reason"] == "zero_denominator"
    assert _value(r["fpr_conditional"]) == 0.0
    assert head["agreement_with_human"]["kappa"]["undefined_reason"] == "single_class"


def test_empty_split_yields_only_explicit_undefined_values(tmp_path: Path) -> None:
    ds = load(tmp_path, {"heldout": [case_doc("a")]})
    metrics = split_metrics((), table({}))
    head = metrics["headline"]
    assert head["n_labelled"] == 0
    for block in head["rates"].values():
        assert (
            block["value"] is None and block["undefined_reason"] == "zero_denominator"
        )
    assert ds is not None


def test_missing_and_failed_are_distinct_from_each_other_and_from_abstention(
    tmp_path: Path,
) -> None:
    docs = [case_doc(f"f{i}", "fail") for i in range(4)] + [
        case_doc(f"p{i}", "pass") for i in range(2)
    ]
    outcomes = {
        "f0": "FAILURE",
        "f1": "MISSING",
        "f2": "UNKNOWN",
        "f3": "FAIL",
        "p0": "PASS",
        "p1": "PASS",
    }
    c = _metrics(tmp_path, docs, outcomes)["headline"]["counts"]
    assert (c["failed"], c["missing"], c["abstained"], c["tp"]) == (1, 1, 1, 1)
    assert (c["fail_failed"], c["fail_missing"], c["fail_abstained"]) == (1, 1, 1)


def test_indeterminate_cases_are_excluded_from_accuracy_and_reported_separately(
    tmp_path: Path,
) -> None:
    docs = [
        case_doc("f0", "fail"),
        case_doc("p0", "pass"),
        case_doc("u0", "unknown"),
        case_doc("u1", "unknown"),
        case_doc(
            "x0",
            "unknown",
            provenance="human_adjudicated",
            labels=[("r1", "pass"), ("r2", "fail")],
            adjudication="unresolved",
        ),
    ]
    ds = load(tmp_path, {"heldout": docs}, provenance={"heldout": "synthetic"})
    outcomes = {"f0": "FAIL", "p0": "PASS", "u0": "PASS", "u1": "UNKNOWN", "x0": "FAIL"}
    head = split_metrics(ds.cases(Split.HELDOUT), table(outcomes))["headline"]
    assert head["n_labelled"] == 2
    assert _value(head["rates"]["accuracy_conditional"]) == 1.0
    ind = head["indeterminate"]
    assert ind["n"] == 3
    assert (
        ind["indeterminate_fraction"]["numerator"],
        ind["indeterminate_fraction"]["denominator"],
    ) == (3, 5)
    assert ind["commit_rate_on_indeterminate"]["numerator"] == 2  # u0 and x0 committed
    assert ind["abstention_rate_on_indeterminate"]["numerator"] == 1


def test_strata_are_separate_and_borderline_is_reported_but_not_pooled(
    tmp_path: Path,
) -> None:
    docs = [
        case_doc("c1", "fail", difficulty="clear"),
        case_doc("m1", "pass", difficulty="ambiguous"),
        case_doc("b1", "fail", difficulty="borderline"),
        case_doc("a1", "fail", difficulty="adversarial"),
    ]
    outcomes = {"c1": "FAIL", "m1": "PASS", "b1": "PASS", "a1": "PASS"}
    metrics = _metrics(tmp_path, docs, outcomes)
    assert metrics["headline"]["n_labelled"] == 2  # clear + ambiguous only
    assert metrics["borderline"] == "reported_only"
    assert metrics["strata"]["borderline"]["counts"]["fn"] == 1
    assert metrics["strata"]["adversarial"]["counts"]["fn"] == 1
    assert metrics["headline"]["counts"]["fn"] == 0
    assert metrics["run_index_used"] == 0


def test_runs_other_than_index_zero_cannot_be_selected(tmp_path: Path) -> None:
    ds = load(tmp_path, {"heldout": [case_doc("a")]})
    with pytest.raises(ValueError, match="run index 0"):
        split_metrics(ds.cases(Split.HELDOUT), table({"a": "PASS"}), run_index=1)


def test_run_zero_is_used_even_when_later_runs_differ(tmp_path: Path) -> None:
    ds = load(tmp_path, {"heldout": [case_doc("a", "pass")]})
    metrics = split_metrics(
        ds.cases(Split.HELDOUT), table({"a": ["FAIL", "PASS", "PASS"]})
    )
    assert metrics["headline"]["counts"]["fp"] == 1
    assert metrics["runs_available"] == 3


def test_confidence_is_only_summarised_by_the_declared_level(tmp_path: Path) -> None:
    docs = [case_doc("a", "pass"), case_doc("b", "fail")]
    head = _metrics(tmp_path, docs, {"a": "PASS", "b": "PASS"})["headline"]
    by_level = head["accuracy_by_declared_confidence"]
    assert (by_level["high"]["numerator"], by_level["high"]["denominator"]) == (1, 2)
    assert by_level["low"]["undefined_reason"] == "zero_denominator"
    flat = str(head)
    for forbidden in ("brier", "ece", "calibration_curve", "probability"):
        assert forbidden not in flat.lower()


def test_fingerprint_helper_is_stable() -> None:
    assert fingerprint().behaviour_digest == fingerprint().behaviour_digest

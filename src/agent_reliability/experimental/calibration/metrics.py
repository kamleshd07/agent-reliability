"""Calibration metrics over a labelled evaluation set (normative: ARCHITECTURE 4.x)."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations
from typing import Any, Final

from agent_reliability.experimental.calibration._stats import (
    Proportion,
    Undefined,
    cohen_kappa,
    f1,
    mean,
)
from agent_reliability.experimental.calibration.dataset import ReferenceCase
from agent_reliability.experimental.calibration.judgments import JudgmentTable, Outcome

__all__ = [
    "DIFFICULTIES",
    "HEADLINE",
    "inter_labeler_agreement",
    "slice_metrics",
    "split_metrics",
]

HEADLINE: Final = ("clear", "ambiguous")
DIFFICULTIES: Final = ("clear", "ambiguous", "borderline", "adversarial")
_CATEGORIES: Final = ("PASS", "FAIL", "UNKNOWN")


def _num(value: float | Undefined) -> dict[str, Any]:
    if isinstance(value, Undefined):
        return value.as_json()
    return {"value": round(value, 6)}


def slice_metrics(
    cases: Sequence[ReferenceCase], table: JudgmentTable, run_index: int
) -> dict[str, Any]:
    """Metrics for one slice. ``E`` = determinate, resolved labels; ``I`` = the rest."""
    labelled = [c for c in cases if not c.indeterminate]
    indeterminate = [c for c in cases if c.indeterminate]

    tp = fn = fp = tn = 0
    fail_abstained = pass_abstained = 0
    fail_failed = pass_failed = 0
    fail_missing = pass_missing = 0
    support_fail = support_pass = 0
    pairs: list[tuple[str, str]] = []
    confidence_total = dict.fromkeys(("high", "medium", "low"), 0)
    confidence_correct = dict.fromkeys(("high", "medium", "low"), 0)
    for case in labelled:
        outcome = table.outcome(case.case_id, run_index)
        is_fail = case.human_label == "fail"
        if is_fail:
            support_fail += 1
        else:
            support_pass += 1
        if outcome is Outcome.PASS:
            fn += is_fail
            tn += not is_fail
        elif outcome is Outcome.FAIL:
            tp += is_fail
            fp += not is_fail
        elif outcome is Outcome.UNKNOWN:
            fail_abstained += is_fail
            pass_abstained += not is_fail
        elif outcome is Outcome.FAILURE:
            fail_failed += is_fail
            pass_failed += not is_fail
        else:
            fail_missing += is_fail
            pass_missing += not is_fail
        if outcome.is_verdict:
            pairs.append((case.human_label.upper(), outcome.value))
        if outcome.is_committed:
            row = table.row(case.case_id, run_index)
            level = None if row is None else row.confidence_level
            if level is not None:
                confidence_total[level] += 1
                correct = (outcome is Outcome.FAIL) == is_fail
                confidence_correct[level] += correct

    total = len(labelled)
    answered = tp + fn + fp + tn
    abstained = fail_abstained + pass_abstained
    judged = answered + abstained
    failed = fail_failed + pass_failed
    missing = fail_missing + pass_missing
    pass_judged_committed = tn + fp
    fail_judged_committed = tp + fn

    ind_total = len(indeterminate)
    ind_answered = ind_abstained = 0
    for case in indeterminate:
        outcome = table.outcome(case.case_id, run_index)
        ind_answered += outcome.is_committed
        ind_abstained += outcome is Outcome.UNKNOWN

    return {
        "n_labelled": total,
        "counts": {
            "tp": tp,
            "fn": fn,
            "fp": fp,
            "tn": tn,
            "answered": answered,
            "abstained": abstained,
            "failed": failed,
            "missing": missing,
            "judged": judged,
            "support_fail": support_fail,
            "support_pass": support_pass,
            "fail_abstained": fail_abstained,
            "pass_abstained": pass_abstained,
            "fail_failed": fail_failed,
            "pass_failed": pass_failed,
            "fail_missing": fail_missing,
            "pass_missing": pass_missing,
        },
        "rates": {
            "verdict_rate": Proportion(judged, total).as_json(),
            "committed_coverage": Proportion(answered, total).as_json(),
            "abstention_rate": Proportion(abstained, judged).as_json(),
            "failure_rate": Proportion(failed, total).as_json(),
            "missing_rate": Proportion(missing, total).as_json(),
            "accuracy_conditional": Proportion(tp + tn, answered).as_json(),
            "accuracy_effective": Proportion(tp + tn, total).as_json(),
            "fnr_conditional": Proportion(fn, fail_judged_committed).as_json(),
            "fnr_effective": Proportion(support_fail - tp, support_fail).as_json(),
            "fpr_conditional": Proportion(fp, pass_judged_committed).as_json(),
            "fpr_effective": Proportion(fp, support_pass).as_json(),
            "precision_fail": Proportion(tp, tp + fp).as_json(),
            "precision_pass": Proportion(tn, tn + fn).as_json(),
            "recall_fail": Proportion(tp, tp + fn).as_json(),
            "recall_pass": Proportion(tn, tn + fp).as_json(),
        },
        "f1": {"fail": _num(f1(tp, fp, fn)), "pass": _num(f1(tn, fn, fp))},
        "agreement_with_human": {
            "judged_pairs": len(pairs),
            "raw": Proportion(sum(1 for a, b in pairs if a == b), len(pairs)).as_json(),
            "kappa": _num(cohen_kappa(pairs, _CATEGORIES)),
            "note": "agreement is not correctness",
        },
        "accuracy_by_declared_confidence": {
            level: Proportion(
                confidence_correct[level], confidence_total[level]
            ).as_json()
            for level in ("high", "medium", "low")
        },
        "indeterminate": {
            "n": ind_total,
            "indeterminate_fraction": Proportion(
                ind_total, total + ind_total
            ).as_json(),
            "commit_rate_on_indeterminate": Proportion(
                ind_answered, ind_total
            ).as_json(),
            "abstention_rate_on_indeterminate": Proportion(
                ind_abstained, ind_total
            ).as_json(),
            "note": "human indecision is not truth; a commit is not an error",
        },
    }


def inter_labeler_agreement(cases: Sequence[ReferenceCase]) -> dict[str, Any]:
    """Mean pairwise agreement over cases with at least two labeler entries."""
    per_case: list[float] = []
    for case in cases:
        labels = [label for _, label in case.labels]
        if len(labels) >= 2:
            pairs = list(combinations(labels, 2))
            per_case.append(sum(1 for a, b in pairs if a == b) / len(pairs))
    result = mean(per_case)
    return {
        "cases_with_two_or_more_labelers": len(per_case),
        "mean_pairwise_agreement": _num(result),
    }


def split_metrics(
    cases: Sequence[ReferenceCase], table: JudgmentTable, run_index: int = 0
) -> dict[str, Any]:
    """Headline (clear + ambiguous), every difficulty stratum, labelers.

    ``borderline`` is reported but assessed by no criterion; ``adversarial`` is the
    stratum for the defect-pass count criterion.
    """
    if run_index != 0:
        raise ValueError("assessments use run index 0 (no run selection)")
    by_difficulty = {d: [c for c in cases if c.difficulty == d] for d in DIFFICULTIES}
    headline = [c for c in cases if c.difficulty in HEADLINE]
    return {
        "run_index_used": run_index,
        "runs_available": table.runs_available,
        "headline": slice_metrics(headline, table, run_index),
        "strata": {
            d: slice_metrics(group, table, run_index)
            for d, group in by_difficulty.items()
        },
        "borderline": "reported_only",
        "inter_labeler_agreement": inter_labeler_agreement(cases),
    }

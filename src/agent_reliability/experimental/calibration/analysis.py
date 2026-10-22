"""Repeatability of one judge configuration and disagreement between two."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations
from typing import Any, Final

from agent_reliability.experimental.calibration._stats import (
    Proportion,
    Undefined,
    cohen_kappa,
    mean,
)
from agent_reliability.experimental.calibration.dataset import ReferenceCase
from agent_reliability.experimental.calibration.judgments import JudgmentTable, Outcome

__all__ = ["DISAGREEMENT_CATEGORIES", "compare_judges", "repeatability"]

DISAGREEMENT_CATEGORIES: Final = (
    "missing",
    "evaluation_failure",
    "indeterminate_ground_truth",
    "judgment_disagreement",
    "abstention_mismatch",
    "both_abstain",
    "agreement",
)


def repeatability(
    cases: Sequence[ReferenceCase], table: JudgmentTable
) -> dict[str, Any]:
    """Run-to-run stability of ONE fingerprint over the labelled (determinate) cases.

    Failed runs are excluded from the stability comparison but counted, and a
    worst-case rate treats every case that lost its comparison to failures as
    unstable. Identical requests to a caching or deterministic provider are
    trivially stable: stability is only informative if repetitions are independent.
    """
    compared = unstable = excluded = 0
    pass_fail_flips = unknown_flips = 0
    agreements: list[float] = []
    repetitions = 0
    for case in cases:
        if case.indeterminate:
            continue
        runs = table.runs(case.case_id)
        repetitions = max(repetitions, len(runs))
        if len(runs) < 2:
            continue
        usable = [r.outcome for r in runs if r.outcome.is_verdict]
        if len(usable) < 2:
            excluded += 1
            continue
        compared += 1
        distinct = set(usable)
        if len(distinct) > 1:
            unstable += 1
            if Outcome.UNKNOWN in distinct:
                unknown_flips += 1
            else:
                pass_fail_flips += 1
        pairs = list(combinations(usable, 2))
        agreements.append(sum(1 for a, b in pairs if a == b) / len(pairs))
    pairwise = mean(agreements)
    return {
        "repetitions": repetitions,
        "cases_compared": compared,
        "unstable": unstable,
        "unstable_rate": Proportion(unstable, compared).as_json(),
        "excluded_for_failures": excluded,
        "unstable_rate_worst_case": Proportion(
            unstable + excluded, compared + excluded
        ).as_json(),
        "flip_kinds": {
            "pass_fail": pass_fail_flips,
            "involving_unknown": unknown_flips,
        },
        "mean_pairwise_agreement": (
            pairwise.as_json()
            if isinstance(pairwise, Undefined)
            else {"value": round(pairwise, 6)}
        ),
        "caveat": "stability is only informative if repetitions are independent calls",
    }


def _category(case: ReferenceCase, a: Outcome, b: Outcome) -> str:
    if Outcome.MISSING in (a, b):
        return "missing"
    if Outcome.FAILURE in (a, b):
        return "evaluation_failure"
    if case.indeterminate:
        return "indeterminate_ground_truth"
    if a.is_committed and b.is_committed:
        return "judgment_disagreement" if a is not b else "agreement"
    if a is Outcome.UNKNOWN and b is Outcome.UNKNOWN:
        return "both_abstain"
    return "abstention_mismatch"


def compare_judges(
    cases: Sequence[ReferenceCase],
    first: JudgmentTable,
    second: JudgmentTable,
    run_index: int = 0,
) -> dict[str, Any]:
    """Disagreement between two judge configurations on the same examples.

    Every example lands in exactly one ordered category; there is deliberately no
    combined "disagreement rate". Agreement is never presented as correctness:
    each judge's correctness against the human label and the count of errors they
    share are reported alongside.
    """
    if first.fingerprint.equivalent_to(second.fingerprint):
        raise ValueError(
            "equivalent fingerprints: use repeatability, not a judge comparison"
        )
    counts = dict.fromkeys(DISAGREEMENT_CATEGORIES, 0)
    determinate_both_committed = determinate_both_verdict = 0
    shared_errors = 0
    correct = {"first": 0, "second": 0}
    labelled = 0
    pairs: list[tuple[str, str]] = []
    for case in cases:
        a = first.outcome(case.case_id, run_index)
        b = second.outcome(case.case_id, run_index)
        counts[_category(case, a, b)] += 1
        if a.is_verdict and b.is_verdict:
            pairs.append((a.value, b.value))
        if case.indeterminate:
            continue
        labelled += 1
        if a.is_verdict and b.is_verdict:
            determinate_both_verdict += 1
        if a.is_committed and b.is_committed:
            determinate_both_committed += 1
        truth = Outcome.FAIL if case.human_label == "fail" else Outcome.PASS
        correct["first"] += a is truth
        correct["second"] += b is truth
        if a.is_committed and a is b and a is not truth:
            shared_errors += 1
    disagreement = sum(
        1
        for case in cases
        if not case.indeterminate
        and first.outcome(case.case_id, run_index).is_committed
        and second.outcome(case.case_id, run_index).is_committed
        and first.outcome(case.case_id, run_index)
        is not second.outcome(case.case_id, run_index)
    )
    mismatch = sum(
        1
        for case in cases
        if not case.indeterminate
        and first.outcome(case.case_id, run_index).is_verdict
        and second.outcome(case.case_id, run_index).is_verdict
        and first.outcome(case.case_id, run_index).is_committed
        != second.outcome(case.case_id, run_index).is_committed
    )
    kappa = cohen_kappa(pairs, ("PASS", "FAIL", "UNKNOWN"))
    return {
        "categories": counts,
        "judgment_disagreement_rate": Proportion(
            disagreement, determinate_both_committed
        ).as_json(),
        "abstention_mismatch_rate": Proportion(
            mismatch, determinate_both_verdict
        ).as_json(),
        "agreement_raw": Proportion(
            sum(1 for x, y in pairs if x == y), len(pairs)
        ).as_json(),
        "kappa": kappa.as_json()
        if isinstance(kappa, Undefined)
        else {"value": round(kappa, 6)},
        "correct_against_human": {
            "first": Proportion(correct["first"], labelled).as_json(),
            "second": Proportion(correct["second"], labelled).as_json(),
        },
        "shared_errors": shared_errors,
        "note": "agreement is not correctness; shared_errors = equal wrong commits",
        "differing_components": list(first.fingerprint.diff(second.fingerprint)),
    }

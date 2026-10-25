# ruff: noqa: E501 -- long explanatory strings stay readable as sentences.
"""Which of the existing signals would have caught each wrong answer?

Language: Python. Replays the recording and, for every run Gentlity marks as failed,
prints what three ordinary signals say: (1) the upstream agent's own outcome (run state,
step errors, empty answer), (2) a plain assertion loop that checks that every expected
value appears verbatim in the answer, and (3) Gentlity's ``task_success``. Signal 2 is
deliberately naive: it is what a quick pytest loop would do without tolerance rules.

    python compare_baselines.py
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from smolagents_text_to_sql_evaluation import harness
else:
    from . import harness


def naive_assertion_passes(case: dict, answer: str) -> bool:
    if case["kind"] == "absent":
        return "not" in answer.casefold() or "no " in answer.casefold()
    return all(str(value).casefold() in answer.casefold() for value in case["expected"])


def main() -> None:
    data = harness.load_cases()
    runs = harness.run_cases(data["cases"], data["tolerance"], mode="replay")
    adjudication = harness.load_adjudication(harness.DEFAULT_MODEL_TAG)
    print("case  upstream-visible  naive-assertion  gentlity  adjudicated-verdict")
    naive_wrong = 0
    for run in runs:
        gentlity_fail = run.outcomes["task_success"].value != "pass"
        naive_fail = not naive_assertion_passes(run.case, run.answer)
        verdict = adjudication[run.case["id"]]["verdict"]
        really_wrong = verdict == "true_failure"
        naive_wrong += naive_fail != really_wrong
        if gentlity_fail or naive_fail or harness.upstream_visible(run):
            print(
                f"{run.case['id']:<5} {harness.upstream_visible(run)!s:<17} "
                f"{'FAIL' if naive_fail else 'pass':<16} "
                f"{'FAIL' if gentlity_fail else 'pass':<9} {verdict}"
            )
    gentlity_wrong = sum(
        (r.outcomes["task_success"].value != "pass")
        != (adjudication[r.case["id"]]["verdict"] == "true_failure")
        for r in runs
    )
    print(
        f"disagreements with the adjudicated truth: naive assertion {naive_wrong}, gentlity {gentlity_wrong}"
    )


if __name__ == "__main__":
    main()

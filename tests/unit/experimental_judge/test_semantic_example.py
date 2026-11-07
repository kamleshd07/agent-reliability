# ruff: noqa: E501 -- long strings and narrative lines read best unbroken.
"""The semantic-evaluation example: dataset invariants, offline replay of the recorded live run, quickstart."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest
from examples.semantic_shopping_evaluation.evaluate import metrics
from examples.semantic_shopping_evaluation.golden import cases

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[3]
EXPECTED = ROOT / "examples" / "semantic_shopping_evaluation" / "expected"


def test_golden_dataset_is_well_formed_and_labelled_before_any_judge_ran() -> None:
    data = cases()
    assert len({c["case_id"] for c in data}) == len(data) >= 50
    assert {c["source"] for c in data} == {"agent_run", "constructed"}
    for c in data:
        assert set(c["labels"]) == {"groundedness", "relevance"}
        assert c["labels"]["groundedness"] in (None, "pass", "fail", "unknown")
        assert c["labels"]["relevance"] in ("pass", "fail", "unknown")
    for outcome in (
        "pass",
        "fail",
        "unknown",
    ):  # every outcome is represented for both checks
        assert any(c["labels"]["groundedness"] == outcome for c in data)
        assert any(c["labels"]["relevance"] == outcome for c in data)


@pytest.mark.parametrize(
    "name", sorted(p.name for p in EXPECTED.glob("verdicts-*.json"))
)
def test_recorded_live_runs_are_consistent_with_the_dataset_and_never_count_failures_as_fail(
    name: str,
) -> None:
    run = json.loads((EXPECTED / name).read_text(encoding="utf-8"))
    labels = {c["case_id"]: c["labels"] for c in cases()}
    for row in run["rows"]:
        assert labels[row["case_id"]][row["check"]] == row["expected"]
        if row["status"] == "evaluator_failure":
            assert row["outcome"] is None and row["failure_class"]
    m = metrics(run["rows"])
    for check in m.values():
        # a failed evaluation is excluded from agreement, never scored as a disagreement or as a FAIL
        agree = check["agreement_on_judge_determinate"]
        assert (
            agree["n"]
            + check["evaluator_failures_on_human_determinate"]
            + check["judge_unknown_on_human_determinate"]
            == check["human_determinate"]
        )
    text = json.dumps(run)
    assert (
        "Rs 1,999" not in text and "kettle" not in text.lower()
    )  # verdict files carry no evaluated text


def test_quickstart_runs_offline() -> None:
    done = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "semantic_quickstart.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert done.stderr == ""
    assert (
        "determinate pass" in done.stdout
        and "determinate fail" in done.stdout
        and "authoritative=False" in done.stdout
    )

"""Resource bounds: lookups are O(1), so metrics stay linear in the table size."""

from __future__ import annotations

import time

import pytest

from agent_reliability.experimental.calibration import (
    Judgment,
    JudgmentTable,
    Outcome,
    repeatability,
    split_metrics,
)
from agent_reliability.experimental.calibration.dataset import (
    LabelProvenance,
    _parse_case,
)
from agent_reliability.experimental.judge import JudgeDimension
from tests.fakes.p29_calibration import case_doc, fingerprint

pytestmark = pytest.mark.unit


def test_metrics_over_a_large_table_run_in_linear_not_quadratic_time() -> None:
    n = 20_000
    cases = [
        _parse_case(
            case_doc(f"c{i:06d}", "fail" if i % 2 else "pass"),
            LabelProvenance.SYNTHETIC,
            JudgeDimension.ANSWER_CORRECTNESS,
        )
        for i in range(n)
    ]
    rows = tuple(
        Judgment(
            c.case_id, run, Outcome.FAIL if c.human_label == "fail" else Outcome.PASS
        )
        for c in cases
        for run in range(3)
    )
    table = JudgmentTable(fingerprint(), rows)
    start = time.perf_counter()
    split_metrics(cases, table)
    repeatability(cases, table)
    elapsed = time.perf_counter() - start
    # A linear scan per lookup would need ~1e9 row visits here (minutes); the indexed
    # table takes well under a second. The bound is deliberately generous.
    assert elapsed < 10.0
    assert table.runs_available == 3
    assert table.outcome("c000001", 2) is Outcome.FAIL


def test_duplicate_example_run_pairs_are_rejected_at_construction() -> None:
    row = Judgment("a", 0, Outcome.PASS)
    with pytest.raises(ValueError, match="duplicate"):
        JudgmentTable(fingerprint(), (row, row))

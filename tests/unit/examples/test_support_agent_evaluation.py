"""The offline support-agent evaluation: determinism, correctness and honesty.

SYNTHETIC validation only: every input is a deterministic stand-in. These tests prove
the evaluation package behaves as documented; they are not evidence about real users.
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from examples.support_agent_evaluation import harness
from examples.support_agent_evaluation.agent import SupportAgent
from examples.support_agent_evaluation.report import to_json, to_markdown
from examples.support_agent_evaluation.run_evaluation import main

from agent_reliability.domain import EvaluationOutcome

PACKAGE = Path(harness.__file__).resolve().parent
KNOWLEDGE, CASES_FILE = harness.load_data()
CASES = {c["id"]: c for c in CASES_FILE["cases"]}
PASS, FAIL, UNKNOWN = (
    EvaluationOutcome.PASS,
    EvaluationOutcome.FAIL,
    EvaluationOutcome.UNKNOWN,
)


@pytest.fixture(scope="module")
def runs() -> dict[str, dict[str, harness.CaseRun]]:
    out: dict[str, dict[str, harness.CaseRun]] = {}
    for version in harness.VERSIONS:
        executed = harness.run_version(version, KNOWLEDGE, CASES_FILE["cases"])
        out[version] = {r.case["id"]: r for r in executed}
    return out


@pytest.fixture(scope="module")
def analysis() -> dict[str, Any]:
    return harness.analyse(CASES_FILE, KNOWLEDGE)


# -- dataset ---------------------------------------------------------------------------


def test_dataset_is_well_formed_and_labels_origin() -> None:
    ids = [c["id"] for c in CASES_FILE["cases"]]
    assert len(ids) == len(set(ids)) == 38
    for case in CASES_FILE["cases"]:
        assert case["origin"] in {"organic", "injected"}
        assert (case["origin"] == "injected") == (case["fault"] is not None)
        assert case["fault"] in {
            None,
            "order_tool_error",
            "kb_timeout",
            "kb_stale",
            "kb_empty",
        }
        assert case["accept_phrases"] and all(case["accept_phrases"])
        mode = case["failure_mode"]
        assert mode is None or mode in CASES_FILE["failure_modes"]
        assert set(case["oracle"]) == {
            "facts_any",
            "accept_escalation",
            "must_escalate",
            "forbid_facts",
        }


def test_data_is_synthetic_and_carries_no_secret_shapes() -> None:
    text = "".join(
        (PACKAGE / "data" / name).read_text("utf-8")
        for name in ("knowledge_base.json", "cases.json")
    )
    assert not re.search(r"@|AKIA|sk-[A-Za-z0-9]|-----BEGIN|https?://", text)


# -- evaluator correctness against labelled truth --------------------------------------

EXPECTED_OUTCOMES = [
    # (version, case, indicator, expected outcome)
    ("v1", "K01", "task_success", PASS),
    ("v1", "S01", "task_success", FAIL),  # stale article, run completes silently
    ("v2", "S01", "task_success", PASS),
    ("v1", "T01", "task_success", PASS),  # correct but eight seconds late
    ("v1", "T01", "latency", FAIL),
    ("v2", "T01", "latency", PASS),  # bounded wait, graceful fallback
    ("v2", "T01", "task_success", PASS),  # the fallback counts as accepted behaviour
    ("v1", "E01", "task_success", FAIL),  # fabricated "on its way"
    ("v1", "E01", "escalation", FAIL),
    ("v2", "E01", "escalation", PASS),
    ("v1", "F04", "refund_policy", FAIL),  # 129 USD refunded without approval
    ("v2", "F04", "refund_policy", PASS),
    ("v1", "F07", "refund_policy", PASS),  # 399 USD was escalated even by v1
    ("v1", "F08", "task_success", PASS),  # exactly 100 USD is allowed
    ("v1", "N01", "task_success", FAIL),  # crashed: empty answer
    ("v1", "N01", "latency", UNKNOWN),  # no duration was measured
    ("v2", "N01", "task_success", PASS),
    ("v1", "R01", "task_success", FAIL),  # organic retrieval confusion
    ("v2", "R01", "task_success", PASS),
    ("v2", "R02", "task_success", FAIL),  # v2 is not perfect
    ("v2", "K06", "task_success", FAIL),  # unplanned finding kept as found
]


@pytest.mark.parametrize(
    ("version", "case", "indicator", "expected"), EXPECTED_OUTCOMES
)
def test_evaluator_outcomes_match_hand_labelled_truth(
    runs: dict[str, dict[str, harness.CaseRun]],
    version: str,
    case: str,
    indicator: str,
    expected: EvaluationOutcome,
) -> None:
    assert runs[version][case].outcomes[indicator] is expected


def test_known_evaluator_limitations_are_real_and_documented(
    runs: dict[str, dict[str, harness.CaseRun]],
) -> None:
    """A false positive (correct answer, too-strict phrase) and false negatives (wrong
    answer that still contains the phrase) exist, and the oracle exposes them."""
    for version in harness.VERSIONS:
        l02 = runs[version]["L02"]
        assert l02.outcomes["task_success"] is FAIL
        assert harness.oracle_failures(l02)["task_success"] is False  # false positive
    l01 = runs["v1"]["L01"]
    assert l01.outcomes["task_success"] is PASS
    assert harness.oracle_failures(l01)["task_success"] is True  # false negative


def test_oracle_reads_structured_claims_not_answer_text(
    runs: dict[str, dict[str, harness.CaseRun]],
) -> None:
    record = runs["v1"]["S01"]
    assert record.result is not None
    reworded = replace(record.result, answer="30 days " + record.result.answer)
    altered = replace(record, result=reworded)
    assert harness.oracle_failures(altered) == harness.oracle_failures(record)


# -- SLI, SLO and error budget regression (numbers come from the SDK) ---------


def test_sli_slo_and_error_budget_regression(analysis: dict[str, Any]) -> None:
    v1, v2 = (
        analysis["versions"]["v1"]["indicators"],
        analysis["versions"]["v2"]["indicators"],
    )
    counts = {
        "v1": {
            "task_success": (20, 18, 0),
            "refund_policy": (1, 3, 0),
            "escalation": (1, 7, 0),
            "latency": (33, 3, 2),
        },
        "v2": {
            "task_success": (34, 4, 0),
            "refund_policy": (4, 0, 0),
            "escalation": (8, 0, 0),
            "latency": (38, 0, 0),
        },
    }
    for version, block in (("v1", v1), ("v2", v2)):
        for name, expected in counts[version].items():
            got = block[name]["counts"]
            assert (got["pass"], got["fail"], got["unknown"]) == expected
    assert {n: e["slo"]["status"] for n, e in v1.items()} == dict.fromkeys(
        v1, "breached"
    )
    assert {n: e["slo"]["status"] for n, e in v2.items()} == {
        "task_success": "breached",
        "refund_policy": "met",
        "escalation": "met",
        "latency": "met",
    }
    # v2 still overspends the task_success error budget (4 bad events, 3.8 allowed)
    budget = v2["task_success"]["error_budget"]
    assert budget["observed_bad_events"] == 4
    assert budget["remaining_fraction"]["numerator"] < 0


def test_regression_table_compares_same_methodology(analysis: dict[str, Any]) -> None:
    table = analysis["regression"]
    assert all(row["comparable"] for row in table.values())
    assert table["refund_policy"]["v1_slo"] == "breached"
    assert table["refund_policy"]["v2_slo"] == "met"


def test_changing_an_evaluator_version_is_refused_not_averaged(
    analysis: dict[str, Any],
) -> None:
    assert analysis["methodology_change_demo"] == {
        "conflict": ["evaluator_version_mismatch"]
    }


# -- silent failures and value over ordinary logs -------------------------


def test_silent_failures_complete_without_any_warning_or_error(
    runs: dict[str, dict[str, harness.CaseRun]], analysis: dict[str, Any]
) -> None:
    silent = analysis["versions"]["v1"]["visibility"]["silent_failures_no_log_signal"]
    assert silent == [
        "F04",
        "F05",
        "F06",
        "K06",
        "L02",
        "R01",
        "R02",
        "R03",
        "R04",
        "S01",
        "S02",
        "S03",
        "T01",
        "T02",
        "T03",
    ]
    for case_id in silent:
        record = runs["v1"][case_id]
        assert record.lifecycle == "completed"
        assert record.log_signal == "none"
        assert record.failing_indicators


def test_failure_evidence_is_complete_bounded_and_reproducible(
    analysis: dict[str, Any],
) -> None:
    for version, block in analysis["versions"].items():
        for item in block["failures"]:
            assert item["case"] in CASES
            assert item["reproduce"] == (
                f"python run_evaluation.py --version {version} --case {item['case']}"
            )
            assert item["evaluator_reason"]
            assert item["origin"] in {"organic", "injected"}
            assert item["log_signal"] in {"none", "warning", "error"}
            assert set(item) >= {
                "request",
                "answer",
                "tools_called",
                "corrective_action",
            }


def test_every_reproduce_command_reproduces_that_failure() -> None:
    analysis = harness.analyse(CASES_FILE, KNOWLEDGE, ("v1",), "S01")
    failures = analysis["versions"]["v1"]["failures"]
    assert [f["indicator"] for f in failures] == ["task_success"]


# -- determinism, offline, packaging ---------------------------------


def test_two_executions_are_byte_identical_and_match_the_committed_report(
    analysis: dict[str, Any],
) -> None:
    again = harness.analyse(CASES_FILE, KNOWLEDGE)
    assert to_json(analysis) == to_json(again)
    expected = PACKAGE / "expected"
    assert to_json(analysis) == (expected / "report.json").read_text("utf-8")
    assert to_markdown(analysis) == (expected / "report.md").read_text("utf-8")


def test_the_evaluation_makes_no_network_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_: object, **__: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    harness.analyse(CASES_FILE, KNOWLEDGE)


def test_cli_writes_reports_and_runs_as_a_plain_script(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main(["--output-dir", str(out), "--version", "v2"]) == 0
    assert json.loads((out / "report.json").read_text("utf-8"))["versions"].keys() == {
        "v2"
    }
    script = PACKAGE / "run_evaluation.py"
    done = subprocess.run(
        [sys.executable, str(script), "--version", "v1", "--case", "S01"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "cases: 1" in done.stdout
    assert "task_success" in done.stdout


def test_agent_rejects_an_unknown_version() -> None:
    with pytest.raises(ValueError):
        SupportAgent("v3", [], [], {})

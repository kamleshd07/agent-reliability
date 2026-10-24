# ruff: noqa: E501 -- long explanatory strings stay readable as sentences.
"""Replay of the recorded smolagents run through the real upstream agent loop.

Needs the example-only dependencies in
``examples/smolagents_text_to_sql_evaluation/requirements.txt`` (smolagents, sqlalchemy).
Without them the whole module is skipped with that reason; the reference-data and
checker tests in ``test_smolagents_text_to_sql_evaluation.py`` always run.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

PACKAGE = (
    Path(__file__).resolve().parents[3]
    / "examples"
    / "smolagents_text_to_sql_evaluation"
)
DATA = json.loads((PACKAGE / "data" / "cases.json").read_text(encoding="utf-8"))
CASES = DATA["cases"]
NEEDS_AGENT_STACK = (
    "install examples/smolagents_text_to_sql_evaluation/requirements.txt"
)


smolagents = pytest.importorskip("smolagents", reason=NEEDS_AGENT_STACK)
pytest.importorskip("sqlalchemy", reason=NEEDS_AGENT_STACK)

from examples.smolagents_text_to_sql_evaluation import harness  # noqa: E402
from examples.smolagents_text_to_sql_evaluation.replay import (  # noqa: E402
    ReplayDivergence,
)
from examples.smolagents_text_to_sql_evaluation.report import (  # noqa: E402
    to_json,
    to_markdown,
)
from examples.smolagents_text_to_sql_evaluation.run_evaluation import main  # noqa: E402


@pytest.fixture(scope="module")
def analysis() -> dict[str, Any]:
    runs = harness.run_cases(CASES, DATA["tolerance"], mode="replay")
    tag = harness.DEFAULT_MODEL_TAG
    return harness.analyse(
        runs, harness.load_transcript(tag)["meta"], harness.load_adjudication(tag)
    )


def test_replay_matches_the_committed_report_byte_for_byte(
    analysis: dict[str, Any],
) -> None:
    assert to_json(analysis) == (PACKAGE / "expected" / "report.json").read_text(
        encoding="utf-8"
    )
    assert to_markdown(analysis) == (PACKAGE / "expected" / "report.md").read_text(
        encoding="utf-8"
    )


def test_recorded_smolagents_version_is_the_pinned_one(
    analysis: dict[str, Any],
) -> None:
    assert analysis["meta"]["smolagents_version"] == "1.26.0"
    assert smolagents.__version__ == "1.26.0"


def test_every_case_is_adjudicated_and_disagreements_are_explained(
    analysis: dict[str, Any],
) -> None:
    counts = analysis["summary"]["adjudication"]
    assert counts["unadjudicated"] == 0
    for case in analysis["cases"]:
        verdict = case["adjudication"]["verdict"]
        failed = case["outcomes"]["task_success"] == "fail"
        if verdict == "true_pass":
            assert not failed
        elif verdict == "true_failure":
            assert failed
        else:
            assert verdict in {"ambiguous_case", "evaluator_false_positive"} and failed


def test_silent_failures_are_the_ones_the_upstream_signals_miss(
    analysis: dict[str, Any],
) -> None:
    silent = analysis["summary"]["silent_task_failures"]
    true_failures = [
        c["case"]
        for c in analysis["cases"]
        if c["adjudication"]["verdict"] == "true_failure"
    ]
    assert set(true_failures) <= set(silent)
    for case in analysis["cases"]:
        if case["adjudication"]["verdict"] == "true_failure":
            assert case["agent_state"] == "success" and case["step_error_types"] == []


def test_replay_refuses_a_changed_conversation(monkeypatch: pytest.MonkeyPatch) -> None:
    transcript = harness.load_transcript(harness.DEFAULT_MODEL_TAG)
    transcript["cases"]["Q05"]["steps"][0]["input_fingerprint"] = "0" * 16
    monkeypatch.setattr(harness, "load_transcript", lambda tag: transcript)
    with pytest.raises(ReplayDivergence):
        harness.run_cases(
            [c for c in CASES if c["id"] == "Q05"], DATA["tolerance"], mode="replay"
        )


def test_command_line_reproduces_one_case(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--case", "Q33"]) == 0
    out = capsys.readouterr().out
    assert "task_success: 0.0%" in out
    with pytest.raises(SystemExit):
        main(["--case", "NOPE"])


def test_failed_tool_call_is_still_a_tool_call(analysis: dict[str, Any]) -> None:
    q35 = next(c for c in analysis["cases"] if c["case"] == "Q35")
    assert "sql_engine" in q35["tool_names"]
    assert "SELECT date FROM receipts WHERE receipt_id = 1" in q35["sql_queries"]
    assert q35["step_error_types"] == ["AgentToolExecutionError"]


def test_adapter_reads_native_and_text_calls_from_an_errored_step() -> None:
    native = {
        "step_number": 1,
        "error": {"type": "AgentToolCallError"},
        "tool_calls": [],
        "model_output_message": {
            "tool_calls": [
                {"function": {"name": "sql_engine", "arguments": {"query": "select 1"}}}
            ]
        },
    }
    text = {
        "step_number": 2,
        "error": {"type": "AgentToolExecutionError"},
        "tool_calls": [],
        "model_output": 'Action:\n{"name": "sql_engine", "arguments": "{\\"query\\": \\"select 2\\"}"}',
    }
    junk = {
        "step_number": 3,
        "error": {"type": "AgentParsingError"},
        "model_output": "no json",
    }

    result = SimpleNamespace(steps=[{"task": "x"}, native, text, junk])

    errors, tools, queries = harness._agent_step_facts(result)
    assert errors == (
        "AgentToolCallError",
        "AgentToolExecutionError",
        "AgentParsingError",
    )
    assert tools == ("sql_engine", "sql_engine")
    assert queries == ("select 1", "select 2")


def test_empty_tool_result_precedes_the_invented_answers() -> None:
    from examples.smolagents_text_to_sql_evaluation.replay import ReplayModel

    transcript = harness.load_transcript(harness.DEFAULT_MODEL_TAG)
    for case_id, expect_empty in (("Q33", True), ("Q36", True), ("Q34", False)):
        case = next(c for c in CASES if c["id"] == case_id)
        agent = harness._make_agent(
            ReplayModel(transcript["cases"][case_id]["steps"], "m")
        )
        result = agent.run(case["question"], return_full_result=True)
        first = next(s for s in result.steps if "step_number" in s)
        assert (first["observations"] == "") is expect_empty


def test_crashed_run_counts_against_tool_execution() -> None:
    class Unavailable(smolagents.Model):
        def generate(self, messages: Any, **kwargs: Any) -> Any:
            raise ConnectionError("model server unavailable")

    case = next(c for c in CASES if c["id"] == "Q05")
    (record,) = harness.run_cases(
        [case], DATA["tolerance"], mode="live", live_model_factory=lambda: Unavailable()
    )
    assert record.lifecycle == "failed"
    assert record.step_error_types[-1] == "run_exception"
    assert record.outcomes["tool_execution"].value == "fail"
    assert record.outcomes["task_success"].value == "fail"

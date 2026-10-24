# ruff: noqa: E501 -- report strings stay readable as whole sentences.
"""Render the analysis as stable JSON, a console summary and a Markdown report.

Language: Python. Pure formatting: every number comes from ``harness.analyse``.
"""

from __future__ import annotations

import json
from typing import Any

SMALL_SAMPLE = 10


def to_json(analysis: dict[str, Any]) -> str:
    return json.dumps(analysis, indent=2, sort_keys=True) + "\n"


def _pct(entry: dict[str, Any]) -> str:
    part = entry["reliability"]["pass_ratio"]
    if part is None:
        return "n/a"
    return f"{part['numerator'] / part['denominator']:.1%}"


def _left(entry: dict[str, Any]) -> str:
    part = entry["error_budget"]["remaining_fraction"]
    if part is None:
        return "n/a"
    return f"{part['numerator'] / part['denominator']:.0%}"


def to_text(analysis: dict[str, Any]) -> str:
    meta, summary = analysis["meta"], analysis["summary"]
    lines = [
        f"agent: smolagents {meta['smolagents_version']} ToolCallingAgent; model {meta['model_id']} (recorded {meta['recorded_at']})",
        f"cases: {summary['cases']}",
    ]
    for name, entry in analysis["indicators"].items():
        if "conflict" in entry:
            lines.append(f"  {name}: conflict {entry['conflict']}")
            continue
        considered = entry["counts"]["considered"]
        small = " (small sample)" if considered < SMALL_SAMPLE else ""
        lines.append(
            f"  {name}: {_pct(entry)} n={considered}{small} slo={entry['slo']['status']} budget={entry['error_budget']['status']} left={_left(entry)}"
        )
    lines.append(
        f"task failures: {summary['task_failures']}; with no upstream error signal (silent): {len(summary['silent_task_failures'])}"
    )
    return "\n".join(lines) + "\n"


def to_markdown(analysis: dict[str, Any]) -> str:
    meta, summary = analysis["meta"], analysis["summary"]
    out = ["# smolagents text-to-SQL agent: Gentlity reliability evaluation", ""]
    out.append(
        "Local real-world integration, **not** independent external validation. The agent is the upstream "
        f"`smolagents` {meta['smolagents_version']} `ToolCallingAgent` with the upstream `sql_engine` tool; the model is a "
        f"small local model (`{meta['model_id']}`); the questions are authored by the Gentlity authors (one is upstream's own). "
        "Model responses were recorded once and are replayed; the agent loop and SQL execution run for real."
    )
    out += [
        "",
        "## Indicators",
        "",
        "| Indicator | Reliability | n | SLO | SLO status | Error budget | Budget left |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, entry in analysis["indicators"].items():
        slo = analysis["slo_design"][name]["slo"]
        if "conflict" in entry:
            out.append(f"| {name} | conflict | - | {slo} | - | - | - |")
            continue
        out.append(
            f"| {name} | {_pct(entry)} | {entry['counts']['considered']} | {slo} | {entry['slo']['status']} | {entry['error_budget']['status']} | {_left(entry)} |"
        )
    out += ["", "## Failures behind task_success", ""]
    out.append(
        f"{summary['task_failures']} of {summary['cases']} runs failed `task_success`. "
        f"Visible through the upstream agent's own signals (run state, step errors, empty output): {summary['task_failures_visible_to_upstream_signals']}. "
        f"Silent (state `success`, no step error, plain answer): {summary['silent_task_failures']}."
    )
    adj = summary["adjudication"]
    out += ["", f"Manual adjudication of the evaluator verdicts: {adj}.", ""]
    out.append("| Case | Outcome | Answer | Expected | Upstream-visible | Verdict |")
    out.append("|---|---|---|---|---|---|")
    for c in analysis["cases"]:
        if c["outcomes"].get("task_success") == "pass" and not c["adjudication"]:
            continue
        verdict = (c["adjudication"] or {}).get("verdict", "-")
        answer = c["answer"].replace("|", "/").replace("\n", " ")[:90]
        out.append(
            f"| {c['case']} | {c['outcomes'].get('task_success')} | {answer} | {c['expected']} | {c['upstream_visible']} | {verdict} |"
        )
    out.append("")
    return "\n".join(out)

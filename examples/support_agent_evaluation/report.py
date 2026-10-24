# ruff: noqa: E501 -- report strings stay readable as whole sentences.
"""Render the analysis as stable JSON and as a short Markdown summary.

Language: Python. Pure formatting: every number comes from ``harness.analyse``.
"""

from __future__ import annotations

import json
from typing import Any


def to_json(analysis: dict[str, Any]) -> str:
    return json.dumps(analysis, indent=2, sort_keys=True) + "\n"


def _pct(entry: dict[str, Any]) -> str:
    part = entry["reliability"]["pass_ratio"]
    if part is None:
        return "n/a"
    return f"{part['numerator'] / part['denominator']:.1%}"


def _remaining(entry: dict[str, Any]) -> str:
    part = entry["error_budget"]["remaining_fraction"]
    if part is None:
        return "n/a"
    return f"{part['numerator'] / part['denominator']:.0%}"


def to_markdown(analysis: dict[str, Any]) -> str:
    out: list[str] = []
    data = analysis["dataset"]
    out.append("# Support-agent reliability evaluation")
    out.append("")
    out.append(
        f"Synthetic, offline, deterministic. {data['cases']} cases "
        f"({data['organic']} organic, {data['injected']} injected faults). "
        "This is synthetic validation only; it is not evidence from real users."
    )
    out.append("")
    for version, block in analysis["versions"].items():
        out.append(f"## Agent {version}")
        out.append("")
        out.append(
            "| Indicator | Reliability | SLO | SLO status | Error budget | Budget left |"
        )
        out.append("|---|---|---|---|---|---|")
        for name, entry in block["indicators"].items():
            objective = analysis["objectives"][name]["slo"]
            if "conflict" in entry:
                out.append(
                    f"| {name} | conflict: {entry['conflict']} | {objective} | - | - | - |"
                )
                continue
            out.append(
                f"| {name} | {_pct(entry)} | {objective} | {entry['slo']['status']} | "
                f"{entry['error_budget']['status']} | {_remaining(entry)} |"
            )
        seen = block["visibility"]
        out.append("")
        out.append(
            f"Visibility without Gentlity: {seen['run_status_or_error_log_success']} of "
            f"{seen['runs']} runs look successful from run status and error logs, but "
            f"{seen['runs_with_a_gentlity_failure']} runs have at least one failed indicator. "
            f"No log signal at all: {seen['silent_failures_no_log_signal']}. "
            f"Warning log only: {seen['failures_with_only_a_warning_log']}. "
            f"Visible as a crash or error log: "
            f"{seen['failures_visible_as_run_failure_or_error_log']}."
        )
        out.append("")
        out.append(
            "Evaluator accuracy against the independent oracle (false positives / false negatives):"
        )
        out.append("")
        out.append("| Indicator | TP | FP | FN | TN |")
        out.append("|---|---|---|---|---|")
        for name, row in block["evaluator_accuracy_vs_oracle"].items():
            out.append(
                f"| {name} | {row['true_positive']} | {row['false_positive']} | "
                f"{row['false_negative']} | {row['true_negative']} |"
            )
        out.append("")
    if "regression" in analysis:
        out.append("## Regression: v1 -> v2")
        out.append("")
        out.append("| Indicator | v1 | v2 | v1 SLO | v2 SLO | Comparable |")
        out.append("|---|---|---|---|---|---|")
        for name, row in analysis["regression"].items():
            if not row.get("comparable", False):
                out.append(f"| {name} | - | - | - | - | no |")
                continue
            out.append(
                f"| {name} | {row['v1_reliability']:.1%} | {row['v2_reliability']:.1%} | "
                f"{row['v1_slo']} | {row['v2_slo']} | yes |"
            )
        out.append("")
        demo = analysis["methodology_change_demo"]
        out.append(
            "Methodology guard: mixing observations from two versions of the same "
            f"evaluator is refused by the SDK (reasons: {demo.get('conflict')})."
        )
        out.append("")
    out.append("## Failure evidence")
    out.append("")
    for version, block in analysis["versions"].items():
        for item in block["failures"]:
            out.append(
                f"- **{version} / {item['case']} / {item['indicator']}** "
                f"({item['origin']}, {item['failure_mode'] or 'no mode'}): "
                f"reason `{item['evaluator_reason']}`; log signal `{item['log_signal']}`; "
                f"oracle agrees: {item['oracle_agrees_it_is_a_failure']}. "
                f"Answer: {item['answer']!r}. Reproduce: `{item['reproduce']}`"
            )
    out.append("")
    return "\n".join(out)


def to_text(analysis: dict[str, Any]) -> str:
    """A compact console summary."""
    lines = [
        f"cases: {analysis['dataset']['cases']} "
        f"(organic {analysis['dataset']['organic']}, injected {analysis['dataset']['injected']})"
    ]
    for version, block in analysis["versions"].items():
        lines.append(f"[{version}]")
        for name, entry in block["indicators"].items():
            if "conflict" in entry:
                lines.append(f"  {name}: conflict {entry['conflict']}")
                continue
            lines.append(
                f"  {name}: {_pct(entry)} slo={entry['slo']['status']} "
                f"budget={entry['error_budget']['status']}"
            )
        seen = block["visibility"]
        lines.append(
            f"  silent failures (no log signal): {len(seen['silent_failures_no_log_signal'])}; "
            f"runs with a failed indicator: {seen['runs_with_a_gentlity_failure']}/{seen['runs']}"
        )
    return "\n".join(lines) + "\n"

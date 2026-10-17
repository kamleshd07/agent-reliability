"""Check that a P29 pilot report cannot claim a safeguard without its evidence.

    python scripts/p29_pilot_report_check.py docs/P29_PILOT_REPORT_TEMPLATE.json
    python scripts/p29_pilot_report_check.py my_pilot_report.json --json verdict.json

Exit status 0 means the report is internally consistent (every safeguard marked
SATISFIED has every field filled, at least one evidence reference and a complete
sign-off). It does NOT judge whether the evidence is true, and it never sets a
status itself: ``pilot_ready`` is only reported, and only when all six safeguards
are SATISFIED and consistent. See docs/P29_PILOT_SAFEGUARDS.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

SCHEMA = "gentlity.p29-pilot-report/1"
STATUSES = ("NOT_SATISFIED", "SATISFIED")
FIELDS: dict[str, tuple[str, ...]] = {
    "SG-1": (
        "expected_evaluations_per_hour",
        "tokens_per_evaluation_measured",
        "budget_per_window",
        "max_pending",
        "max_concurrency",
        "r13_r14_incidents",
    ),
    "SG-2": ("note_restated_in_report",),
    "SG-3": ("indicator_windows", "dashboards_inspected"),
    "SG-4": (
        "judge_shares_scope_with_deterministic",
        "separate_scope_feasible",
        "decision",
        "readings_kept_on_deterministic_indicators",
    ),
    "SG-5": (
        "counters_wired",
        "alert_rule_ids",
        "firing_test_date",
        "firing_test_result",
    ),
    "SG-6": ("gate_id", "on_no_data", "partial_outage_not_covered_stated"),
}
MUST_BE_TRUE = {
    ("SG-2", "note_restated_in_report"),
    ("SG-5", "counters_wired"),
    ("SG-6", "partial_outage_not_covered_stated"),
}
_ON_NO_DATA = {"block", "warn", "allow"}
BOOLEANS = {
    ("SG-4", "judge_shares_scope_with_deterministic"),
    ("SG-4", "separate_scope_feasible"),
}
POSITIVE_COUNTS = {
    ("SG-1", "expected_evaluations_per_hour"),
    ("SG-1", "tokens_per_evaluation_measured"),
    ("SG-1", "budget_per_window"),
    ("SG-1", "max_pending"),
    ("SG-1", "max_concurrency"),
}
NONNEG_COUNTS = {("SG-1", "r13_r14_incidents")}
TEXT_LISTS = {
    ("SG-3", "dashboards_inspected"),
    ("SG-4", "readings_kept_on_deterministic_indicators"),
    ("SG-5", "alert_rule_ids"),
}
_WINDOW_KEYS = (
    "indicator",
    "window",
    "pass",
    "fail",
    "unknown",
    "execution_failures",
    "determinate",
    "reliability",
    "source",
)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _text(value: object, minimum: int = 1) -> bool:
    return isinstance(value, str) and len(value.strip()) >= minimum


def _count(value: object, *, positive: bool) -> bool:
    ok = isinstance(value, int) and not isinstance(value, bool)
    return ok and (value > 0 if positive else value >= 0)  # type: ignore[operator]


def _texts(value: object) -> bool:
    if _text(value):
        return True
    return isinstance(value, list) and bool(value) and all(_text(v) for v in value)


def _valid_date(value: object) -> bool:
    if not isinstance(value, str) or not _DATE.match(value):
        return False
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    return parsed.year >= 2020


def _row_problems(number: int, row: Any) -> list[str]:
    if not isinstance(row, dict):
        return [f"indicator_windows[{number}] is not an object"]
    out = [
        f"indicator_windows[{number}] missing {k}" for k in _WINDOW_KEYS if k not in row
    ]
    if out:
        return out
    for key in ("indicator", "window", "source"):
        if not _text(row[key]):
            out.append(f"indicator_windows[{number}].{key} is blank")
    for key in ("pass", "fail", "unknown", "execution_failures", "determinate"):
        if not _count(row[key], positive=False):
            out.append(
                f"indicator_windows[{number}].{key} must be a non-negative integer"
            )
    rel = row["reliability"]
    if rel is not None and not (
        isinstance(rel, (int, float)) and not isinstance(rel, bool) and 0 <= rel <= 1
    ):
        out.append(f"indicator_windows[{number}].reliability must be null or in [0, 1]")
    return out


def _field_problems(sg: str, fields: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for name in FIELDS[sg]:
        value = fields.get(name)
        if (sg, name) in MUST_BE_TRUE:
            ok = value is True
            why = "must be true"
        elif (sg, name) in BOOLEANS:
            ok = isinstance(value, bool)
            why = "must be true or false"
        elif (sg, name) in POSITIVE_COUNTS:
            ok = _count(value, positive=True)
            why = "must be a positive integer"
        elif (sg, name) in NONNEG_COUNTS:
            ok = _count(value, positive=False)
            why = "must be a non-negative integer"
        elif (sg, name) in TEXT_LISTS:
            ok = _texts(value)
            why = "must be non-blank text or a list of non-blank text"
        elif name == "indicator_windows":
            ok = isinstance(value, list) and bool(value)
            why = "must be a non-empty list"
        elif name == "on_no_data":
            ok = isinstance(value, str) and value in _ON_NO_DATA
            why = "must be set explicitly to one of block/warn/allow"
        elif name == "firing_test_date":
            ok = _valid_date(value)
            why = "must be an ISO date"
        else:
            ok = _text(value)
            why = "must be non-blank text"
        if not ok:
            out.append(f"field {name} {why}")
    if sg == "SG-3" and isinstance(fields.get("indicator_windows"), list):
        for number, row in enumerate(fields["indicator_windows"]):
            out += _row_problems(number, row)
    return out


def _problems(sg: str, entry: Any) -> list[str]:
    if not isinstance(entry, dict):
        return ["entry is not an object"]
    status = entry.get("status")
    if status not in STATUSES:
        return [f"status must be one of {STATUSES}"]
    fields = entry.get("fields")
    if not isinstance(fields, dict):
        return ["fields must be an object"]
    out: list[str] = []
    unknown = sorted(set(fields) - set(FIELDS[sg]))
    if unknown:
        out.append(f"unknown fields: {unknown}")
    if status == "NOT_SATISFIED":
        return out
    out += _field_problems(sg, fields)
    evidence = entry.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        out.append("no evidence reference")
    elif any(not _text(item, 6) for item in evidence):
        out.append("every evidence reference must be text of at least 6 characters")
    signoff = entry.get("signoff")
    if not isinstance(signoff, dict):
        out.append("sign-off missing")
    else:
        for key in ("role", "name"):
            if not _text(signoff.get(key), 2):
                out.append(f"sign-off {key} is blank")
        if not _valid_date(signoff.get("date")):
            out.append("sign-off date must be an ISO date (2020 or later)")
    return out


def check(report: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "consistent": True,
        "safeguards": {},
        "pilot_ready": False,
    }
    problems_top: list[str] = []
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        problems_top.append(f"schema must be {SCHEMA}")
        report = {}
    safeguards = report.get("safeguards")
    if not isinstance(safeguards, dict):
        problems_top.append("safeguards must be an object")
        safeguards = {}
    for sg in FIELDS:
        entry = safeguards.get(sg)
        problems = ["safeguard missing"] if entry is None else _problems(sg, entry)
        status = entry.get("status") if isinstance(entry, dict) else None
        result["safeguards"][sg] = {"status": status, "problems": problems}
    extra = (
        sorted(set(safeguards) - set(FIELDS)) if isinstance(safeguards, dict) else []
    )
    if extra:
        problems_top.append(f"unknown safeguards: {extra}")
    # Authorization is an owner act recorded outside this report; the report may not
    # carry it unless every safeguard is satisfied and consistent.
    all_satisfied = all(
        v["status"] == "SATISFIED" and not v["problems"]
        for v in result["safeguards"].values()
    )
    if "pilot_authorized" in report and not isinstance(
        report["pilot_authorized"], bool
    ):
        problems_top.append("pilot_authorized must be true or false")
    if report.get("pilot_authorized") is True and not all_satisfied:
        problems_top.append(
            "pilot_authorized is true but not every safeguard is satisfied"
        )
    result["problems"] = problems_top
    result["consistent"] = not problems_top and all(
        not v["problems"] for v in result["safeguards"].values()
    )
    result["pilot_ready"] = result["consistent"] and all(
        v["status"] == "SATISFIED" for v in result["safeguards"].values()
    )
    return result


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate JSON key")
    return dict(pairs)


def _no_constant(name: str) -> Any:
    raise ValueError(f"{name} is not allowed")


def load_strict(text: str) -> Any:
    """Parse JSON refusing duplicate keys and NaN/Infinity."""
    return json.loads(
        text, object_pairs_hook=_no_duplicates, parse_constant=_no_constant
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path)
    parser.add_argument("--json", type=Path, dest="json_out")
    args = parser.parse_args(argv)
    try:
        report = load_strict(args.report.read_text(encoding="utf-8"))
    except (ValueError, RecursionError, OSError) as error:
        print(f"report is not acceptable JSON: {error}")
        return 1
    result = check(report)
    for sg, verdict in result["safeguards"].items():
        print(
            f"{sg}: {verdict['status']}"
            + "".join(f"\n  - {p}" for p in verdict["problems"])
        )
    for problem in result["problems"]:
        print(f"report: {problem}")
    print(f"consistent: {result['consistent']}  pilot_ready: {result['pilot_ready']}")
    if args.json_out:
        args.json_out.write_text(
            json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
        )
    return 0 if result["consistent"] else 1


if __name__ == "__main__":
    sys.exit(main())

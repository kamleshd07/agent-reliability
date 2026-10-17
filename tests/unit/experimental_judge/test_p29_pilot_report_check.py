"""The pilot-report checker refuses a SATISFIED safeguard that lacks its evidence."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "docs" / "P29_PILOT_REPORT_TEMPLATE.json"
SCRIPT = ROOT / "scripts" / "p29_pilot_report_check.py"

pytestmark = pytest.mark.skipif(
    not (TEMPLATE.is_file() and SCRIPT.is_file()),
    reason="repository-only governance files (not part of the installed package)",
)


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("p29_pilot_report_check", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECK = _module().check
SIGNOFF = {
    "role": "pilot owner (example)",
    "name": "Example Person",
    "date": "2026-01-02",
}
FILLED: dict[str, dict[str, Any]] = {
    "SG-1": {
        "expected_evaluations_per_hour": 100,
        "tokens_per_evaluation_measured": 900,
        "budget_per_window": 1000000,
        "max_pending": 64,
        "max_concurrency": 4,
        "r13_r14_incidents": 0,
    },
    "SG-2": {"note_restated_in_report": True},
    "SG-3": {
        "indicator_windows": [
            {
                "indicator": "answer-correctness",
                "window": "2026-01-01/2026-01-02",
                "pass": 1,
                "fail": 1,
                "unknown": 0,
                "execution_failures": 1,
                "determinate": 2,
                "reliability": 0.5,
                "source": "P3 summary read",
            }
        ],
        "dashboards_inspected": ["dash-1"],
    },
    "SG-4": {
        "judge_shares_scope_with_deterministic": True,
        "separate_scope_feasible": True,
        "decision": "use a separate scope",
        "readings_kept_on_deterministic_indicators": ["task-success"],
    },
    "SG-5": {
        "counters_wired": True,
        "alert_rule_ids": ["rule-1"],
        "firing_test_date": "2026-01-02",
        "firing_test_result": "fired",
    },
    "SG-6": {
        "gate_id": "gate-1",
        "on_no_data": "block",
        "partial_outage_not_covered_stated": True,
    },
}


def _template() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    return loaded


def _satisfied(sg: str, report: dict[str, Any]) -> None:
    entry = report["safeguards"][sg]
    entry["status"] = "SATISFIED"
    entry["fields"] = copy.deepcopy(FILLED[sg])
    entry["evidence"] = [f"artifact-{sg}"]
    entry["signoff"] = dict(SIGNOFF)


def test_shipped_template_is_consistent_and_claims_nothing() -> None:
    result = CHECK(_template())
    assert result["consistent"] is True and result["pilot_ready"] is False
    assert {v["status"] for v in result["safeguards"].values()} == {"NOT_SATISFIED"}
    assert _template()["pilot_authorized"] is False


@pytest.mark.parametrize("sg", sorted(FILLED))
def test_a_fully_evidenced_safeguard_is_accepted(sg: str) -> None:
    report = _template()
    _satisfied(sg, report)
    assert CHECK(report)["safeguards"][sg]["problems"] == []


@pytest.mark.parametrize("sg", sorted(FILLED))
def test_satisfied_without_evidence_or_signoff_or_fields_is_rejected(sg: str) -> None:
    for breakage in ("evidence", "signoff", "fields"):
        report = _template()
        _satisfied(sg, report)
        entry = report["safeguards"][sg]
        entry[breakage] = (
            []
            if breakage == "evidence"
            else (
                {"role": None, "name": None, "date": None}
                if breakage == "signoff"
                else {}
            )
        )
        result = CHECK(report)
        assert result["safeguards"][sg]["problems"], (sg, breakage)
        assert result["consistent"] is False


def test_sign_off_with_an_invalid_date_is_rejected() -> None:
    report = _template()
    _satisfied("SG-1", report)
    report["safeguards"]["SG-1"]["signoff"]["date"] = "yesterday"
    assert CHECK(report)["consistent"] is False


def test_sg6_requires_an_explicit_on_no_data_and_the_partial_outage_statement() -> None:
    report = _template()
    _satisfied("SG-6", report)
    report["safeguards"]["SG-6"]["fields"]["on_no_data"] = "maybe"
    assert CHECK(report)["consistent"] is False
    _satisfied("SG-6", report)
    report["safeguards"]["SG-6"]["fields"]["partial_outage_not_covered_stated"] = False
    assert CHECK(report)["consistent"] is False


def test_sg3_rows_must_show_every_count_beside_reliability() -> None:
    report = _template()
    _satisfied("SG-3", report)
    del report["safeguards"]["SG-3"]["fields"]["indicator_windows"][0]["fail"]
    assert CHECK(report)["consistent"] is False


def test_pilot_ready_needs_all_six_and_authorization_cannot_be_claimed_early() -> None:
    report = _template()
    for sg in ("SG-1", "SG-2", "SG-3", "SG-4", "SG-5"):
        _satisfied(sg, report)
    assert CHECK(report)["pilot_ready"] is False
    report["pilot_authorized"] = True
    result = CHECK(report)
    assert result["consistent"] is False and result["pilot_ready"] is False
    _satisfied("SG-6", report)
    assert CHECK(report)["pilot_ready"] is True


def test_unknown_status_schema_and_extra_safeguard_are_rejected() -> None:
    report = _template()
    report["safeguards"]["SG-1"]["status"] = "DONE"
    assert CHECK(report)["consistent"] is False
    assert CHECK({"schema": "other"})["consistent"] is False
    report = _template()
    report["safeguards"]["SG-7"] = {}
    assert CHECK(report)["consistent"] is False


BYPASSES = [
    ("SG-1", "signoff", {"role": " ", "name": "Example Person", "date": "2026-01-02"}),
    ("SG-1", "signoff", {"role": "role x", "name": " ", "date": "2026-01-02"}),
    (
        "SG-1",
        "signoff",
        {"role": "role x", "name": "Example Person", "date": "0001-01-01"},
    ),
    ("SG-1", "evidence", ["x"]),
    ("SG-1", "evidence", ["      "]),
    ("SG-1", "evidence", [None]),
    ("SG-4", "fields", {**FILLED["SG-4"], "separate_scope_feasible": None}),
    ("SG-4", "fields", {**FILLED["SG-4"], "decision": " "}),
    ("SG-1", "fields", {**FILLED["SG-1"], "max_pending": 0}),
    ("SG-1", "fields", {**FILLED["SG-1"], "max_concurrency": False}),
    ("SG-1", "fields", {**FILLED["SG-1"], "r13_r14_incidents": -1}),
    ("SG-5", "fields", {**FILLED["SG-5"], "alert_rule_ids": [" "]}),
    ("SG-5", "fields", {**FILLED["SG-5"], "counters_wired": False}),
    ("SG-3", "fields", {**FILLED["SG-3"], "dashboards_inspected": False}),
    (
        "SG-3",
        "fields",
        {
            **FILLED["SG-3"],
            "indicator_windows": [
                dict.fromkeys(FILLED["SG-3"]["indicator_windows"][0])
            ],
        },
    ),
    ("SG-1", "fields", None),
    ("SG-1", "fields", "abc"),
]


@pytest.mark.parametrize(("sg", "key", "value"), BYPASSES)
def test_blank_wrongly_typed_or_junk_values_are_not_evidence(
    sg: str, key: str, value: Any
) -> None:
    report = _template()
    _satisfied(sg, report)
    report["safeguards"][sg][key] = value
    result = CHECK(report)
    assert result["consistent"] is False and result["pilot_ready"] is False


@pytest.mark.parametrize("shape", [[], None, "x", 3])
def test_malformed_top_level_shapes_are_refused_without_crashing(shape: Any) -> None:
    report = _template()
    report["safeguards"] = shape
    assert CHECK(report)["consistent"] is False


def test_duplicate_keys_and_nan_are_refused_when_loading() -> None:
    load = _module().load_strict
    with pytest.raises(ValueError):
        load('{"a": 1, "a": 2}')
    with pytest.raises(ValueError):
        load('{"a": NaN}')


def test_non_boolean_authorization_and_unhashable_on_no_data_are_refused() -> None:
    report = _template()
    report["pilot_authorized"] = "yes"
    assert CHECK(report)["consistent"] is False
    report = _template()
    _satisfied("SG-6", report)
    report["safeguards"]["SG-6"]["fields"]["on_no_data"] = ["block"]
    assert CHECK(report)["consistent"] is False


def test_unreadable_or_deeply_nested_input_gives_a_clean_refusal(
    tmp_path: Path,
) -> None:
    main = _module().main
    deep = tmp_path / "deep.json"
    deep.write_text("[" * 200000, encoding="utf-8")
    assert main([str(deep)]) == 1
    assert main([str(tmp_path / "missing.json")]) == 1

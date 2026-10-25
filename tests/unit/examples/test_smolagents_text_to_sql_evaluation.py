# ruff: noqa: E501 -- long explanatory strings stay readable as sentences.
"""The smolagents text-to-SQL evaluation: reference data, replay fidelity, honesty.

Local real-world integration, not external validation. The reference and checker tests
need only the standard library and run everywhere; the replay tests need the
example-only dependencies in ``examples/smolagents_text_to_sql_evaluation/requirements.txt``
(smolagents, sqlalchemy) and are skipped, with that reason, when they are not installed.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from examples.smolagents_text_to_sql_evaluation import checks

PACKAGE = (
    Path(__file__).resolve().parents[3]
    / "examples"
    / "smolagents_text_to_sql_evaluation"
)
DATA = json.loads((PACKAGE / "data" / "cases.json").read_text(encoding="utf-8"))
CASES = DATA["cases"]
ROWS = [
    (1, "Alan Payne", 12.06, 1.20),
    (2, "Alex Mason", 23.86, 0.24),
    (3, "Woodrow Wilson", 53.43, 5.43),
    (4, "Margaret James", 21.11, 1.00),
]
NEEDS_AGENT_STACK = (
    "install examples/smolagents_text_to_sql_evaluation/requirements.txt"
)


def _reference(sql: str) -> list[Any]:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "create table receipts(receipt_id integer, customer_name text, price real, tip real)"
    )
    connection.executemany("insert into receipts values (?, ?, ?, ?)", ROWS)
    return [row[0] for row in connection.execute(sql).fetchall()]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_expected_value_comes_from_the_reference_sql(case: dict[str, Any]) -> None:
    if case["kind"] == "absent":
        assert case["reference_sql"] is None and case["expected"] == []
        return
    values = _reference(case["reference_sql"])
    if case["kind"] == "number":
        assert len(values) == 1
        assert abs(values[0] - case["expected"][0]) < 1e-6
    elif case["kind"] == "name":
        assert values == case["expected"]
    else:
        assert sorted(values) == sorted(case["expected"])
        assert not set(case["forbidden"]) & set(case["expected"])


def test_case_set_is_honestly_labelled() -> None:
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)) == 36
    assert [c["id"] for c in CASES if c["origin"] == "upstream"] == ["Q01"]
    assert {c["origin"] for c in CASES} == {"upstream", "authored"}


def test_checker_rules() -> None:
    number = {
        "kind": "number",
        "question": "What is 2 plus 2 receipts?",
        "expected": [4.0],
        "forbidden": [],
    }
    assert checks.answer_matches(number, "There are 4 receipts", 0.01)
    assert not checks.answer_matches(number, "There are 5 receipts", 0.01)
    assert not checks.answer_matches(number, "no digits", 0.01)
    names = {
        "kind": "names",
        "question": "q",
        "expected": ["A B"],
        "forbidden": ["C D"],
    }
    assert checks.answer_matches(names, "a b", 0.01)
    assert not checks.answer_matches(names, "A B and C D", 0.01)
    absent = {"kind": "absent", "question": "q", "expected": [], "forbidden": []}
    assert checks.answer_matches(absent, "That is not available", 0.01)
    assert not checks.answer_matches(absent, "Woodrow Wilson", 0.01)
    with pytest.raises(ValueError):
        checks.answer_matches({**absent, "kind": "other"}, "x", 0.01)


def test_recorded_files_carry_no_local_paths_or_credentials() -> None:
    pattern = re.compile(
        r"/(?:Users|home)/|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|@[\w-]+\.\w+"
    )
    for path in (PACKAGE / "transcripts").glob("*.json"):
        assert pattern.search(path.read_text(encoding="utf-8")) is None, path.name
    for path in [*(PACKAGE / "expected").glob("*"), *(PACKAGE / "data").glob("*")]:
        assert pattern.search(path.read_text(encoding="utf-8")) is None, path.name


def test_absent_rule_needs_a_refusal_and_no_invented_number() -> None:
    case = {
        "kind": "absent",
        "question": "price of receipt 9?",
        "expected": [],
        "forbidden": [],
    }
    assert checks.answer_matches(case, "There is no receipt 9.", 0.01)
    assert not checks.answer_matches(case, "The price is 12.50 -- unknown source", 0.01)
    assert not checks.answer_matches(case, "A piano costs more", 0.01)

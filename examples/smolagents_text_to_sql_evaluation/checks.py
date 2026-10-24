"""Independent reference checks for the text-to-SQL cases.

Language: Python. Standard library only. ``reference_sql`` in ``data/cases.json`` is run
by the tests against the same four rows with ``sqlite3``; the agent never sees it, so
the expected value does not come from the agent under test.
"""

from __future__ import annotations

import re
from typing import Any

ABSENT_PHRASES = (
    "no ",
    "not ",
    "cannot",
    "can't",
    "unable",
    "doesn't",
    "does not",
    "n/a",
    "unknown",
    "none",
    "unavailable",
    "isn't",
    "there is no",
)
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def numbers_in(text: str) -> list[float]:
    found: list[float] = []
    for token in _NUMBER.findall(text):
        try:
            found.append(float(token.replace(",", "")))
        except ValueError:  # pragma: no cover - the pattern only yields numbers
            continue
    return found


def answer_matches(case: dict[str, Any], answer: str, tolerance: float) -> bool:
    """True when ``answer`` agrees with the case's reference value."""
    folded = answer.casefold()
    kind = case["kind"]
    if kind == "absent":
        return any(phrase in folded + " " for phrase in ABSENT_PHRASES)
    if any(name.casefold() in folded for name in case["forbidden"]):
        return False
    if kind in ("name", "names"):
        return all(name.casefold() in folded for name in case["expected"])
    if kind == "number":
        question_numbers = set(numbers_in(case["question"]))
        values = [v for v in numbers_in(answer) if v not in question_numbers]
        return any(abs(v - case["expected"][0]) <= tolerance for v in values)
    raise ValueError(f"unknown case kind {kind!r}")

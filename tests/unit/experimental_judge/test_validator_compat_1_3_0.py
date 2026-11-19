"""Compatibility of the shared schema validator with the 1.3.0 behaviour.

1.3.0 evaluated ``pattern`` with ``re.search`` alone, so an anchored ``...$`` pattern
accepted a value with one trailing newline. The validator now follows ECMA-262 and
rejects it. This module pins the *only* intended difference: for every pattern the
bundled schemas use, a value without a trailing newline gets the same verdict as the
1.3.0 rule, and a value with one gets a rejection when the pattern ends in ``$``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from importlib import resources
from typing import Any

import pytest

from agent_reliability.experimental.judge._jsonschema import SchemaViolation, validate
from agent_reliability.experimental.judge.calibration import load_schema

pytestmark = pytest.mark.unit

SAMPLES = (
    "a", "abc-1", "ok-value", "a.b_c", "x" * 64, "0" * 64, "f" * 64, "-bad", "",
    "Judge", "JudgeFooError", "2026-01-01T00:00:00Z", "a" * 128, "a" * 129, " ",
)  # fmt: skip


def _patterns(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        if isinstance(node.get("pattern"), str):
            yield node["pattern"]
        for value in node.values():
            yield from _patterns(value)
    elif isinstance(node, list):
        for value in node:
            yield from _patterns(value)


def _bundled_patterns() -> list[str]:
    found: set[str] = set()
    base = resources.files("agent_reliability.experimental")
    for folder in ("judge", "calibration"):
        schemas = base.joinpath(folder, "schemas")
        for entry in schemas.iterdir():
            if entry.name.endswith(".schema.json"):
                found.update(_patterns(json.loads(entry.read_text(encoding="utf-8"))))
    return sorted(found)


def _accepts(pattern: str, value: str) -> bool:
    try:
        validate(value, {"type": "string", "pattern": pattern})
    except SchemaViolation:
        return False
    return True


PATTERNS = _bundled_patterns()


def test_bundled_schemas_expose_anchored_patterns() -> None:
    assert PATTERNS
    assert any(p.endswith("$") for p in PATTERNS)


@pytest.mark.parametrize("pattern", PATTERNS)
def test_values_without_trailing_newline_keep_the_1_3_0_verdict(pattern: str) -> None:
    for sample in SAMPLES:
        for value in (sample, sample + " ", sample + "\r\n", "\n" + sample):
            if value.endswith("\n"):
                continue
            legacy = re.search(pattern, value) is not None
            assert _accepts(pattern, value) is legacy, (pattern, value)


@pytest.mark.parametrize("pattern", [p for p in PATTERNS if p.endswith("$")])
def test_trailing_newline_after_an_anchored_pattern_is_the_only_new_rejection(
    pattern: str,
) -> None:
    changed = 0
    for sample in SAMPLES:
        value = sample + "\n"
        legacy = re.search(pattern, value) is not None
        assert _accepts(pattern, value) is False
        changed += legacy  # accepted by 1.3.0, rejected now
    # Every anchored pattern is affected for at least one otherwise-valid value.
    assert changed >= 1


def test_unanchored_pattern_still_accepts_a_trailing_newline() -> None:
    assert _accepts("^[a-z]+", "abc\n") is True


def test_calibration_case_identifier_with_trailing_newline_is_rejected() -> None:
    schema = load_schema("calibration-case")
    (id_pattern,) = {
        p for p in _patterns(schema["properties"]["case_id"]) if p.endswith("$")
    }
    assert re.search(id_pattern, "a01\n") is not None  # accepted by 1.3.0 semantics
    with pytest.raises(SchemaViolation):
        validate(
            {"case_id": "a01\n"},
            {
                "type": "object",
                "properties": {"case_id": schema["properties"]["case_id"]},
            },
        )

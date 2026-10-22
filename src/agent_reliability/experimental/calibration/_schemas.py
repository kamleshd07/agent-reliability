"""The published JSON Schemas of the calibration file formats (stdlib validation)."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

from agent_reliability.experimental.judge._jsonschema import validate

__all__ = ["check", "load_schema"]

_NAMES = ("reference-dataset", "reference-case", "calibration-assessment")


@cache
def _load(name: str) -> str:
    return (
        resources.files("agent_reliability.experimental.calibration")
        .joinpath("schemas", f"{name}.schema.json")
        .read_text(encoding="utf-8")
    )


def load_schema(name: str) -> dict[str, Any]:
    """Return a fresh copy of one published schema."""
    if name not in _NAMES:
        raise ValueError("unknown schema name")
    schema: dict[str, Any] = json.loads(_load(name))
    return schema


def check(document: Any, name: str) -> None:
    """Validate ``document``; raises ``ValueError`` naming a path, never a value."""
    validate(document, load_schema(name))

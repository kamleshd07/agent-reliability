"""Tiny shared validation helpers (stdlib only, no schema language).

Used by the judge-output parser and by ``StructuredOutputEvaluator`` so both
apply identical JSON type and member rules (P29-S08-AC02).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

__all__ = ["JSON_TYPE_NAMES", "check_members", "is_json_type"]

JSON_TYPE_NAMES: Final = frozenset(
    {"string", "integer", "number", "boolean", "array", "object", "null"}
)


def is_json_type(value: Any, name: str) -> bool:
    """RFC 8259 value types. ``bool`` is never an integer or a number."""
    if name == "string":
        return isinstance(value, str)
    if name == "integer":
        return type(value) is int
    if name == "number":
        return type(value) in (int, float)
    if name == "boolean":
        return type(value) is bool
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, Mapping)
    if name == "null":
        return value is None
    raise ValueError("unknown JSON type name")


def check_members(
    document: Mapping[str, Any], required: frozenset[str], allowed: frozenset[str]
) -> bool:
    """All required members present and no member outside ``allowed``."""
    keys = set(document)
    return required <= keys and not keys - allowed

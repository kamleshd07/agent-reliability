"""Minimal stdlib JSON Schema subset validator (no third-party dependency).

Supports exactly what the P29 calibration schemas use: ``type`` (name or list),
``enum``, ``const``, ``pattern``, ``minLength``, ``maxLength``, ``minimum``,
``maximum``, ``required``, ``properties``, ``additionalProperties`` (bool or
schema), ``propertyNames`` (enum/pattern), ``items``, ``minItems``,
``maxItems`` and local ``$ref`` to ``#/$defs/...``. Anything else in a schema is
rejected so an unsupported keyword can never be silently ignored.
"""

from __future__ import annotations

import re
from typing import Any, Final

from agent_reliability.experimental.judge._schema import is_json_type

__all__ = ["SchemaViolation", "validate"]

_KNOWN: Final = frozenset(
    {
        "$schema", "$id", "$defs", "$ref", "title", "type", "enum", "const",
        "pattern", "minLength", "maxLength", "minimum", "maximum", "required",
        "properties", "additionalProperties", "propertyNames", "items",
        "minItems", "maxItems",
    }
)  # fmt: skip


class SchemaViolation(ValueError):
    """A document does not satisfy a schema. The message names a path, never a value."""


def validate(document: Any, schema: dict[str, Any]) -> None:
    _check(document, schema, schema, "$")


def _fail(path: str, reason: str) -> SchemaViolation:
    return SchemaViolation(f"{path}: {reason}")


def _resolve(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/$defs/"):
        raise ValueError("unsupported $ref")
    target: dict[str, Any] = root["$defs"][ref[len("#/$defs/") :]]
    return target


def _check(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str) -> None:
    unknown = set(schema) - _KNOWN
    if unknown:
        raise ValueError("unsupported schema keyword")
    if "$ref" in schema:
        _check(value, _resolve(root, schema["$ref"]), root, path)
        return
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(is_json_type(value, n) for n in names):
            raise _fail(path, "wrong type")
    if "const" in schema and (
        value != schema["const"] or type(value) is not type(schema["const"])
    ):
        raise _fail(path, "not the required constant")
    if "enum" in schema and not any(
        value == option and type(value) is type(option) for option in schema["enum"]
    ):
        raise _fail(path, "not an allowed value")
    if isinstance(value, str):
        if "pattern" in schema and (
            re.search(schema["pattern"], value) is None
            # ECMA-262 `$` (no multiline flag) does not match before a trailing
            # newline, but Python's does; keep both readings identical.
            or (schema["pattern"].endswith("$") and value.endswith("\n"))
        ):
            raise _fail(path, "does not match the pattern")
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get(
            "maxLength", 10**9
        ):
            raise _fail(path, "length out of range")
    if type(value) in (int, float):
        if "minimum" in schema and value < schema["minimum"]:
            raise _fail(path, "below the minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise _fail(path, "above the maximum")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get(
            "maxItems", 10**9
        ):
            raise _fail(path, "item count out of range")
        if "items" in schema:
            for index, item in enumerate(value):
                _check(item, schema["items"], root, f"{path}[{index}]")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise _fail(path, f"missing member {key}")
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        name_rule = schema.get("propertyNames")
        for key, item in value.items():
            if name_rule is not None:
                _check(key, name_rule, root, f"{path}.<name>")
            if key in properties:
                _check(item, properties[key], root, f"{path}.{key}")
            elif extra is False:
                raise _fail(path, "unexpected member")
            elif isinstance(extra, dict):
                _check(item, extra, root, f"{path}.{key}")

"""Strict, bounded JSON reading for untrusted dataset files."""

from __future__ import annotations

import json
from typing import Any

__all__ = ["canonical", "strict_loads"]


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _no_constants(_: str) -> Any:
    raise ValueError("NaN and Infinity are not valid JSON")


def _depth_ok(value: Any, limit: int) -> bool:
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if depth > limit:
            return False
        if isinstance(item, dict):
            stack.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            stack.extend((v, depth + 1) for v in item)
    return True


def strict_loads(text: str, *, max_depth: int = 8) -> Any:
    """Parse JSON rejecting duplicate members, NaN/Infinity and excess nesting."""
    try:
        value = json.loads(
            text, object_pairs_hook=_no_duplicates, parse_constant=_no_constants
        )
    except RecursionError:
        raise ValueError("JSON nesting is too deep") from None
    if not _depth_ok(value, max_depth):
        raise ValueError("JSON nesting is too deep")
    return value


def canonical(value: Any) -> str:
    """Canonical JSON: sorted members, compact separators, UTF-8 text, no NaN."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )

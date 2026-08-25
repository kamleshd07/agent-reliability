"""Bounded validation for public M4 machine identifiers."""

from __future__ import annotations

import re

_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_OPAQUE_ID = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._+-]{0,126}[A-Za-z0-9])?$")
_REASON_CODE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")


def validate_evaluator_name(value: str) -> str:
    if not isinstance(value, str) or _NAME.fullmatch(value) is None:
        raise ValueError(
            "evaluator name must be 1-64 lowercase ASCII letters, digits, or "
            "internal hyphens, beginning and ending with a letter or digit"
        )
    return value


def validate_opaque_id(value: str, field: str) -> str:
    if not isinstance(value, str) or _OPAQUE_ID.fullmatch(value) is None:
        raise ValueError(f"{field} must be a 1-128 character ASCII machine identifier")
    return value


def validate_optional_opaque_id(value: str | None, field: str) -> str | None:
    return None if value is None else validate_opaque_id(value, field)


def validate_reason_code(value: str | None) -> str | None:
    if value is not None and _REASON_CODE.fullmatch(value) is None:
        raise ValueError(
            "reason_code must be a 1-128 character lowercase ASCII machine code"
        )
    return value


def validate_exception_type(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or not value.isprintable()
        or any(character.isspace() for character in value)
    ):
        raise ValueError("exception_type must be a bounded printable class name")
    return value

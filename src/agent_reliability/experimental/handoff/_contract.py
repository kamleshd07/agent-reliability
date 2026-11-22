"""Closed, content-free P25 handoff event (wire schema_version 1).

Pure functions: no I/O, no threads, no framework import. Only identifiers, closed
enumerations, one timestamp and bounded machine keys can be expressed. Bounds are the
documented contract bounds; the platform stays the authority and may be stricter.
The reporter is never sent: the platform derives it from ``kind``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Literal
from uuid import UUID

SCHEMA_VERSION: Final = 1
HANDOFF_EVENTS_PATH: Final = "/api/v1/handoff-events"
MAX_BODY_BYTES: Final = 16 * 1024

Kind = Literal["requested", "acknowledged", "terminal"]
Acceptance = Literal["accepted", "declined"]
TerminalState = Literal["completed", "failed", "cancelled"]

_KINDS: Final = frozenset({"requested", "acknowledged", "terminal"})
_ACCEPTANCE: Final = frozenset({"accepted", "declined"})
_TERMINAL: Final = frozenset({"completed", "failed", "cancelled"})
_SOURCE: Final = re.compile(r"[A-Za-z0-9._-]{1,100}\Z", re.ASCII)
_KEY128: Final = re.compile(r"[A-Za-z0-9._-]{1,128}\Z", re.ASCII)
_KEY200: Final = re.compile(r"[A-Za-z0-9._-]{1,200}\Z", re.ASCII)
_RUN_ID: Final = re.compile(r"[!-~]{1,200}\Z", re.ASCII)


class HandoffValidationError(ValueError):
    """A member is outside the closed contract. The message is a fixed label and never
    contains the offending value."""


def valid_source(value: object) -> bool:
    return type(value) is str and _SOURCE.match(value) is not None


def _fail(label: str) -> HandoffValidationError:
    return HandoffValidationError(label)


def _text(value: object, pattern: re.Pattern[str], name: str) -> str:
    if type(value) is not str or not pattern.match(value):
        raise _fail(f"{name}_invalid")
    return value


def _uuid(value: object, name: str) -> str:
    if type(value) is UUID:
        return str(value)
    if type(value) is str and len(value) == 36:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    raise _fail(f"{name}_invalid")


def _instant(value: object) -> str:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.tzinfo.utcoffset(value) is None
    ):
        raise _fail("event_time_invalid")
    try:
        utc = value.astimezone(UTC)
    except (ValueError, OverflowError):
        raise _fail("event_time_invalid") from None
    return utc.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _optional(value: object, pattern: re.Pattern[str], name: str) -> str | None:
    return None if value is None else _text(value, pattern, name)


@dataclass(frozen=True, slots=True)
class HandoffEvent:
    """A validated event: the exact wire members and the encoded body."""

    members: dict[str, Any]
    body: bytes

    @property
    def idempotency_key(self) -> str:
        return str(self.members["idempotency_key"])

    @property
    def kind(self) -> str:
        return str(self.members["kind"])


def _semantic(
    *,
    source: str,
    handoff_id: str,
    kind: str,
    originating_agent_id: str,
    originating_producer_run_id: str,
    receiving_agent_id: str,
    receiving_producer_run_id: str | None,
    outcome_correlation_id: str | None,
    event_time: str,
    acceptance: str | None,
    terminal_state: str | None,
) -> str:
    # Mirrors the platform's semantic digest: every member except delivery
    # bookkeeping, event_time included (a different time is different evidence).
    parts = [
        str(SCHEMA_VERSION),
        source,
        handoff_id,
        kind,
        originating_agent_id,
        originating_producer_run_id,
        receiving_agent_id,
        str(receiving_producer_run_id),
        str(outcome_correlation_id),
        event_time,
        str(acceptance),
        str(terminal_state),
    ]
    return "hk1-" + hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def idempotency_key(
    *,
    source: str,
    kind: Kind,
    handoff_id: str,
    originating_agent_id: UUID | str,
    originating_producer_run_id: str,
    receiving_agent_id: UUID | str,
    event_time: datetime,
    receiving_producer_run_id: str | None = None,
    outcome_correlation_id: str | None = None,
    acceptance: Acceptance | None = None,
    terminal_state: TerminalState | None = None,
) -> str:
    """Deterministic key (``hk1-`` plus SHA-256 hex) over the semantic members.

    The same logical event always yields the same key, across processes and restarts,
    provided the same ``event_time`` is supplied. Content-free by construction.
    """
    if type(kind) is not str or kind not in _KINDS:
        raise _fail("kind_invalid")
    return _semantic(
        source=_text(source, _SOURCE, "source"),
        handoff_id=_text(handoff_id, _KEY128, "handoff_id"),
        kind=kind,
        originating_agent_id=_uuid(originating_agent_id, "originating_agent_id"),
        originating_producer_run_id=_text(
            originating_producer_run_id, _RUN_ID, "originating_producer_run_id"
        ),
        receiving_agent_id=_uuid(receiving_agent_id, "receiving_agent_id"),
        receiving_producer_run_id=_optional(
            receiving_producer_run_id, _RUN_ID, "receiving_producer_run_id"
        ),
        outcome_correlation_id=_optional(
            outcome_correlation_id, _KEY128, "outcome_correlation_id"
        ),
        event_time=_instant(event_time),
        acceptance=acceptance,
        terminal_state=terminal_state,
    )


def build_event(
    *,
    source: str,
    kind: Kind,
    handoff_id: str,
    originating_agent_id: UUID | str,
    originating_producer_run_id: str,
    receiving_agent_id: UUID | str,
    event_time: datetime,
    receiving_producer_run_id: str | None = None,
    outcome_correlation_id: str | None = None,
    acceptance: Acceptance | None = None,
    terminal_state: TerminalState | None = None,
    idempotency_key: str | None = None,
) -> HandoffEvent:
    """Validate against the closed contract and encode the exact request body."""
    if type(kind) is not str or kind not in _KINDS:
        raise _fail("kind_invalid")
    if kind == "acknowledged":
        if type(acceptance) is not str or acceptance not in _ACCEPTANCE:
            raise _fail("acceptance_invalid")
    elif acceptance is not None:
        raise _fail("acceptance_not_allowed")
    if kind == "terminal":
        if type(terminal_state) is not str or terminal_state not in _TERMINAL:
            raise _fail("terminal_state_invalid")
    elif terminal_state is not None:
        raise _fail("terminal_state_not_allowed")
    key = (
        idempotency_key_for(
            source=source,
            kind=kind,
            handoff_id=handoff_id,
            originating_agent_id=originating_agent_id,
            originating_producer_run_id=originating_producer_run_id,
            receiving_agent_id=receiving_agent_id,
            event_time=event_time,
            receiving_producer_run_id=receiving_producer_run_id,
            outcome_correlation_id=outcome_correlation_id,
            acceptance=acceptance,
            terminal_state=terminal_state,
        )
        if idempotency_key is None
        else _text(idempotency_key, _KEY200, "idempotency_key")
    )
    members: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": _text(source, _SOURCE, "source"),
        "handoff_id": _text(handoff_id, _KEY128, "handoff_id"),
        "kind": kind,
        "idempotency_key": key,
        "originating_agent_id": _uuid(originating_agent_id, "originating_agent_id"),
        "originating_producer_run_id": _text(
            originating_producer_run_id, _RUN_ID, "originating_producer_run_id"
        ),
        "receiving_agent_id": _uuid(receiving_agent_id, "receiving_agent_id"),
    }
    receiving_run = _optional(
        receiving_producer_run_id, _RUN_ID, "receiving_producer_run_id"
    )
    if receiving_run is not None:
        members["receiving_producer_run_id"] = receiving_run
    correlation = _optional(outcome_correlation_id, _KEY128, "outcome_correlation_id")
    if correlation is not None:
        members["outcome_correlation_id"] = correlation
    members["event_time"] = _instant(event_time)
    if acceptance is not None:
        members["acceptance"] = acceptance
    if terminal_state is not None:
        members["terminal_state"] = terminal_state
    body = json.dumps(members, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    if len(body) > MAX_BODY_BYTES:  # unreachable with the bounds; defensive
        raise _fail("body_too_large")
    return HandoffEvent(members, body)


idempotency_key_for = idempotency_key

"""Experimental, opt-in, bounded emitter of content-free P25 handoff events.

Disabled by default: a disabled emitter starts no thread, opens no socket and sends
nothing. When enabled it keeps a bounded in-memory buffer (events and bytes), delivers
from one daemon worker with capped exponential backoff, and never raises into or
blocks application code. Delivery is at-least-once with idempotency keys; events still
buffered when the process dies, dropped on overflow, or whose attempts or age are
exhausted are lost and counted. A 404 or 405 from the route marks the platform
``unsupported`` for the life of the process: there is no protocol downgrade.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import math
import os
import random
import threading
import time
import weakref
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Final, Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from ._contract import (
    HANDOFF_EVENTS_PATH,
    SCHEMA_VERSION,
    Acceptance,
    HandoffEvent,
    HandoffValidationError,
    Kind,
    TerminalState,
    build_event,
    valid_source,
)

MAX_COUNT: Final = 2**53 - 1
_MAX_RESPONSE: Final = 65536

Overflow = Literal["drop_oldest", "drop_newest"]
Disposition = Literal[
    "queued", "disabled", "invalid", "dropped", "unsupported", "closed", "error"
]
State = Literal["disabled", "active", "unsupported", "closed"]


class HandoffConfigError(ValueError):
    """Invalid emitter configuration. Fixed-label message, never a value."""


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status: int
    headers: Mapping[str, str]  # lower-case names
    body: bytes


class Transport(Protocol):
    """Sends one POST. Raises on any network failure; never follows redirects."""

    def __call__(
        self, url: str, body: bytes, headers: Mapping[str, str], timeout: float
    ) -> TransportResponse: ...


@dataclass(frozen=True, slots=True)
class HandoffEmitterConfig:
    """Closed configuration. ``enabled`` defaults to False (nothing is ever sent)."""

    enabled: bool = False
    base_url: str | None = None
    credential_provider: Callable[[], str] | None = field(default=None, repr=False)
    source: str = "agent-reliability"
    max_events: int = 256
    max_bytes: int = 1024 * 1024
    overflow: Overflow = "drop_oldest"
    max_attempts: int = 5
    max_event_age_seconds: float = 300.0
    backoff_base_seconds: float = 0.5
    backoff_cap_seconds: float = 30.0
    retry_after_cap_seconds: float = 60.0
    request_timeout_seconds: float = 10.0


@dataclass(frozen=True, slots=True)
class HandoffEmitterStats:
    """Counters and state: fixed labels and integers, never evidence or a secret."""

    state: State
    queued_events: int
    queued_bytes: int
    submitted: int  # accepted into the buffer
    delivered_created: int  # 201
    delivered_duplicate: int  # 200 (identical replay)
    rejected: int  # not retried: 401/403/409 conflict/413/422/other
    rejected_invalid: int  # failed client-side validation, never queued
    retries: int
    dropped_buffer_full: int  # overflow (oldest evicted or newest refused)
    lost_exhausted: int  # attempts or max age exhausted
    dropped_unsupported: int  # discarded because the platform is unsupported
    dropped_closed: int  # emitted after close, or abandoned at close
    unsupported_responses: int
    last_error: str | None  # fixed label


_LIVE: weakref.WeakSet[HandoffEmitter] = weakref.WeakSet()


def _after_fork_in_child() -> None:
    for emitter in list(_LIVE):
        emitter._reset_after_fork()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork_in_child)

_ZERO = HandoffEmitterStats("disabled", 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, None)


@dataclass(slots=True)
class _Item:
    body: bytes
    enqueued: float
    closed: bool = False  # already counted as dropped_closed


def _stdlib_transport(
    url: str, body: bytes, headers: Mapping[str, str], timeout: float
) -> TransportResponse:
    parts = urlsplit(url)
    host = parts.hostname or ""
    cls = (
        http.client.HTTPSConnection
        if parts.scheme == "https"
        else http.client.HTTPConnection
    )
    connection = cls(host, parts.port, timeout=timeout)
    try:
        connection.request("POST", parts.path, body=body, headers=dict(headers))
        response = connection.getresponse()
        data = response.read(_MAX_RESPONSE + 1)
        if len(data) > _MAX_RESPONSE:
            data = b""
        return TransportResponse(
            response.status,
            {k.lower(): v for k, v in response.getheaders()},
            data,
        )
    finally:
        connection.close()


def _valid_base_url(url: object) -> str:
    if type(url) is not str or any(not "!" <= c <= "~" for c in url):
        raise HandoffConfigError("base_url_invalid")
    parts = urlsplit(url)
    try:
        host, _ = parts.hostname, parts.port
    except ValueError:
        raise HandoffConfigError("base_url_invalid") from None
    ok_scheme = parts.scheme == "https" or (
        parts.scheme == "http"
        and host is not None
        and (host == "::1" or host.startswith("127."))
    )
    if (
        not ok_scheme
        or not host
        or parts.username is not None
        or parts.password is not None
        or parts.path.strip("/")
        or parts.query
        or parts.fragment
    ):
        raise HandoffConfigError("base_url_invalid")
    return url.rstrip("/")


def _check(value: object, low: float, high: float, integer: bool = False) -> None:
    ok = (
        type(value) is int
        if integer
        else type(value) in (int, float) and math.isfinite(value)  # type: ignore[arg-type]
    )
    if not ok or not low <= value <= high:  # type: ignore[operator]
        raise HandoffConfigError("capacity_invalid")


class HandoffEmitter:
    """Emit requested / acknowledged / terminal handoff events. See module docstring.

    Thread-safe. Needs a bearer machine credential with ONLY the ``handoff:ingest``
    scope bound to one deployment (the credential proves the reporting agent).
    """

    def __init__(
        self, config: HandoffEmitterConfig, *, _transport: Transport | None = None
    ) -> None:
        if not isinstance(config, HandoffEmitterConfig):
            raise HandoffConfigError("config_invalid")
        self._enabled = config.enabled is True
        self._source = config.source
        self._cond = threading.Condition()
        self._queue: deque[_Item] = deque()
        self._queued_bytes = 0
        self._stats = replace(_ZERO)
        self._busy = False
        self._inflight: _Item | None = None
        self._stop = False
        self._abandon = False
        self._worker: threading.Thread | None = None
        self._wake = threading.Event()
        self._random = random.Random()
        self._transport: Transport = _transport or _stdlib_transport
        self._provider: Callable[[], str] | None = None
        self._url = ""
        self._cfg = config
        _LIVE.add(self)
        if not self._enabled:
            return
        if type(config.source) is not str or not valid_source(config.source):
            raise HandoffConfigError("source_invalid")
        if not callable(config.credential_provider):
            raise HandoffConfigError("credential_provider_required")
        if config.overflow not in ("drop_oldest", "drop_newest"):
            raise HandoffConfigError("overflow_invalid")
        _check(config.max_events, 1, 10_000, True)
        _check(config.max_bytes, 1024, 16 * 1024 * 1024, True)
        _check(config.max_attempts, 1, 10, True)
        _check(config.max_event_age_seconds, 0.01, 3600)
        _check(config.backoff_base_seconds, 0.0, 60)
        _check(config.backoff_cap_seconds, config.backoff_base_seconds, 600)
        _check(config.retry_after_cap_seconds, 0.0, 600)
        _check(config.request_timeout_seconds, 0.05, 60)
        self._url = _valid_base_url(config.base_url) + HANDOFF_EVENTS_PATH
        self._provider = config.credential_provider
        self._stats = replace(_ZERO, state="active")

    def __repr__(self) -> str:
        return f"HandoffEmitter(state={self.stats.state!r})"

    # -- typed helpers ----------------------------------------------------------

    def requested(
        self,
        *,
        handoff_id: str,
        originating_agent_id: UUID | str,
        originating_producer_run_id: str,
        receiving_agent_id: UUID | str,
        receiving_producer_run_id: str | None = None,
        outcome_correlation_id: str | None = None,
        event_time: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> Disposition:
        """The originator delegated to the receiver."""
        return self._emit(
            "requested",
            handoff_id,
            originating_agent_id,
            originating_producer_run_id,
            receiving_agent_id,
            receiving_producer_run_id,
            outcome_correlation_id,
            event_time,
            idempotency_key,
            None,
            None,
        )

    def acknowledged(
        self,
        *,
        handoff_id: str,
        originating_agent_id: UUID | str,
        originating_producer_run_id: str,
        receiving_agent_id: UUID | str,
        acceptance: Acceptance,
        receiving_producer_run_id: str | None = None,
        outcome_correlation_id: str | None = None,
        event_time: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> Disposition:
        """The receiver accepted or declined."""
        return self._emit(
            "acknowledged",
            handoff_id,
            originating_agent_id,
            originating_producer_run_id,
            receiving_agent_id,
            receiving_producer_run_id,
            outcome_correlation_id,
            event_time,
            idempotency_key,
            acceptance,
            None,
        )

    def terminal(
        self,
        *,
        handoff_id: str,
        originating_agent_id: UUID | str,
        originating_producer_run_id: str,
        receiving_agent_id: UUID | str,
        terminal_state: TerminalState,
        receiving_producer_run_id: str | None = None,
        outcome_correlation_id: str | None = None,
        event_time: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> Disposition:
        """The receiver reports its own terminal state (not a verified outcome)."""
        return self._emit(
            "terminal",
            handoff_id,
            originating_agent_id,
            originating_producer_run_id,
            receiving_agent_id,
            receiving_producer_run_id,
            outcome_correlation_id,
            event_time,
            idempotency_key,
            None,
            terminal_state,
        )

    # -- lifecycle --------------------------------------------------------------

    @property
    def stats(self) -> HandoffEmitterStats:
        with self._cond:
            return replace(
                self._stats,
                queued_events=len(self._queue),
                queued_bytes=self._queued_bytes,
            )

    def flush(self, timeout: float) -> HandoffEmitterStats:
        """Wait up to ``timeout`` seconds for the buffer to drain. Never raises."""
        try:
            deadline = time.monotonic() + max(0.0, float(timeout))
            with self._cond:
                while self._queue or self._busy:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._cond.wait(remaining)
        except Exception:
            self._count("rejected_invalid", error="internal")
        return self.stats

    def close(self, timeout: float = 5.0) -> HandoffEmitterStats:
        """Flush, stop, and abandon (count as dropped) what is still buffered."""
        with contextlib.suppress(Exception):
            self.flush(timeout)
            with self._cond:
                self._stop = True
                self._abandon = True
                self._cond.notify_all()
            self._wake.set()
            worker = self._worker
            if worker is not None:
                worker.join(max(0.1, min(float(timeout), 5.0)))
            with self._cond:
                leftover = len(self._queue)
                inflight = self._inflight
                if inflight is not None and not inflight.closed:
                    inflight.closed = True
                    leftover += 1
                if leftover:
                    self._bump("dropped_closed", leftover)
                self._queue.clear()
                self._queued_bytes = 0
                self._stats = replace(self._stats, state="closed")
        return self.stats

    def _reset_after_fork(self) -> None:
        # Runs in the child only, single-threaded: the parent's worker thread does
        # not exist here and its lock may be held. Events buffered at fork time
        # belong to the parent, which still delivers them: the child discards its
        # copy (no duplicate sends) and lazily starts a fresh worker on next emit.
        self._cond = threading.Condition()
        self._queue = deque()
        self._queued_bytes = 0
        self._busy = False
        self._inflight = None
        self._worker = None
        self._wake = threading.Event()

    def __enter__(self) -> HandoffEmitter:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close(5.0)

    # -- internals --------------------------------------------------------------

    def _emit(
        self,
        kind: Kind,
        handoff_id: str,
        originating_agent_id: UUID | str,
        originating_run: str,
        receiving_agent_id: UUID | str,
        receiving_run: str | None,
        correlation: str | None,
        event_time: datetime | None,
        key: str | None,
        acceptance: Acceptance | None,
        terminal_state: TerminalState | None,
    ) -> Disposition:
        try:
            if not self._enabled:
                return "disabled"
            event = build_event(
                source=self._source,
                kind=kind,
                handoff_id=handoff_id,
                originating_agent_id=originating_agent_id,
                originating_producer_run_id=originating_run,
                receiving_agent_id=receiving_agent_id,
                receiving_producer_run_id=receiving_run,
                outcome_correlation_id=correlation,
                event_time=datetime.now(UTC) if event_time is None else event_time,
                acceptance=acceptance,
                terminal_state=terminal_state,
                idempotency_key=key,
            )
        except HandoffValidationError as error:
            self._count("rejected_invalid", error=str(error))
            return "invalid"
        except Exception:
            self._count("rejected_invalid", error="internal")
            return "error"
        try:
            return self._admit(event)
        except Exception:
            self._count("rejected_invalid", error="internal")
            return "error"

    def _admit(self, event: HandoffEvent) -> Disposition:
        size = len(event.body)
        with self._cond:
            if self._stop:
                self._bump("dropped_closed")
                return "closed"
            if self._stats.state == "unsupported":
                self._bump("dropped_unsupported")
                return "unsupported"
            cfg = self._cfg
            if size > cfg.max_bytes:
                self._bump("dropped_buffer_full")
                return "dropped"
            if cfg.overflow == "drop_newest":
                if (
                    len(self._queue) >= cfg.max_events
                    or self._queued_bytes + size > cfg.max_bytes
                ):
                    self._bump("dropped_buffer_full")
                    self._set_error("buffer_full")
                    return "dropped"
            else:
                while self._queue and (
                    len(self._queue) >= cfg.max_events
                    or self._queued_bytes + size > cfg.max_bytes
                ):
                    old = self._queue.popleft()
                    self._queued_bytes -= len(old.body)
                    self._bump("dropped_buffer_full")
                    self._set_error("buffer_full")
            self._queue.append(_Item(event.body, time.monotonic()))
            self._queued_bytes += size
            self._bump("submitted")
            if self._worker is None:
                self._worker = threading.Thread(
                    target=self._run, name="gentlity-handoff-emitter", daemon=True
                )
                self._worker.start()
            self._cond.notify_all()
        return "queued"

    def _bump(self, name: str, amount: int = 1) -> None:  # caller holds the lock
        self._stats = replace(
            self._stats, **{name: min(MAX_COUNT, getattr(self._stats, name) + amount)}
        )

    def _set_error(self, label: str) -> None:  # caller holds the lock
        self._stats = replace(self._stats, last_error=label)

    def _count(self, name: str, *, error: str | None = None) -> None:
        with contextlib.suppress(Exception), self._cond:
            self._bump(name)
            if error is not None:
                self._set_error(error)

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._queue and not self._stop:
                    self._cond.wait(0.5)
                if self._abandon or not self._queue:
                    return
                item = self._queue.popleft()
                self._queued_bytes -= len(item.body)
                self._busy = True
                self._inflight = item
            try:
                self._deliver(item)
            except BaseException:
                self._count("lost_exhausted", error="internal")
            finally:
                with self._cond:
                    self._busy = False
                    self._inflight = None
                    self._cond.notify_all()

    def _deliver(self, item: _Item) -> None:
        cfg = self._cfg
        label = "network"
        for attempt in range(1, cfg.max_attempts + 1):
            if self._abandon:
                with self._cond:
                    if not item.closed:
                        item.closed = True
                        self._bump("dropped_closed")
                return
            if time.monotonic() - item.enqueued > cfg.max_event_age_seconds:
                break
            if attempt > 1:
                self._count("retries")
            verdict, delay, label = self._attempt(item.body)
            if verdict == "done":
                return
            if verdict == "stop":
                return
            if attempt == cfg.max_attempts:
                break
            backoff = min(
                cfg.backoff_cap_seconds, cfg.backoff_base_seconds * 2 ** (attempt - 1)
            )
            pause = (
                min(delay, cfg.retry_after_cap_seconds)
                if delay is not None
                else backoff * (0.5 + 0.5 * self._random.random())
            )
            self._wake.wait(pause)  # close() interrupts the backoff
        self._count("lost_exhausted", error=label)

    def _reject(self, label: str) -> tuple[str, float | None, str]:
        self._count("rejected", error=label)
        return "stop", None, label

    def _attempt(self, body: bytes) -> tuple[str, float | None, str]:
        """One request. Returns (done|stop|retry, retry-after seconds, fixed label)."""
        provider = self._provider
        token = ""
        try:
            token = provider() if provider is not None else ""
        except BaseException:
            token = ""
        if (
            type(token) is not str
            or not token
            or any(not "!" <= c <= "~" for c in token)
        ):
            return "retry", None, "credential_unavailable"
        try:
            response = self._transport(
                self._url,
                body,
                {
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
                self._cfg.request_timeout_seconds,
            )
        except Exception:  # message may embed the credential: never kept
            return "retry", None, "network"
        finally:
            token = ""
        status = response.status
        parsed = _json_object(response.body)
        if (
            parsed is not None
            and "schema_version" in parsed
            and (
                type(parsed["schema_version"]) is not int
                or parsed["schema_version"] != SCHEMA_VERSION
            )
        ):
            return self._reject("schema_mismatch")
        if status in (404, 405):
            self._mark_unsupported()
            return "stop", None, "unsupported"
        if status in (200, 201):
            if parsed is None or type(parsed.get("event_id")) is not str:
                return self._reject("bad_acknowledgement")
            self._count("delivered_created" if status == 201 else "delivered_duplicate")
            return "done", None, ""
        code = _error_code(parsed)
        if status == 409 and code == "run_not_yet_known":
            return "retry", None, "run_not_yet_known"
        if status == 429 and code != "handoff_limit_exceeded":
            return "retry", _retry_after(response.headers), "rate_limited"
        if 500 <= status <= 599:
            return "retry", None, f"http_{status}"
        return self._reject(f"http_{status}")

    def _mark_unsupported(self) -> None:
        with self._cond:
            self._bump("unsupported_responses")
            self._bump("dropped_unsupported", 1 + len(self._queue))
            self._queue.clear()
            self._queued_bytes = 0
            self._stats = replace(
                self._stats, state="unsupported", last_error="unsupported"
            )


def _json_object(body: bytes) -> dict[str, Any] | None:
    try:
        value = json.loads(body.decode("utf-8", errors="strict"))
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _error_code(parsed: dict[str, Any] | None) -> str | None:
    error = None if parsed is None else parsed.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) else None


def _retry_after(headers: Mapping[str, str]) -> float | None:
    value = headers.get("retry-after")
    if type(value) is not str or not value.isascii() or not value.isdigit():
        return None
    return float(int(value[:10]))

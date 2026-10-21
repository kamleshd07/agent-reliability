"""Shared, serialized P28 delivery state; transport I/O lives in the adapters."""

from __future__ import annotations

import enum
import json
import math
import os
import random
import re
import threading
import time
from collections import Counter, OrderedDict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

from agent_reliability.adapters._http_protocol import (
    canonical_digest,
    classify_acknowledgement,
    loopback_url,
    retry_after,
    valid_https_endpoint,
)
from agent_reliability.domain import AgentIdentity
from agent_reliability.domain.measurement_health import MeasurementHealthReport
from agent_reliability.evaluation import EvaluationExecutionFailure
from agent_reliability.ports.events import (
    EvaluationRecorded,
    InstrumentationEvent,
    RunCompleted,
    RunFailed,
    RunStarted,
)


class EventDeliveryRejected(Exception):
    """Fixed, redacted local rejection code; contains no evidence or credentials."""


class ExporterClosed(EventDeliveryRejected):
    pass


class ConfigurationFailedError(EventDeliveryRejected):
    pass


class ConfigurationError(Exception):
    pass


class DeliveryDisposition(enum.StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    COMMITTED = "committed"
    DUPLICATE = "duplicate"
    RETRY_SCHEDULED = "retry_scheduled"
    RATE_LIMITED = "rate_limited"
    AUTH_PAUSED = "auth_paused"
    SCHEMA_PAUSED = "schema_paused"
    DEPLOYMENT_UNAVAILABLE = "deployment_unavailable"
    ENDPOINT_PAUSED = "endpoint_paused"
    CONFIGURATION_FAILED = "configuration_failed"
    RETRY_EXHAUSTED = "retry_exhausted"
    PERMANENTLY_FAILED = "permanently_failed"
    INDETERMINATE = "indeterminate"
    OVERFLOWED = "overflowed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class DeliveryRecordStatus:
    event_id: str
    disposition: DeliveryDisposition
    error_code: str | None = None
    may_have_committed: bool = False


@dataclass(frozen=True)
class DeliveryStatusSnapshot:
    queue_depth: int
    high_water_mark: int
    counts_by_disposition: Mapping[DeliveryDisposition, int]
    oldest_queued_age: timedelta | None
    recent_records: tuple[DeliveryRecordStatus, ...]
    pause_reason: str | None
    resume_not_before: datetime | None
    active_binding_count: int
    oldest_binding_age: timedelta | None
    unclassified_422_count: int
    closure_reserve_rejections: int
    late_response_discarded: int
    late_credential_result_discarded: int
    provider_call_outstanding: int
    exhausted_may_have_committed: int
    terminal_tombstone_count: int
    tombstones_evicted: int
    sink_state: str


_OPAQUE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._:/-]{0,198}[A-Za-z0-9])?")
_KEY = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_EXCEPTION = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,199}")
_EDGE = (
    frozenset(range(9, 14))
    | frozenset(range(28, 33))
    | frozenset([0x85, 0xA0, 0x1680, 0x2028, 0x2029, 0x202F, 0x205F, 0x3000])
    | frozenset(range(0x2000, 0x200B))
)


def text(value: Any, limit: int, code: str) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise EventDeliveryRejected(code)
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise EventDeliveryRejected("string_not_unicode")
    if (
        ord(value[0]) in _EDGE
        or ord(value[-1]) in _EDGE
        or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value)
    ):
        raise EventDeliveryRejected(code)
    return value


def frozen_allowlist(values: Any) -> frozenset[str] | None:
    """Snapshot an optional indicator allow-list so later mutation cannot widen it."""
    if values is None:
        return None
    if isinstance(values, str):
        raise ConfigurationError("indicator_allowlist_invalid")
    try:
        # Exact ``str`` copies: a subclass cannot lie about equality, hash or contents.
        return frozenset(
            str.__add__("", v) if isinstance(v, str) and type(v) is not str else v
            for v in values
        )
    except TypeError:
        raise ConfigurationError("indicator_allowlist_invalid") from None


def opaque(value: Any, code: str) -> str:
    if not isinstance(value, str) or not _OPAQUE.fullmatch(value):
        raise EventDeliveryRejected(code)
    return value


def instant(value: datetime) -> str:
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise EventDeliveryRejected("timestamp_naive")
        return value.astimezone(UTC).isoformat()
    except (OverflowError, ValueError, AttributeError):
        raise EventDeliveryRejected("timestamp_out_of_range") from None


def duration(value: float, code: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (float, int))
        or not math.isfinite(value)
        or value < 0
    ):
        raise ConfigurationError(code)
    return float(value)


@dataclass(frozen=True, repr=False)
class Config:
    endpoint: str
    credential_provider: Callable[[], str]
    deployment_id: UUID
    expected_agent: AgentIdentity
    max_queue_records: int = 1000
    max_queue_bytes: int = 4 * 1024 * 1024
    retry_max_attempts: int = 3
    active_delivery_seconds: float = 75
    maximum_residence_seconds: float = 900
    max_throttle_responses: int = 3
    max_active_run_age: float | None = None
    closure_reserve_records: int = 50
    closure_reserve_bytes: int = 3 * 1024 * 1024
    provider_timeout: float = 60
    indicator_allowlist: frozenset[str] | None = None
    allow_unrestricted_indicators: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, str) or not (
            valid_https_endpoint(self.endpoint)
            or loopback_url(self.endpoint, literal_only=True) == "accept"
        ):
            raise ConfigurationError("endpoint_invalid")
        if not callable(self.credential_provider) or not isinstance(
            self.deployment_id, UUID
        ):
            raise ConfigurationError("binding_invalid")
        try:
            agent = self.expected_agent
            if (
                not isinstance(agent, AgentIdentity)
                or not _KEY.fullmatch(agent.agent_id)
                or not isinstance(agent.environment, str)
                or not _KEY.fullmatch(agent.environment)
            ):
                raise ConfigurationError("identity_invalid")
            text(agent.version, 120, "version_invalid")
        except (EventDeliveryRejected, TypeError, AttributeError):
            raise ConfigurationError("identity_invalid") from None
        for name in (
            "max_queue_records",
            "max_queue_bytes",
            "retry_max_attempts",
            "max_throttle_responses",
            "closure_reserve_records",
            "closure_reserve_bytes",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ConfigurationError("capacity_invalid")
        if (
            self.closure_reserve_records >= self.max_queue_records
            or self.closure_reserve_bytes >= self.max_queue_bytes
        ):
            raise ConfigurationError("closure_reserve_invalid")
        if self.max_queue_bytes - self.closure_reserve_bytes < 65536:
            raise ConfigurationError("ordinary_record_headroom_invalid")
        for name in (
            "active_delivery_seconds",
            "maximum_residence_seconds",
            "provider_timeout",
        ):
            if duration(getattr(self, name), name) == 0:
                raise ConfigurationError("timeout_invalid")
        if self.max_active_run_age is not None:
            duration(self.max_active_run_age, "run_age_invalid")
        if type(self.allow_unrestricted_indicators) is not bool:
            raise ConfigurationError("indicator_policy_invalid")
        if self.indicator_allowlist is None and not self.allow_unrestricted_indicators:
            raise ConfigurationError("indicator_policy_required")
        if self.indicator_allowlist is not None and self.allow_unrestricted_indicators:
            raise ConfigurationError("indicator_policy_conflict")
        if self.indicator_allowlist is not None:
            try:
                if not self.indicator_allowlist:
                    raise EventDeliveryRejected("indicator_allowlist_invalid")
                for name in self.indicator_allowlist:
                    text(name, 200, "indicator_allowlist_invalid")
            except (EventDeliveryRejected, TypeError):
                raise ConfigurationError("indicator_allowlist_invalid") from None


@dataclass(repr=False)
class Record:
    event_id: str
    run_id: str
    body: bytes
    digest: str
    accepted: float
    disposition: DeliveryDisposition = DeliveryDisposition.QUEUED
    code: str | None = None
    uncertain: bool = False
    attempts: int = 0
    throttles: int = 0
    retries: int = 0
    ready: float = 0
    active: float = 0
    ticking: float | None = None
    sending: bool = False
    sent: bool = False
    generation: int = 0

    def status(self) -> DeliveryRecordStatus:
        return DeliveryRecordStatus(
            self.event_id, self.disposition, self.code, self.uncertain
        )


@dataclass(repr=False)
class ProviderRead:
    kind: str
    started: float
    done: threading.Event = field(default_factory=threading.Event)


class Core:
    """Every state transition is under lock; no user callback or I/O is under it."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.lock = threading.RLock()
        self.pid = os.getpid()
        self.provider_dispatch: Callable[[Callable[[], None]], None] = lambda action: (
            action()
        )
        self.records: OrderedDict[str, Record] = OrderedDict()
        self.bindings: dict[str, tuple[str | None, float]] = {}
        self.tombstones: OrderedDict[str, float] = OrderedDict()
        self.final_health_runs: set[str] = set()
        self.history: deque[tuple[float, DeliveryRecordStatus]] = deque(maxlen=1000)
        self.counts: Counter[DeliveryDisposition] = Counter()
        self.counters: Counter[str] = Counter()
        self.high_water = 0
        self.lifecycle = "open"
        self.failed = False
        self.gates: set[str] = set()
        self.auth = ""
        self.auth_label = "auth_paused"
        self.rate_until = 0.0
        self.close_deadline = math.inf
        self.credential: str | None = None
        self.baseline: str | None = None
        self.generation = 0
        self.refreshed = False
        self.refresh_completed = -math.inf
        self.read: ProviderRead | None = None
        self.call: ProviderRead | None = None
        self.streak: tuple[Any, int] = (None, 0)
        self.tls_streak = 0

    def assert_pid(self) -> None:
        if os.getpid() != self.pid:
            raise EventDeliveryRejected("fork_unsupported")

    def check(self, *, admission: bool = True) -> None:
        self.assert_pid()
        if self.lifecycle == "closed" or (admission and self.lifecycle == "closing"):
            raise ExporterClosed("exporter_closed")
        if self.failed:
            raise ConfigurationFailedError("configuration_failed")

    def _gate(self) -> str | None:
        if self.auth:
            return "auth_refreshing" if self.auth == "refreshing" else self.auth_label
        for name in (
            "deployment_unavailable",
            "schema_paused",
            "endpoint_paused",
            "rate_gated",
        ):
            if name in self.gates:
                return name
        return None

    def _pause(self, record: Record, now: float) -> None:
        if record.ticking is not None:
            record.active += now - record.ticking
            record.ticking = None
        record.ready = 0
        code = self._gate()
        record.code = code
        record.disposition = {
            "auth_paused": DeliveryDisposition.AUTH_PAUSED,
            "credential_invalid_local": DeliveryDisposition.AUTH_PAUSED,
            "auth_refreshing": DeliveryDisposition.AUTH_PAUSED,
            "deployment_unavailable": DeliveryDisposition.DEPLOYMENT_UNAVAILABLE,
            "schema_paused": DeliveryDisposition.SCHEMA_PAUSED,
            "endpoint_paused": DeliveryDisposition.ENDPOINT_PAUSED,
            "rate_gated": DeliveryDisposition.RATE_LIMITED,
        }.get(code or "", DeliveryDisposition.QUEUED)

    def _sync_gates(self, now: float) -> None:
        if self._gate():
            for record in self.records.values():
                if not record.sending:
                    self._pause(record, now)
        else:
            held = {
                DeliveryDisposition.AUTH_PAUSED,
                DeliveryDisposition.SCHEMA_PAUSED,
                DeliveryDisposition.DEPLOYMENT_UNAVAILABLE,
                DeliveryDisposition.RATE_LIMITED,
                DeliveryDisposition.ENDPOINT_PAUSED,
            }
            for record in self.records.values():
                if record.disposition in held:
                    record.disposition = DeliveryDisposition.QUEUED
                    record.code = None
                    record.ready = 0

    def _terminal(
        self, record: Record, disposition: DeliveryDisposition, code: str | None = None
    ) -> None:
        if record.event_id not in self.records:
            return
        if disposition not in (
            DeliveryDisposition.COMMITTED,
            DeliveryDisposition.DUPLICATE,
            DeliveryDisposition.CANCELLED,
        ):
            now = time.monotonic()
            active = record.active + (
                now - record.ticking if record.ticking is not None else 0
            )
            # R5 gives bounds precedence over every non-ACK response outcome.
            if now - record.accepted > self.config.maximum_residence_seconds:
                disposition = DeliveryDisposition.RETRY_EXHAUSTED
                code = self._gate() or "residence_exceeded"
            elif active > self.config.active_delivery_seconds:
                disposition = DeliveryDisposition.RETRY_EXHAUSTED
                code = "active_time_exceeded"
        if disposition in (
            DeliveryDisposition.COMMITTED,
            DeliveryDisposition.DUPLICATE,
        ):
            record.uncertain = False
        elif record.sending and record.sent:
            record.uncertain = True
        record.disposition, record.code = disposition, code
        self.records.pop(record.event_id)
        self.counts[disposition] += 1
        self.history.append((time.monotonic(), record.status()))
        if (
            disposition
            in (DeliveryDisposition.RETRY_EXHAUSTED, DeliveryDisposition.CANCELLED)
            and record.uncertain
        ):
            self.counters["exhausted_may_have_committed"] += 1
        record.body = b""

    def _abandon_read(self, *, timeout: bool = False) -> None:
        if self.read:
            read = self.read
            self.read = None
            if timeout:
                self.auth = "paused"
                self.auth_label = "credential_invalid_local"
                if read.kind != "dispatch":
                    self.refresh_completed = time.monotonic()
            read.done.set()

    def tick(self) -> None:
        now = time.monotonic()
        if self.read and now - self.read.started >= self.config.provider_timeout:
            self._abandon_read(timeout=True)
        if self.lifecycle == "closed":
            return
        if now >= self.rate_until:
            self.gates.discard("rate_gated")
        self._sync_gates(now)
        for record in list(self.records.values()):
            active = record.active + (
                now - record.ticking if record.ticking is not None else 0
            )
            if now - record.accepted > self.config.maximum_residence_seconds:
                self._terminal(
                    record,
                    DeliveryDisposition.RETRY_EXHAUSTED,
                    self._gate() or "residence_exceeded",
                )
            elif active > self.config.active_delivery_seconds:
                self._terminal(
                    record, DeliveryDisposition.RETRY_EXHAUSTED, "active_time_exceeded"
                )
        if self.config.max_active_run_age is not None:
            for run_id, (_parent, started) in list(self.bindings.items()):
                if now - started > self.config.max_active_run_age:
                    self.release_run(run_id)
        for run_id, ended in list(self.tombstones.items()):
            if now - ended > 600:
                del self.tombstones[run_id]
        while self.history and now - self.history[0][0] > 86400:
            self.history.popleft()
        if self.lifecycle == "closing" and (
            not self.records or now >= self.close_deadline
        ):
            if now >= self.close_deadline:
                self._abandon_read(timeout=True)
            for record in list(self.records.values()):
                self._terminal(record, DeliveryDisposition.CANCELLED, "close_deadline")
            self._abandon_read()
            self.lifecycle = "closed"
            self.credential = self.baseline = None
            self.bindings.clear()
            self.final_health_runs.clear()
            self.tombstones.clear()

    def snapshot(self) -> DeliveryStatusSnapshot:
        self.assert_pid()
        with self.lock:
            self.tick()
            now = time.monotonic()
            rows = tuple(status for _at, status in self.history) + tuple(
                r.status() for r in self.records.values()
            )
            counts = self.counts.copy()
            counts.update(r.disposition for r in self.records.values())
            gate = self._gate()
            state = (
                self.lifecycle
                if self.lifecycle != "open"
                else (
                    "configuration_failed"
                    if self.failed
                    else (
                        "auth_paused"
                        if gate == "credential_invalid_local"
                        else gate or "open"
                    )
                )
            )
            oldest = min((r.accepted for r in self.records.values()), default=None)
            binding_age = min(
                (at for _parent, at in self.bindings.values()), default=None
            )
            return DeliveryStatusSnapshot(
                len(self.records),
                self.high_water,
                MappingProxyType(dict(counts)),
                timedelta(seconds=now - oldest) if oldest is not None else None,
                rows[-1000:],
                "configuration_failed" if self.failed else gate,
                datetime.now(UTC) + timedelta(seconds=max(0, self.rate_until - now))
                if "rate_gated" in self.gates
                else None,
                len(self.bindings),
                timedelta(seconds=now - binding_age)
                if binding_age is not None
                else None,
                self.counters["unclassified_422_count"],
                self.counters["closure_reserve_rejections"],
                self.counters["late_response_discarded"],
                self.counters["late_credential_result_discarded"],
                self.counters["provider_call_outstanding"],
                self.counters["exhausted_may_have_committed"],
                len(self.tombstones),
                self.counters["tombstones_evicted"],
                state,
            )

    def release_run(self, run_id: str) -> None:
        # Never raises, including after fork, close or duplicate release.
        if os.getpid() != self.pid:
            return
        with self.lock:
            if os.getpid() != self.pid or run_id not in self.bindings:
                return
            del self.bindings[run_id]
            self.final_health_runs.discard(run_id)
            self.tombstones[run_id] = time.monotonic()
            while len(self.tombstones) > 1024:
                self.tombstones.popitem(last=False)
                self.counters["tombstones_evicted"] += 1

    def emit(self, event: InstrumentationEvent) -> None:
        try:
            self._emit(event)
        except (TypeError, ValueError, AttributeError, OverflowError):
            raise EventDeliveryRejected("wire_field_rejected") from None

    def _emit(self, event: InstrumentationEvent) -> None:
        self.assert_pid()
        with self.lock:
            self.check()
            self.tick()
            payload: dict[str, Any]
            started = isinstance(event, RunStarted)
            if isinstance(event, RunStarted):
                if event.agent != self.config.expected_agent:
                    raise EventDeliveryRejected("identity_mismatch_local")
                opaque(event.run_id, "run_id_unsupported")
                if event.parent_run_id is not None:
                    opaque(event.parent_run_id, "run_id_unsupported")
                    if event.parent_run_id == event.run_id:
                        raise EventDeliveryRejected("run_id_unsupported")
                if event.run_id in self.bindings or event.run_id in self.tombstones:
                    raise EventDeliveryRejected("run_already_bound")
                if len(self.bindings) >= 1000:
                    raise EventDeliveryRejected("binding_capacity_exhausted")
                parent = event.parent_run_id
                payload = {
                    "kind": "run_lifecycle",
                    "status": "started",
                    "occurred_at": instant(event.started_at),
                    "exception_type": None,
                }
                at = event.started_at
                closure = False
            else:
                if not isinstance(event, (RunCompleted, RunFailed, EvaluationRecorded)):
                    raise EventDeliveryRejected("unsupported_event")
                parent = self._binding(event.run_id)
                closure = isinstance(event, (RunCompleted, RunFailed))
                if isinstance(event, (RunCompleted, RunFailed)):
                    at = event.ended_at
                    payload = {
                        "kind": "run_lifecycle",
                        "status": event.status.value
                        if isinstance(event, RunFailed)
                        else "completed",
                        "occurred_at": instant(at),
                        "exception_type": self._exception(event.exception_type)
                        if isinstance(event, RunFailed)
                        else None,
                    }
                else:
                    assert isinstance(event, EvaluationRecorded)
                    at = event.recorded_at
                    provenance = None
                    if event.provenance:
                        identity = event.provenance.identity
                        provenance = {
                            "name": opaque(identity.name, "evaluator_name_unsupported"),
                            "version": opaque(
                                identity.version, "evaluator_version_unsupported"
                            ),
                            "configuration_id": opaque(
                                identity.configuration_id,
                                "evaluator_version_unsupported",
                            )
                            if identity.configuration_id is not None
                            else None,
                            "deterministic": event.provenance.deterministic,
                        }
                    payload = {
                        "kind": "evaluation_outcome",
                        "evaluation_id": "eval_" + uuid4().hex,
                        "indicator": self._indicator(event.indicator),
                        "outcome": event.outcome.value,
                        "recorded_at": instant(at),
                        "provenance": provenance,
                        "reason_code": opaque(
                            event.reason_code, "reason_code_unsupported"
                        )
                        if event.reason_code is not None
                        else None,
                    }
            self._admit(event.run_id, parent, payload, at, closure)
            if started:
                self.bindings[event.run_id] = (parent, time.monotonic())

    def _binding(self, run_id: str) -> str | None:
        if run_id not in self.bindings:
            raise EventDeliveryRejected(
                "run_released" if run_id in self.tombstones else "unknown_run"
            )
        return self.bindings[run_id][0]

    def _indicator(self, value: Any) -> str:
        if type(value) is not str and isinstance(value, str):
            # Work on an exact ``str`` copy so a subclass cannot lie about its
            # contents, length or equality between validation and serialisation.
            value = str.__add__("", value)
        checked = text(value, 200, "indicator_unsupported")
        allowed = self.config.indicator_allowlist
        if allowed is not None and checked not in allowed:
            self.counters["indicator_not_allowed"] += 1
            raise EventDeliveryRejected("indicator_not_allowed")
        return checked

    def _exception(self, name: str) -> str:
        if not _EXCEPTION.fullmatch(name):
            self.counters["exception_type_substituted"] += 1
            return "Exception"
        return name

    def _admit(
        self,
        run_id: str,
        parent: str | None,
        payload: dict[str, Any],
        at: datetime,
        closure: bool,
    ) -> None:
        event_id = "evt_" + uuid4().hex
        agent = self.config.expected_agent
        envelope = {
            "schema_version": 2,
            "source": "agent-reliability",
            "event_id": event_id,
            "producer_run_id": run_id,
            "parent_producer_run_id": parent,
            "deployment_id": str(self.config.deployment_id),
            "producer_identity": {
                "agent_id": agent.agent_id,
                "version": agent.version,
                "environment": agent.environment,
            },
            "producer_timestamp": instant(at),
            "payload": payload,
        }
        body = json.dumps(
            envelope, ensure_ascii=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        if len(body) > 65536:
            raise EventDeliveryRejected("request_too_large")
        records = self.config.max_queue_records - (
            0 if closure else self.config.closure_reserve_records
        )
        byte_limit = self.config.max_queue_bytes - (
            0 if closure else self.config.closure_reserve_bytes
        )
        if (
            len(self.records) >= records
            or sum(len(r.body) for r in self.records.values()) + len(body) > byte_limit
        ):
            self.counts[DeliveryDisposition.OVERFLOWED] += 1
            if closure:
                self.counters["closure_reserve_rejections"] += 1
            raise EventDeliveryRejected(
                "closure_reserve_exhausted" if closure else "queue_full"
            )
        record = Record(
            event_id, run_id, body, canonical_digest(envelope), time.monotonic()
        )
        if self._gate():
            self._pause(record, time.monotonic())
        self.records[event_id] = record
        self.high_water = max(self.high_water, len(self.records))

    def submit_evaluation_failure(
        self,
        failure: EvaluationExecutionFailure,
        *,
        run_id: str,
        indicator: str,
        evaluation_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        self.assert_pid()
        with self.lock:
            self.check()
            if not isinstance(failure, EvaluationExecutionFailure):
                raise EventDeliveryRejected("failure_unsupported")
            opaque(run_id, "run_id_unsupported")
            parent = self._binding(run_id)
            at = occurred_at if occurred_at is not None else datetime.now(UTC)
            identity = failure.identity
            payload = {
                "kind": "evaluation_execution_failure",
                "evaluation_id": opaque(evaluation_id, "evaluation_id_unsupported")
                if evaluation_id is not None
                else "eval_" + uuid4().hex,
                "indicator": self._indicator(indicator),
                "stage": failure.stage.value,
                "exception_type": self._exception(failure.exception_type),
                "occurred_at": instant(at),
                "evaluator_name": opaque(identity.name, "evaluator_name_unsupported")
                if identity
                else None,
                "evaluator_version": opaque(
                    identity.version, "evaluator_version_unsupported"
                )
                if identity
                else None,
                "evaluator_configuration_id": opaque(
                    identity.configuration_id, "evaluator_version_unsupported"
                )
                if identity and identity.configuration_id is not None
                else None,
            }
            self._admit(run_id, parent, payload, at, False)

    def submit_measurement_health(
        self,
        report: MeasurementHealthReport,
        *,
        run_id: str,
        measurement_id: str | None = None,
        observed_at: datetime | None = None,
    ) -> None:
        self.assert_pid()
        with self.lock:
            self.check()
            if not isinstance(report, MeasurementHealthReport):
                raise EventDeliveryRejected("health_unsupported")
            opaque(run_id, "run_id_unsupported")
            parent = self._binding(run_id)
            if run_id in self.final_health_runs:
                raise EventDeliveryRejected("final_health_already_submitted")
            at = observed_at if observed_at is not None else datetime.now(UTC)
            payload = {
                "kind": "measurement_health",
                "measurement_id": opaque(measurement_id, "measurement_id_unsupported")
                if measurement_id is not None
                else "meas_" + uuid4().hex,
                "health": report.health.value,
                "reasons": sorted(reason.value for reason in report.reasons),
                "observed_at": instant(at),
            }
            self._admit(run_id, parent, payload, at, True)
            self.final_health_runs.add(run_id)

    def start_read(self, kind: str) -> ProviderRead | None:
        if self.read or self.call or self.failed or self.lifecycle == "closed":
            return self.read
        read = ProviderRead(kind, time.monotonic())
        self.read = self.call = read

        def invoke() -> None:
            try:
                result: Any = self.config.credential_provider()
            except BaseException:
                result = None

            def apply_result() -> None:
                with self.lock:
                    self.tick()
                    self.call = None
                    if self.read is not read:
                        self.counters["late_credential_result_discarded"] += 1
                        return
                    self.read = None
                    if read.kind != "dispatch":
                        self.refresh_completed = time.monotonic()
                    valid = (
                        isinstance(result, str)
                        and 1 <= len(result) <= 8185
                        and all("!" <= c <= "~" for c in result)
                    )
                    changed = valid and (
                        self.baseline is None or result != self.baseline
                    )
                    if changed:
                        if result != self.credential:
                            self.generation += 1
                            self.credential = result
                        if (
                            read.kind in ("dispatch", "resume")
                            or self.auth == "refreshing"
                        ):
                            self.auth = ""
                            self.baseline = None
                            if read.kind != "dispatch":
                                self.refreshed = True
                        else:
                            self.auth_label = "auth_paused"
                    else:
                        self.auth = "paused"
                        self.auth_label = (
                            "auth_paused" if valid else "credential_invalid_local"
                        )
                    self._sync_gates(time.monotonic())
                    read.done.set()

            self.provider_dispatch(apply_result)

        threading.Thread(target=invoke, name="gentlity-credential", daemon=True).start()
        return read

    def resume_auth_read(self) -> ProviderRead | None:
        self.assert_pid()
        with self.lock:
            self.check(admission=False)
            self.tick()
            if self.auth != "paused":
                return None
            if self.read:
                self.read.kind = "resume"
                return self.read
            if self.call:
                self.counters["provider_call_outstanding"] += 1
                return None
            return self.start_read("resume")

    def resume(self, gate: str) -> DeliveryStatusSnapshot:
        self.assert_pid()
        with self.lock:
            self.check(admission=False)
            self.gates.discard(gate)
            if gate == "schema_paused":
                self.streak = (None, 0)
            if gate == "endpoint_paused":
                self.tls_streak = 0
            self._sync_gates(time.monotonic())
            return self.snapshot()

    def take(self) -> tuple[Record, str] | None:
        with self.lock:
            self.tick()
            if (
                self.failed
                or self.lifecycle == "closed"
                or self._gate()
                or not self.records
            ):
                return None
            if self.credential is None:
                self.start_read("dispatch")
                return None
            seen: set[str] = set()
            now = time.monotonic()
            for record in self.records.values():
                if record.run_id in seen:
                    continue
                seen.add(record.run_id)
                if record.sending or now < record.ready:
                    continue
                record.sending = True
                record.sent = False
                record.generation = self.generation
                record.disposition = DeliveryDisposition.SENT
                record.code = None
                if record.ticking is None:
                    record.ticking = now
                return record, self.credential
            return None

    def mark_sent(self, record: Record) -> None:
        with self.lock:
            if record.event_id not in self.records:
                raise EventDeliveryRejected("request_abandoned")
            record.sent = True
            record.disposition = DeliveryDisposition.SENT

    def _backoff(self, n: int) -> float:
        return random.uniform(0, min(2, 0.25 * 2 ** min(n - 1, 3)))

    def complete(
        self,
        record: Record,
        status: int = 0,
        body: bytes = b"",
        headers: tuple[str, ...] = (),
        failure: str | None = None,
    ) -> None:
        with self.lock:
            if record.event_id not in self.records or self.lifecycle == "closed":
                self.counters["late_response_discarded"] += 1
                return
            now = time.monotonic()
            record.sending = False
            code: str | None = None
            details: Any = None
            if failure is None:
                self.tls_streak = 0
                try:
                    parsed = (
                        json.loads(body.decode("utf-8")) if len(body) <= 65536 else None
                    )
                    error = parsed.get("error") if isinstance(parsed, dict) else None
                    if isinstance(error, dict) and isinstance(error.get("code"), str):
                        code = error["code"]
                        details = error.get("details")
                except (ValueError, RecursionError):
                    pass
                ack = classify_acknowledgement(status, body, record.event_id)
                if ack.startswith("ack:"):
                    self.streak = (None, 0)
                    self.refreshed = False
                    self._terminal(
                        record,
                        DeliveryDisposition.COMMITTED
                        if status == 201
                        else DeliveryDisposition.DUPLICATE,
                    )
                    return
            if record.sent and (
                failure == "indeterminate"
                or (failure is None and not (400 <= status < 500 and code))
            ):
                record.uncertain = True
            retry = False
            ordinary = False
            if failure:
                ordinary = True
                record.code = failure
                if failure == "tls_verification_failed":
                    self.tls_streak += 1
                    if self.tls_streak >= 3:
                        self.gates.add("endpoint_paused")
                        ordinary = False
            elif status in (401, 403):
                if not self.auth and record.generation == self.generation:
                    self.baseline = self.credential
                    if (
                        status == 401
                        and not self.refreshed
                        and now - self.refresh_completed >= 60
                    ):
                        self.auth = "refreshing"
                        self.start_read("refresh")
                    else:
                        self.auth = "paused"
                        self.auth_label = "auth_paused"
                elif (
                    self.auth == "refreshing"
                    and status == 403
                    and record.generation == self.generation
                ):
                    self.auth = "paused"
                    self.auth_label = "auth_paused"
            elif status == 404 and code == "not_found":
                self.gates.add("deployment_unavailable")
            elif status == 409 and code == "deployment_identity_mismatch":
                self._terminal(record, DeliveryDisposition.PERMANENTLY_FAILED, code)
                self.failed = True
                self._abandon_read()
                for other in list(self.records.values()):
                    self._terminal(
                        other, DeliveryDisposition.CANCELLED, "configuration_failed"
                    )
                return
            elif status == 429:
                record.throttles += 1
                delay = retry_after(headers, grammar="RA-b")
                wait = (
                    self._backoff(record.throttles)
                    if delay is None
                    else min(
                        delay,
                        max(
                            0,
                            self.config.maximum_residence_seconds
                            - (now - record.accepted),
                        ),
                    )
                )
                self.rate_until = max(
                    self.rate_until, now + wait + random.uniform(0, 2)
                )
                self.gates.add("rate_gated")
                if record.throttles > self.config.max_throttle_responses:
                    self._terminal(
                        record, DeliveryDisposition.RETRY_EXHAUSTED, "rate_limited"
                    )
            elif status == 422:
                key: Any = None
                if code == "unsupported_schema_version":
                    key = ("unsupported_schema_version", ())
                elif (
                    code == "validation_error"
                    and isinstance(details, list)
                    and len(details) == 1
                    and isinstance(details[0], dict)
                    and details[0].get("location") == ["body", "producer_identity"]
                ):
                    key = ("validation_error", ("body", "producer_identity"))
                if key:
                    if "schema_paused" not in self.gates:
                        count = self.streak[1] + 1 if self.streak[0] == key else 1
                        self.streak = (key, count)
                        if count >= 3:
                            self.gates.add("schema_paused")
                    retry = True
                    record.code = "compatibility_retry"
                else:
                    self.counters["unclassified_422_count"] += 1
                    self._terminal(
                        record,
                        DeliveryDisposition.PERMANENTLY_FAILED,
                        "unclassified_422",
                    )
            elif 300 <= status < 400:
                self.gates.add("endpoint_paused")
            elif status in (404, 405) and code is None:
                ordinary = True
                record.code = "endpoint_not_found"
            elif status == 408 or status < 200 or 200 <= status < 300 or status >= 500:
                ordinary = True
                record.code = "response_unparseable" if 200 <= status < 300 else None
            else:
                self._terminal(
                    record,
                    DeliveryDisposition.PERMANENTLY_FAILED,
                    code
                    if code
                    in (
                        "conflict",
                        "invalid_transition",
                        "request_too_large",
                        "domain_error",
                        "validation_error",
                    )
                    else "http_permanent_failure",
                )
            if record.event_id in self.records:
                if ordinary:
                    record.attempts += 1
                    retry = True
                    if record.attempts >= self.config.retry_max_attempts:
                        self._terminal(
                            record,
                            DeliveryDisposition.RETRY_EXHAUSTED,
                            "retry_exhausted",
                        )
                if record.event_id in self.records:
                    if self._gate():
                        self._pause(record, now)
                    elif retry:
                        record.retries += 1
                        record.ready = now + self._backoff(record.retries)
                        record.disposition = (
                            DeliveryDisposition.INDETERMINATE
                            if failure == "indeterminate"
                            else DeliveryDisposition.RETRY_SCHEDULED
                        )
                    else:
                        record.disposition = DeliveryDisposition.QUEUED
                        if record.ticking is not None:
                            record.active += now - record.ticking
                            record.ticking = None
            self._sync_gates(now)
            self.tick()

    def begin_close(self, timeout: float) -> None:
        self.assert_pid()
        duration(timeout, "timeout_invalid")
        with self.lock:
            if self.lifecycle not in ("closing", "closed"):
                self.lifecycle = "closing"
                self.close_deadline = time.monotonic() + timeout
            self.tick()

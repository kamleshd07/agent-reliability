"""Bounded normalized collector. No framework, payload, sink or logging dependency."""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from .model import (
    MAX_COUNT,
    TOOL_OUTCOMES,
    CaptureDiagnostics,
    CaptureLimits,
    ExecutionEvent,
    ExecutionState,
    ExecutionTrace,
    RetryObservation,
    SpanKind,
    TokenUsage,
)

# Hard cap for an attempt index: three digits, and far below max_spans.
MAX_RETRY_ATTEMPT = 100


@dataclass(slots=True)
class _Span:
    id: str
    parent: str
    kind: SpanKind
    depth: int
    started_ns: int
    component: str | None
    framework_parent: UUID | None
    tool_class: str | None = None
    action_class: str | None = None
    closed: bool = False
    # Retry corroboration inputs (integers/enums only; the tag itself is never kept).
    # attempt: None = no retry marker, 0 = unusable marker, 2..100 = parsed index.
    attempt: int | None = None
    start_seq: int = 0
    end_seq: int = 0
    state: ExecutionState | None = None


class Collector:
    def __init__(
        self,
        run_id: str,
        parent_run_id: str | None,
        framework_root: UUID,
        limits: CaptureLimits,
        provider_id: str | None,
        model_id: str | None,
        tool_semantics: Mapping[str, tuple[str | None, str | None]] | None = None,
        retry_wrapper_root: bool = False,
    ) -> None:
        # True only when the instrumented object itself is a RunnableRetry, so the
        # root run is a verified retry wrapper. No callback field identifies one.
        self._retry_root = retry_wrapper_root
        self._semantics = tool_semantics or {}
        self.run_id = run_id
        self._parent = parent_run_id
        self._root = framework_root
        self._limits = limits
        self._provider = provider_id
        self._model = model_id
        self._lock = threading.Lock()
        self._spans: dict[UUID, _Span] = {}
        self._events: list[ExecutionEvent] = []
        self._diagnostics = CaptureDiagnostics()
        self._closed = False
        self._started = time.perf_counter_ns()
        self._events.append(
            ExecutionEvent(run_id, 1, run_id, None, "run", "start", datetime.now(UTC))
        )

    def _count(self, field: str) -> None:
        self._diagnostics = replace(
            self._diagnostics,
            **{field: min(MAX_COUNT, getattr(self._diagnostics, field) + 1)},
        )

    def error(self) -> None:
        with self._lock:
            if not self._closed:
                self._count("callback_errors")

    def retry(self) -> None:
        with self._lock:
            if not self._closed:
                self._count("retry_signals")

    def start(
        self,
        key: UUID,
        parent: UUID | None,
        kind: SpanKind,
        component: str | None = None,
        attempt: int | None = None,
    ) -> None:
        with self._lock:
            if self._closed:
                return
            if key in self._spans:
                previous = self._spans[key]
                if (previous.kind, previous.framework_parent, previous.component) != (
                    kind,
                    parent,
                    component,
                ):
                    self._count("callback_errors")
                else:
                    self._count("duplicates")
                return
            if len(self._spans) >= self._limits.max_spans:
                self._count("dropped")
                return
            if key == self._root:
                parent_id, depth = self.run_id, 1
            elif parent in self._spans:
                owner = self._spans[parent]
                if owner.closed:
                    self._count("orphans")
                    return
                parent_id, depth = owner.id, owner.depth + 1
            else:
                self._count("orphans")
                return
            if depth > self._limits.max_depth:
                self._count("dropped")
                return
            span = _Span(
                str(uuid4()),
                parent_id,
                kind,
                depth,
                time.perf_counter_ns(),
                component,
                parent,
                *self._semantics.get(component or "", (None, None)),
                attempt=attempt,
                start_seq=len(self._events) + 1,
            )
            self._spans[key] = span
            self._events.append(
                ExecutionEvent(
                    self.run_id,
                    len(self._events) + 1,
                    span.id,
                    span.parent,
                    kind,
                    "start",
                    datetime.now(UTC),
                    component=component,
                    provider_id=self._provider if kind == "model" else None,
                    model_id=self._model if kind == "model" else None,
                )
            )

    def _end(
        self,
        span: _Span,
        state: ExecutionState,
        usage: TokenUsage | None,
        *,
        synthetic: bool = False,
        outcome: str | None = None,
    ) -> None:
        span.closed = True
        span.state = state
        span.end_seq = len(self._events) + 1
        if span.kind != "tool" or synthetic:
            outcome = None
        elif state == "completed":
            outcome = "success"
        elif state == "cancelled":
            outcome = "cancelled"
        elif outcome not in TOOL_OUTCOMES or outcome in ("success", "cancelled"):
            outcome = "execution_error"
        self._events.append(
            ExecutionEvent(
                self.run_id,
                len(self._events) + 1,
                span.id,
                span.parent,
                span.kind,
                "terminal",
                datetime.now(UTC),
                state,
                None if synthetic else max(0, time.perf_counter_ns() - span.started_ns),
                component=span.component,
                provider_id=self._provider if span.kind == "model" else None,
                model_id=self._model if span.kind == "model" else None,
                usage=(usage or TokenUsage()) if span.kind == "model" else None,
                synthetic=synthetic,
                outcome=outcome,
                tool_class=span.tool_class if span.kind == "tool" else None,
                action_class=span.action_class if span.kind == "tool" else None,
            )
        )

    def end(
        self,
        key: UUID,
        state: ExecutionState,
        usage: TokenUsage | None = None,
        *,
        expected_kind: SpanKind | None = None,
        outcome: str | None = None,
    ) -> None:
        with self._lock:
            if self._closed:
                return
            span = self._spans.get(key)
            if span is None:
                self._count("orphans")
            elif expected_kind is not None and span.kind != expected_kind:
                self._count("callback_errors")
            elif span.closed:
                self._count("duplicates")
            else:
                self._end(span, state, usage, outcome=outcome)

    def _retry_links(
        self,
    ) -> tuple[tuple[tuple[str, str], ...], RetryObservation, int]:
        """Corroborate retry attempts under the verified root wrapper (lock held).

        All-or-nothing: any anomaly yields "unknown" and no links, never a guess.
        """
        if not self._retry_root:
            return (), "not_collected", 0
        root = self._spans.get(self._root)
        if root is None or root.kind != "step" or self._diagnostics.partial:
            return (), "unknown", 0
        kids = sorted(
            (s for s in self._spans.values() if s.framework_parent == self._root),
            key=lambda s: s.start_seq,
        )
        first = kids[0] if kids else None
        if first is None or first.kind == "run":
            return (), "unknown", len(kids)
        if first.kind == "tool" and first.component is None:
            return (), "unknown", len(kids)
        links: list[tuple[str, str]] = []
        for index, span in enumerate(kids):
            expected = None if index == 0 else index + 1
            if expected is not None and expected > MAX_RETRY_ATTEMPT:
                return (), "unknown", len(kids)
            if (
                span.attempt != expected
                or span.kind != first.kind
                or span.component != first.component
            ):
                return (), "unknown", len(kids)
            if index:
                previous = kids[index - 1]
                if (
                    previous.state not in ("failed", "incomplete")
                    or not 0 < previous.end_seq < span.start_seq
                ):
                    return (), "unknown", len(kids)
                links.append((span.id, previous.id))
        return tuple(links), "observed", len(kids)

    def finish(self, state: ExecutionState) -> ExecutionTrace:
        with self._lock:
            self._closed = True
            if not self._spans:
                self._count("unfinished")
            for span in self._spans.values():
                if not span.closed:
                    self._count("unfinished")
                    self._end(
                        span,
                        "cancelled" if state == "cancelled" else "incomplete",
                        None,
                        synthetic=True,
                    )
            self._events.append(
                ExecutionEvent(
                    self.run_id,
                    len(self._events) + 1,
                    self.run_id,
                    None,
                    "run",
                    "terminal",
                    datetime.now(UTC),
                    state,
                    max(0, time.perf_counter_ns() - self._started),
                )
            )
            links, observation, attempts = self._retry_links()
            result = ExecutionTrace(
                self.run_id,
                self._parent,
                tuple(self._events),
                self._diagnostics,
                links,
                observation,
                attempts,
            )
            self._spans.clear()
            self._events.clear()
            return result

"""Bounded normalized collector. No framework, payload, sink or logging dependency."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from .model import (
    MAX_COUNT,
    CaptureDiagnostics,
    CaptureLimits,
    ExecutionEvent,
    ExecutionState,
    ExecutionTrace,
    SpanKind,
    TokenUsage,
)


@dataclass(slots=True)
class _Span:
    id: str
    parent: str
    kind: SpanKind
    depth: int
    started_ns: int
    component: str | None
    framework_parent: UUID | None
    closed: bool = False


class Collector:
    def __init__(
        self,
        run_id: str,
        parent_run_id: str | None,
        framework_root: UUID,
        limits: CaptureLimits,
        provider_id: str | None,
        model_id: str | None,
    ) -> None:
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
    ) -> None:
        span.closed = True
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
            )
        )

    def end(
        self,
        key: UUID,
        state: ExecutionState,
        usage: TokenUsage | None = None,
        *,
        expected_kind: SpanKind | None = None,
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
                self._end(span, state, usage)

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
            result = ExecutionTrace(
                self.run_id, self._parent, tuple(self._events), self._diagnostics
            )
            self._spans.clear()
            self._events.clear()
            return result

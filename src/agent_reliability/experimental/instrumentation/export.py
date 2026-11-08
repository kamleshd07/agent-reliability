"""Neutral, content-free conversion of a local trace to Gentlity execution requests.

Pure functions only: no framework or HTTP import. The wire shapes follow the platform's
execution-structure (P18a), classification (P18b) and model-usage (P20a) contracts.
Only closed vocabularies, bounded identifiers, timestamps and integer token counts leave
the process. Retries are never exported: the platform has no retry field.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from .model import ExecutionEvent, ExecutionTrace

SCHEMA_VERSION = 1
MAX_ITEMS_PER_REQUEST = 50
MAX_STEPS_PER_RUN = 1000
SOURCE = "agent-reliability"

STRUCTURE_PATH = "/api/v1/execution-structures/batches"
CLASSIFICATION_PATH = "/api/v1/execution-classifications/batches"
USAGE_PATH = "/api/v1/execution-model-usage/batches"

_STEP_TYPE = {"step": "other", "tool": "tool", "model": "model"}


class TraceExporter(Protocol):
    """Receives each finished trace. Must be non-blocking and must not raise into
    application code (the wrapper also isolates failures)."""

    def submit(self, trace: ExecutionTrace) -> bool: ...


@dataclass(frozen=True, slots=True)
class ExportRequest:
    path: str
    body: bytes


def instant(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _spans(trace: ExecutionTrace) -> list[tuple[ExecutionEvent, ExecutionEvent | None]]:
    starts: dict[str, ExecutionEvent] = {}
    ends: dict[str, ExecutionEvent] = {}
    order: list[str] = []
    for event in trace.events:
        if event.kind == "run":
            continue
        if event.phase == "start":
            if event.span_id not in starts:
                starts[event.span_id] = event
                order.append(event.span_id)
        else:
            ends.setdefault(event.span_id, event)
    return [(starts[i], ends.get(i)) for i in order[:MAX_STEPS_PER_RUN]]


def _step(
    run_id: str, start: ExecutionEvent, end: ExecutionEvent | None
) -> dict[str, Any]:
    begun = start.at
    state = "started"
    finished: datetime | None = None
    if end is not None and end.state in ("completed", "failed", "cancelled"):
        state = end.state
        finished = (
            begun + timedelta(microseconds=end.duration_ns // 1000)
            if end.duration_ns is not None and not end.synthetic
            else max(end.at, begun)
        )
    component = start.component if start.kind == "tool" else start.model_id
    return {
        "step_id": start.span_id,
        "parent_step_id": None
        if start.parent_span_id == run_id
        else start.parent_span_id,
        "step_type": _STEP_TYPE[start.kind],
        "component_name": component,
        "state": state,
        "started_at": instant(begun),
        "ended_at": None if finished is None else instant(finished),
    }


def _body(fields: dict[str, Any]) -> bytes:
    return json.dumps(fields, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _chunks(items: Sequence[Any]) -> list[Sequence[Any]]:
    return [
        items[i : i + MAX_ITEMS_PER_REQUEST]
        for i in range(0, len(items), MAX_ITEMS_PER_REQUEST)
    ]


def build_requests(
    trace: ExecutionTrace, *, deployment_id: str, source: str = SOURCE
) -> list[ExportRequest]:
    """Ordered requests for one run: structure first, then classification and usage.

    Identifiers are the trace's own random span ids, so retrying the same requests
    is idempotent on the platform.
    """
    spans = _spans(trace)
    if not spans:
        return []
    requests: list[ExportRequest] = []
    steps = [_step(trace.run_id, s, e) for s, e in spans]
    for chunk in _chunks(steps):
        requests.append(
            ExportRequest(
                STRUCTURE_PATH,
                _body(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "source": source,
                        "producer_run_id": trace.run_id,
                        "deployment_id": deployment_id,
                        "steps": list(chunk),
                    }
                ),
            )
        )
    classes = [
        {
            "step_id": s.span_id,
            "classification_revision": 1,
            "tool_class": e.tool_class,
            "action_class": e.action_class,
            "execution_outcome": e.outcome,
        }
        for s, e in spans
        if s.kind == "tool"
        and e is not None
        and (e.tool_class or e.action_class or e.outcome)
    ]
    for chunk in _chunks(classes):
        requests.append(
            ExportRequest(
                CLASSIFICATION_PATH,
                _body(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "source": source,
                        "producer_run_id": trace.run_id,
                        "assertions": list(chunk),
                    }
                ),
            )
        )
    usage = [
        {
            "step_id": s.span_id,
            "usage_revision": 1,
            "total_tokens": e.usage.total_tokens,
            "input_tokens": e.usage.input_tokens,
            "output_tokens": e.usage.output_tokens,
        }
        for s, e in spans
        if s.kind == "model"
        and e is not None
        and e.usage is not None
        and e.usage.availability == "reported"
    ]
    for chunk in _chunks(usage):
        requests.append(
            ExportRequest(
                USAGE_PATH,
                _body(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "source": source,
                        "producer_run_id": trace.run_id,
                        "assertions": list(chunk),
                    }
                ),
            )
        )
    return requests

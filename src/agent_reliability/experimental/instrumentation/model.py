"""Experimental, local-only content-free execution facts (not outcome evaluations)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

SpanKind = Literal["run", "step", "tool", "model"]
ExecutionState = Literal["completed", "failed", "cancelled", "incomplete"]
# Local-only retry observation (P20c M3 spike). Never exported; no wire contract exists.
RetryObservation = Literal["not_collected", "observed", "unknown"]
_ALIAS = re.compile(r"[A-Za-z0-9._-]{1,128}\Z", re.ASCII)
MAX_COUNT = 2**63 - 1

# Closed vocabularies shared with the platform's execution-classification contract.
TOOL_CLASSES = frozenset(
    {
        "data_store",
        "network_api",
        "retrieval",
        "browser",
        "code_execution",
        "file_system",
        "messaging",
        "other",
        "unknown",
    }
)
ACTION_CLASSES = frozenset({"read", "write", "execute", "other", "unknown"})
TOOL_OUTCOMES = frozenset(
    {
        "success",
        "timeout",
        "unavailable",
        "permission_denied",
        "cancelled",
        "execution_error",
    }
)


def alias(value: str) -> str:
    if type(value) is not str or _ALIAS.fullmatch(value) is None:
        raise ValueError(
            "instrumentation identifiers must be safe ASCII logical aliases"
        )
    return value


@dataclass(frozen=True, slots=True)
class CaptureLimits:
    """Local bounds, not a platform component quota or a latency guarantee."""

    max_spans: int = 1000
    max_depth: int = 16
    max_active_runs: int = 32
    max_retained_runs: int = 8

    def __post_init__(self) -> None:
        for value, ceiling in (
            (self.max_spans, 1000),
            (self.max_depth, 16),
            (self.max_active_runs, 128),
            (self.max_retained_runs, 32),
        ):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("invalid instrumentation resource bound")


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Provider-reported integers; missing or invalid total is explicitly unknown."""

    availability: Literal["reported", "unknown"] = "unknown"
    total_tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self) -> None:
        values = (self.total_tokens, self.input_tokens, self.output_tokens)
        if any(
            v is not None and (type(v) is not int or not 0 <= v <= MAX_COUNT)
            for v in values
        ):
            raise ValueError("invalid reported token count")
        if self.availability == "unknown":
            if any(v is not None for v in values):
                raise ValueError("unknown usage has no inferred counts")
        elif self.availability != "reported" or self.total_tokens is None:
            raise ValueError("reported usage requires a total")


@dataclass(frozen=True, slots=True)
class CaptureDiagnostics:
    dropped: int = 0
    duplicates: int = 0
    orphans: int = 0
    callback_errors: int = 0
    unfinished: int = 0
    retry_signals: int = 0

    @property
    def partial(self) -> bool:
        return bool(
            self.dropped or self.orphans or self.callback_errors or self.unfinished
        )


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    run_id: str
    sequence: int
    span_id: str
    parent_span_id: str | None
    kind: SpanKind
    phase: Literal["start", "terminal"]
    at: datetime
    state: ExecutionState | None = None
    duration_ns: int | None = None
    component: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    usage: TokenUsage | None = None
    synthetic: bool = False
    # Tool spans only: a closed technical outcome and optional declared classes.
    # Never derived from names, messages or payloads.
    outcome: str | None = None
    tool_class: str | None = None
    action_class: str | None = None


@dataclass(frozen=True, slots=True)
class ComponentSummary:
    """Per-component execution facts. Duration is callback elapsed time, summed
    over observed spans; nested or concurrent spans overlap, so totals can exceed
    wall-clock time."""

    kind: SpanKind
    component: str | None
    calls: int
    failed: int
    cancelled: int
    incomplete: int
    total_duration_ns: int
    max_duration_ns: int


@dataclass(frozen=True, slots=True)
class ExecutionSummary:
    run_id: str
    state: ExecutionState | None
    duration_ns: int | None
    components: tuple[ComponentSummary, ...]
    total_tokens: int | None
    token_unknown_models: int
    retry_signals: int
    complete: bool
    # Local-only (not exported): see ExecutionTrace.retry_observation.
    retry_observation: RetryObservation = "not_collected"
    retry_link_count: int = 0


@dataclass(frozen=True, slots=True)
class ExecutionTrace:
    run_id: str
    parent_run_id: str | None
    events: tuple[ExecutionEvent, ...]
    diagnostics: CaptureDiagnostics
    # Local-only retry evidence (P20c M3 detection spike). build_requests never reads
    # these fields; there is no public retry-link wire contract. ``retry_links`` holds
    # (retry_span_id, retry_of_span_id) pairs and is non-empty only when
    # ``retry_observation == "observed"``. "not_collected" means the retry context could
    # not be verified (nothing was read); "unknown" means it was verified but the
    # evidence did not corroborate. Neither is ever evidence of "no retry".
    retry_links: tuple[tuple[str, str], ...] = ()
    retry_observation: RetryObservation = "not_collected"
    retry_attempts: int = 0

    @property
    def complete(self) -> bool:
        return not self.diagnostics.partial

    @property
    def model_invocations(self) -> int:
        """Captured model-start callbacks, not hidden provider HTTP attempts."""
        return sum(e.kind == "model" and e.phase == "start" for e in self.events)

    @property
    def tool_calls(self) -> int:
        return sum(e.kind == "tool" and e.phase == "start" for e in self.events)

    def summary(self) -> ExecutionSummary:
        """Where time went, which tools ran and what failed; content-free."""
        groups: dict[tuple[SpanKind, str | None], list[ExecutionEvent]] = {}
        root_state: ExecutionState | None = None
        root_duration: int | None = None
        tokens = 0
        reported = False
        unknown = 0
        for event in self.events:
            if event.phase != "terminal":
                continue
            if event.kind == "run":
                root_state, root_duration = event.state, event.duration_ns
                continue
            label = event.component if event.kind == "tool" else event.model_id
            groups.setdefault((event.kind, label), []).append(event)
            if event.kind == "model":
                if event.usage is not None and event.usage.availability == "reported":
                    reported = True
                    tokens += event.usage.total_tokens or 0
                else:
                    unknown += 1
        rows = tuple(
            ComponentSummary(
                kind,
                label,
                len(items),
                sum(e.state == "failed" for e in items),
                sum(e.state == "cancelled" for e in items),
                sum(e.state == "incomplete" for e in items),
                sum(e.duration_ns or 0 for e in items),
                max((e.duration_ns or 0 for e in items), default=0),
            )
            for (kind, label), items in sorted(
                groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")
            )
        )
        return ExecutionSummary(
            self.run_id,
            root_state,
            root_duration,
            rows,
            tokens if reported else None,
            unknown,
            self.diagnostics.retry_signals,
            self.complete,
            self.retry_observation,
            len(self.retry_links),
        )

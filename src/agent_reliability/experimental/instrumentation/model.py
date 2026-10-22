"""Experimental, local-only content-free execution facts (not outcome evaluations)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

SpanKind = Literal["run", "step", "tool", "model"]
ExecutionState = Literal["completed", "failed", "cancelled", "incomplete"]
_ALIAS = re.compile(r"[A-Za-z0-9._-]{1,128}\Z", re.ASCII)
MAX_COUNT = 2**63 - 1


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


@dataclass(frozen=True, slots=True)
class ExecutionTrace:
    run_id: str
    parent_run_id: str | None
    events: tuple[ExecutionEvent, ...]
    diagnostics: CaptureDiagnostics

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

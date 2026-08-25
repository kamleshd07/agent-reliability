"""Instrumentation events: the payload shape the ``EventSink`` port
speaks in.

An event represents *something that happened*, once — it is not a
domain object. ``agent_reliability.domain.AgentRun`` is the durable,
structured representation of a run's identity and lifecycle; these
events are what the SDK emits, once each, as that lifecycle unfolds.
The SDK does not treat the two as interchangeable, and does not retain
events after handing them to a sink. See docs/SDK_DESIGN.md, "Event vs.
domain object."

Deliberately four flat, immutable event types — not a richer hierarchy,
and not stringly-typed dictionaries. Each contains only what downstream
reliability processing needs, nothing else: notably, ``RunFailed``
carries the failing exception's *class name* only, never ``str(exc)``,
the exception object, or its traceback (see docs/SDK_DESIGN.md's event
model section for why — both a privacy and a memory-safety concern).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agent_reliability.domain import AgentIdentity, EvaluationOutcome, RunStatus
from agent_reliability.evaluation import EvaluationProvenance

__all__ = [
    "EvaluationRecorded",
    "InstrumentationEvent",
    "RunCompleted",
    "RunFailed",
    "RunStarted",
]

_TERMINAL_FAILURE_STATUSES = frozenset({RunStatus.FAILED, RunStatus.CANCELLED})


@dataclass(frozen=True)
class RunStarted:
    """A run began. Emitted once, at the start of ``sdk.run(...)``."""

    run_id: str
    parent_run_id: str | None
    agent: AgentIdentity
    started_at: datetime


@dataclass(frozen=True)
class RunCompleted:
    """A run finished with no exception."""

    run_id: str
    ended_at: datetime


@dataclass(frozen=True)
class RunFailed:
    """A run finished because of an exception, or was cancelled.

    ``status`` is always ``RunStatus.FAILED`` or ``RunStatus.CANCELLED``
    (never ``STARTED``/``COMPLETED``) — see docs/SDK_DESIGN.md for the
    classification rule.
    """

    run_id: str
    ended_at: datetime
    status: RunStatus
    exception_type: str

    def __post_init__(self) -> None:
        if self.status not in _TERMINAL_FAILURE_STATUSES:
            raise ValueError(
                "RunFailed.status must be RunStatus.FAILED or "
                f"RunStatus.CANCELLED, got {self.status}"
            )
        if not self.exception_type:
            raise ValueError("RunFailed.exception_type must not be empty")


@dataclass(frozen=True)
class EvaluationRecorded:
    """A manual or evaluator-produced outcome was recorded against a run.

    ``provenance is None`` means the existing low-level manual assertion API
    produced the event. Evaluator-produced events carry immutable provenance.
    """

    run_id: str
    indicator: str
    outcome: EvaluationOutcome
    recorded_at: datetime
    provenance: EvaluationProvenance | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if self.provenance is None and self.reason_code is not None:
            raise ValueError("reason_code requires evaluator provenance")


InstrumentationEvent = RunStarted | RunCompleted | RunFailed | EvaluationRecorded

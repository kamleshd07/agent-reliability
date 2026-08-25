"""Ports: typed interfaces the application layer depends on.

``Clock``, ``RunIdGenerator``, and ``EventSink`` (with the
``InstrumentationEvent`` types the sink port speaks in) are the M2 runtime
ports. M3 adds the paired ``RunContextBridge``/``RunContextScope`` lifecycle
port; see ADR-0006.
Ports are defined in terms of domain types and immutable, vendor-neutral M4
evaluation contract values — never in terms of evaluator execution or a
specific adapter (e.g. no ``ports`` module may import the OpenTelemetry SDK).
Concrete implementations live in ``agent_reliability.adapters``. ADR-0007
records this narrow refinement of ADR-0001.

The exports of this subpackage are part of the stable 1.0 contract documented
in docs/GA_CONTRACT.md. Protocol additions can break structural implementers
and therefore require the same compatibility review as signature changes.
"""

from __future__ import annotations

from agent_reliability.ports.clock import Clock
from agent_reliability.ports.event_sink import EventSink
from agent_reliability.ports.events import (
    EvaluationRecorded,
    InstrumentationEvent,
    RunCompleted,
    RunFailed,
    RunStarted,
)
from agent_reliability.ports.id_generator import RunIdGenerator
from agent_reliability.ports.run_context import RunContextBridge, RunContextScope

__all__ = [
    "Clock",
    "EvaluationRecorded",
    "EventSink",
    "InstrumentationEvent",
    "RunCompleted",
    "RunContextBridge",
    "RunContextScope",
    "RunFailed",
    "RunIdGenerator",
    "RunStarted",
]

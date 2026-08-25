"""Adapters: concrete implementations of ports.

The default clock, id generator, and event sinks arrived in M2. M3's optional
OpenTelemetry adapter lives in ``agent_reliability.adapters.otel`` and is not
imported here, preserving base-install import safety.

This is the only layer permitted to depend on a specific vendor SDK,
transport, or agent framework. Adapters implement ports; they are never
imported by ``domain`` or ``application``.

The exports of this subpackage are part of the stable 1.0 contract documented
in docs/GA_CONTRACT.md.
"""

from __future__ import annotations

from agent_reliability.adapters.event_sinks import (
    CompositeEventSink,
    InMemoryEventSink,
    NoOpEventSink,
)
from agent_reliability.adapters.system_clock import SystemClock
from agent_reliability.adapters.uuid_run_id_generator import UuidRunIdGenerator

__all__ = [
    "CompositeEventSink",
    "InMemoryEventSink",
    "NoOpEventSink",
    "SystemClock",
    "UuidRunIdGenerator",
]

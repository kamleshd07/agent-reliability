"""Default ``EventSink`` implementations.

``NoOpEventSink`` is what ``AgentReliability()`` uses when no sink is
given — a library should not silently print to the console by default,
and doing nothing observable until a caller opts in is the least
surprising default for production embedding (docs/SDK_DESIGN.md).
"""

from __future__ import annotations

import threading

from agent_reliability.ports.event_sink import EventSink
from agent_reliability.ports.events import InstrumentationEvent

__all__ = ["CompositeEventSink", "InMemoryEventSink", "NoOpEventSink"]


class NoOpEventSink:
    """Discards every event. The default sink."""

    def emit(self, event: InstrumentationEvent) -> None:
        return None


class InMemoryEventSink:
    """Appends every event to a list, held in memory for the sink's
    lifetime.

    Intended for tests and local examples — **not** a production
    default. Unbounded accumulation of every event for the life of the
    process is exactly the kind of memory growth this project's
    engineering principles warn against as a default (docs/SDK_DESIGN.md,
    "Memory safety"). ``events`` is safe to read/append from multiple
    threads (protected by an internal lock); it is still an unbounded,
    ever-growing list, by design, for this sink.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[InstrumentationEvent] = []

    def emit(self, event: InstrumentationEvent) -> None:
        with self._lock:
            self._events.append(event)

    @property
    def events(self) -> list[InstrumentationEvent]:
        """A snapshot copy of the events received so far."""
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class CompositeEventSink:
    """Fans one event out to multiple sinks.

    Each child's ``emit`` is called independently; one child raising
    does not stop delivery to the others (the exception is allowed to
    propagate to the SDK's own failure-isolation wrapper around this
    composite's ``emit`` call, which reports it via diagnostics exactly
    as it would for a single misbehaving sink — see
    docs/adr/0004-instrumentation-failure-isolation.md). The *first*
    child to raise is what gets reported; later children still run.
    """

    def __init__(self, sinks: list[EventSink]) -> None:
        self._sinks = list(sinks)

    def emit(self, event: InstrumentationEvent) -> None:
        first_error: Exception | None = None
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

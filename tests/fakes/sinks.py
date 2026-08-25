from __future__ import annotations

from agent_reliability.ports.events import InstrumentationEvent


class RecordingSink:
    """Appends every event it receives — a thin, test-only recorder
    distinct from the shipped ``InMemoryEventSink`` so SDK tests do not
    depend on adapters test coverage passing first."""

    def __init__(self) -> None:
        self.events: list[InstrumentationEvent] = []

    def emit(self, event: InstrumentationEvent) -> None:
        self.events.append(event)


class BrokenSink:
    """A sink that always raises — for failure-isolation tests."""

    def emit(self, event: InstrumentationEvent) -> None:
        raise RuntimeError("sink is broken")


class BrokenNTimesSink:
    """A sink that raises on its first ``n`` calls, then behaves normally.
    Useful for proving a transient sink failure does not corrupt
    subsequent delivery."""

    def __init__(self, n: int) -> None:
        self._remaining = n
        self.events: list[InstrumentationEvent] = []

    def emit(self, event: InstrumentationEvent) -> None:
        if self._remaining > 0:
            self._remaining -= 1
            raise RuntimeError("sink is transiently broken")
        self.events.append(event)

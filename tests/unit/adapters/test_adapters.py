from __future__ import annotations

import subprocess
import sys
import threading
from datetime import timedelta

import pytest

from agent_reliability.adapters import (
    CompositeEventSink,
    InMemoryEventSink,
    NoOpEventSink,
    SystemClock,
    UuidRunIdGenerator,
)
from agent_reliability.ports.events import RunCompleted


class TestSystemClock:
    def test_returns_timezone_aware_utc(self) -> None:
        now = SystemClock().now()
        assert now.tzinfo is not None
        assert now.utcoffset() == timedelta(0)

    def test_successive_calls_do_not_go_backwards(self) -> None:
        clock = SystemClock()
        first = clock.now()
        second = clock.now()
        assert second >= first


class TestUuidRunIdGenerator:
    def test_generates_unique_ids(self) -> None:
        generator = UuidRunIdGenerator()
        ids = {generator.generate() for _ in range(1000)}
        assert len(ids) == 1000

    def test_ids_are_not_sequential(self) -> None:
        generator = UuidRunIdGenerator()
        a, b = generator.generate(), generator.generate()
        assert a != b
        assert not (a.endswith("0") and b.endswith("1"))  # not literally counting


class TestNoOpEventSink:
    def test_discards_everything_without_raising(self) -> None:
        sink = NoOpEventSink()
        sink.emit(
            RunCompleted(run_id="x", ended_at=SystemClock().now())
        )  # must not raise


class TestInMemoryEventSink:
    def test_events_accumulate_in_order(self) -> None:
        sink = InMemoryEventSink()
        e1 = RunCompleted(run_id="1", ended_at=SystemClock().now())
        e2 = RunCompleted(run_id="2", ended_at=SystemClock().now())
        sink.emit(e1)
        sink.emit(e2)
        assert sink.events == [e1, e2]

    def test_events_property_is_a_snapshot_copy(self) -> None:
        sink = InMemoryEventSink()
        sink.emit(RunCompleted(run_id="1", ended_at=SystemClock().now()))
        snapshot = sink.events
        sink.emit(RunCompleted(run_id="2", ended_at=SystemClock().now()))
        assert len(snapshot) == 1  # snapshot was not mutated by the later emit

    def test_clear_empties_the_sink(self) -> None:
        sink = InMemoryEventSink()
        sink.emit(RunCompleted(run_id="1", ended_at=SystemClock().now()))
        sink.clear()
        assert sink.events == []

    def test_retention_is_deliberately_unbounded_until_clear(self) -> None:
        sink = InMemoryEventSink()
        events = [
            RunCompleted(run_id=str(i), ended_at=SystemClock().now())
            for i in range(1_000)
        ]
        for event in events:
            sink.emit(event)
        assert sink.events == events

    def test_concurrent_emit_from_many_threads_loses_no_events(self) -> None:
        sink = InMemoryEventSink()
        thread_count = 20
        per_thread = 50

        def worker(tag: int) -> None:
            for i in range(per_thread):
                sink.emit(
                    RunCompleted(run_id=f"{tag}-{i}", ended_at=SystemClock().now())
                )

        threads = [
            threading.Thread(target=worker, args=(t,)) for t in range(thread_count)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(sink.events) == thread_count * per_thread


class TestCompositeEventSink:
    def test_fans_out_to_all_children(self) -> None:
        a, b = InMemoryEventSink(), InMemoryEventSink()
        composite = CompositeEventSink([a, b])
        event = RunCompleted(run_id="1", ended_at=SystemClock().now())
        composite.emit(event)
        assert a.events == [event]
        assert b.events == [event]

    def test_one_child_raising_does_not_stop_delivery_to_others(self) -> None:
        class Broken:
            def emit(self, event: object) -> None:
                raise RuntimeError("broken")

        healthy = InMemoryEventSink()
        composite = CompositeEventSink([Broken(), healthy])
        event = RunCompleted(run_id="1", ended_at=SystemClock().now())

        with pytest.raises(RuntimeError, match="broken"):
            composite.emit(event)

        assert healthy.events == [
            event
        ]  # still delivered despite the earlier child raising

    def test_only_the_first_of_multiple_failures_is_raised(self) -> None:
        class BrokenFirst:
            def emit(self, event: object) -> None:
                raise RuntimeError("first")

        class BrokenSecond:
            def emit(self, event: object) -> None:
                raise RuntimeError("second")

        composite = CompositeEventSink([BrokenFirst(), BrokenSecond()])
        event = RunCompleted(run_id="1", ended_at=SystemClock().now())

        with pytest.raises(RuntimeError, match="first"):
            composite.emit(event)

    @pytest.mark.parametrize(
        "failing_indices",
        [{0}, {1}, {2}, {0, 2}, {0, 1, 2}],
        ids=["first", "middle", "last", "multiple", "all"],
    )
    def test_every_child_is_attempted_once_for_every_failure_order(
        self, failing_indices: set[int]
    ) -> None:
        calls: list[list[object]] = [[], [], []]

        class TrackingSink:
            def __init__(self, index: int) -> None:
                self.index = index

            def emit(self, event: object) -> None:
                calls[self.index].append(event)
                if self.index in failing_indices:
                    raise RuntimeError(f"failure-{self.index}")

        event = RunCompleted(run_id="1", ended_at=SystemClock().now())
        composite = CompositeEventSink([TrackingSink(i) for i in range(3)])
        with pytest.raises(RuntimeError, match=f"failure-{min(failing_indices)}"):
            composite.emit(event)
        assert calls == [[event], [event], [event]]


class TestOptionalOtelDependency:
    """M3's OpenTelemetry adapter must stay opt-in: importing the base
    ``adapters``/``sdk`` packages must never pull in ``opentelemetry``,
    regardless of whether it happens to be installed in the current
    environment (installed or not, this package must not import it
    unless the caller explicitly imports ``agent_reliability.adapters.otel``).
    Run in a fresh interpreter — other tests in this suite already import
    ``opentelemetry`` at module level, so checking ``sys.modules`` in-process
    would not prove anything.
    """

    def test_importing_base_package_never_imports_opentelemetry(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys\n"
                "import agent_reliability\n"
                "import agent_reliability.sdk\n"
                "import agent_reliability.adapters\n"
                "import agent_reliability.ports\n"
                "assert 'opentelemetry' not in sys.modules, sys.modules.keys()\n"
                "print('OK')\n",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK" in result.stdout

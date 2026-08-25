"""M2 does not claim automatic cross-thread context propagation
(docs/SDK_DESIGN.md, "Threads are not automatically supported"). These
tests prove the limitation is real and prove the documented workaround
(``contextvars.copy_context()`` + ``Context.run()``) actually works —
per the M2 brief: "never rely on assumptions," test what is claimed and
what is not.
"""

from __future__ import annotations

import contextvars
import threading

from agent_reliability.adapters import (
    InMemoryEventSink,
    SystemClock,
    UuidRunIdGenerator,
)
from agent_reliability.sdk import AgentReliability, current_run
from tests.fakes.clock import FakeClock
from tests.fakes.id_generator import SequentialRunIdGenerator
from tests.fakes.sinks import RecordingSink


def _sdk() -> AgentReliability:
    return AgentReliability(
        sink=RecordingSink(),
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator(),
    )


class TestNoAutomaticCrossThreadPropagation:
    def test_a_plain_new_thread_does_not_see_the_parent_run(self) -> None:
        sdk = _sdk()
        observed: list[object] = []

        def worker() -> None:
            observed.append(current_run())

        with sdk.run(agent_id="parent", name="Parent", version="1"):
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()

        assert observed == [None]  # the new thread never saw the parent run

    def test_a_run_started_in_a_plain_new_thread_has_no_parent(self) -> None:
        sdk = _sdk()
        observed_parent_ids: list[str | None] = []

        def worker() -> None:
            with sdk.run(agent_id="child", name="Child", version="1") as run:
                observed_parent_ids.append(run.parent_run_id)

        with sdk.run(agent_id="parent", name="Parent", version="1"):
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()

        assert observed_parent_ids == [None]


class TestDocumentedThreadWorkaround:
    def test_copy_context_and_context_run_propagates_correctly(self) -> None:
        sdk = _sdk()
        observed: list[object] = []

        def worker() -> None:
            observed.append(current_run())

        with sdk.run(agent_id="parent", name="Parent", version="1") as parent:
            ctx = contextvars.copy_context()
            thread = threading.Thread(target=lambda: ctx.run(worker))
            thread.start()
            thread.join()

            assert observed == [parent]

    def test_copy_context_lets_a_child_run_in_a_thread_see_the_correct_parent(
        self,
    ) -> None:
        sdk = _sdk()
        observed_parent_ids: list[str | None] = []

        def worker() -> None:
            with sdk.run(agent_id="child", name="Child", version="1") as run:
                observed_parent_ids.append(run.parent_run_id)

        with sdk.run(agent_id="parent", name="Parent", version="1") as parent:
            ctx = contextvars.copy_context()
            thread = threading.Thread(target=lambda: ctx.run(worker))
            thread.start()
            thread.join()

        assert observed_parent_ids == [parent.run_id]


class TestConcurrentRunAcrossThreads:
    """docs/SDK_DESIGN.md claims ``AgentReliability`` is safe to call
    ``.run()`` on concurrently from multiple threads, since it holds no
    mutable per-run state. Proven here with real OS threads (not just
    asyncio tasks), using the actual shipped default adapters
    (``SystemClock``, ``UuidRunIdGenerator``) rather than the
    single-threaded test fakes used elsewhere in this file — the fakes
    are not claimed to be thread-safe, only the shipped defaults are.
    """

    def test_many_threads_calling_run_concurrently_never_cross_contaminate(
        self,
    ) -> None:
        sink = InMemoryEventSink()
        sdk = AgentReliability(
            sink=sink, clock=SystemClock(), run_id_generator=UuidRunIdGenerator()
        )
        thread_count = 30
        observed_run_ids: list[str] = []
        observed_parent_ids: list[str | None] = []
        lock = threading.Lock()

        def worker() -> None:
            with sdk.run(agent_id="a", name="A", version="1") as run:
                # No thread should ever see another thread's run as current.
                assert current_run() is run
                with lock:
                    observed_run_ids.append(run.run_id)
                    observed_parent_ids.append(run.parent_run_id)

        threads = [threading.Thread(target=worker) for _ in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(observed_run_ids)) == thread_count  # no id collisions
        assert all(
            parent_id is None for parent_id in observed_parent_ids
        )  # no cross-thread parenting
        assert current_run() is None  # main thread's own context untouched
        assert (
            len([e for e in sink.events if type(e).__name__ == "RunStarted"])
            == thread_count
        )

from __future__ import annotations

import asyncio

import pytest

from agent_reliability.domain import EvaluationOutcome, RunStatus
from agent_reliability.ports.events import RunFailed
from agent_reliability.sdk import AgentReliability, current_run
from tests.fakes.clock import FakeClock
from tests.fakes.id_generator import SequentialRunIdGenerator
from tests.fakes.sinks import RecordingSink


def _sdk() -> tuple[AgentReliability, RecordingSink]:
    sink = RecordingSink()
    sdk = AgentReliability(
        sink=sink, clock=FakeClock(), run_id_generator=SequentialRunIdGenerator()
    )
    return sdk, sink


class TestAsyncNormalCompletion:
    async def test_async_with_completes_normally(self) -> None:
        sdk, sink = _sdk()
        async with sdk.run(agent_id="a", name="A", version="1") as run:
            await asyncio.sleep(0)
            run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)
        assert [type(e).__name__ for e in sink.events] == [
            "RunStarted",
            "EvaluationRecorded",
            "RunCompleted",
        ]

    async def test_context_restored_after_async_block(self) -> None:
        sdk, _ = _sdk()
        assert current_run() is None
        async with sdk.run(agent_id="a", name="A", version="1") as run:
            assert current_run() is run
        assert current_run() is None


class TestAsyncExceptionPreservation:
    async def test_original_exception_propagates_unchanged(self) -> None:
        sdk, _ = _sdk()
        original = ValueError("boom")
        with pytest.raises(ValueError) as excinfo:
            async with sdk.run(agent_id="a", name="A", version="1"):
                raise original
        assert excinfo.value is original

    async def test_cancelled_error_propagates_and_is_classified_as_cancelled(
        self,
    ) -> None:
        sdk, sink = _sdk()

        async def cancel_inside() -> None:
            async with sdk.run(agent_id="a", name="A", version="1"):
                raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await cancel_inside()

        failed = sink.events[-1]
        assert isinstance(failed, RunFailed)
        assert failed.status is RunStatus.CANCELLED
        assert failed.exception_type == "CancelledError"

    async def test_task_cancel_propagates_and_is_classified_as_cancelled(self) -> None:
        sdk, sink = _sdk()
        started = asyncio.Event()

        async def worker() -> None:
            async with sdk.run(agent_id="a", name="A", version="1"):
                started.set()
                await asyncio.sleep(10)

        task = asyncio.create_task(worker())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        failed = sink.events[-1]
        assert isinstance(failed, RunFailed)
        assert failed.status is RunStatus.CANCELLED


class TestAsyncNesting:
    async def test_nested_async_runs_have_correct_parent(self) -> None:
        sdk, _ = _sdk()
        async with sdk.run(agent_id="parent", name="Parent", version="1") as parent:
            async with sdk.run(agent_id="child", name="Child", version="1") as child:
                assert child.parent_run_id == parent.run_id
            assert current_run() is parent
        assert current_run() is None


class TestConcurrentAsyncTasks:
    async def test_many_concurrent_tasks_never_cross_contaminate_context(self) -> None:
        sdk, _sink = _sdk()
        task_count = 150

        async def run_one(index: int) -> tuple[str, str | None]:
            async with sdk.run(agent_id=f"agent-{index}", name="A", version="1") as run:
                # Yield control so other tasks interleave here.
                await asyncio.sleep(0)
                observed_parent = current_run()
                await asyncio.sleep(0)
                assert observed_parent is run
                return run.run_id, run.parent_run_id

        results = await asyncio.gather(*(run_one(i) for i in range(task_count)))

        run_ids = [run_id for run_id, _ in results]
        assert len(set(run_ids)) == task_count  # every run id is unique
        assert all(
            parent_id is None for _, parent_id in results
        )  # no cross-task parenting
        assert current_run() is None

    async def test_concurrent_nested_tasks_isolate_parent_chains(self) -> None:
        sdk, _ = _sdk()

        async def parent_and_child(tag: str) -> tuple[str, str]:
            async with sdk.run(
                agent_id=f"parent-{tag}", name="P", version="1"
            ) as parent:
                await asyncio.sleep(0)
                async with sdk.run(
                    agent_id=f"child-{tag}", name="C", version="1"
                ) as child:
                    await asyncio.sleep(0)
                    assert child.parent_run_id == parent.run_id
                    return parent.run_id, child.run_id

        results = await asyncio.gather(*(parent_and_child(tag) for tag in "abcdefgh"))
        all_ids = [run_id for pair in results for run_id in pair]
        assert len(set(all_ids)) == len(
            all_ids
        )  # no id collisions across concurrent tasks

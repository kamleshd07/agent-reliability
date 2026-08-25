"""Property-based tests for the M2 SDK runtime: nested run depth, id
uniqueness, and lifecycle-event ordering invariants.
"""

from __future__ import annotations

from contextlib import ExitStack

from hypothesis import given, settings
from hypothesis import strategies as st

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.ports.events import (
    EvaluationRecorded,
    RunCompleted,
    RunFailed,
    RunStarted,
)
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


@settings(max_examples=50)
@given(depth=st.integers(min_value=1, max_value=30))
def test_arbitrary_nesting_depth_produces_a_correct_parent_chain(depth: int) -> None:
    sdk, _ = _sdk()
    with ExitStack() as stack:
        handles = []
        for i in range(depth):
            handle = stack.enter_context(
                sdk.run(agent_id=f"agent-{i}", name="A", version="1")
            )
            handles.append(handle)

        for i, handle in enumerate(handles):
            expected_parent = handles[i - 1].run_id if i > 0 else None
            assert handle.parent_run_id == expected_parent

    assert current_run() is None


@settings(max_examples=50)
@given(count=st.integers(min_value=1, max_value=100))
def test_sequential_runs_never_produce_duplicate_ids(count: int) -> None:
    sdk, _ = _sdk()
    seen_ids: set[str] = set()
    for i in range(count):
        with sdk.run(agent_id=f"agent-{i}", name="A", version="1") as run:
            assert run.run_id not in seen_ids
            seen_ids.add(run.run_id)
    assert len(seen_ids) == count


@settings(max_examples=30)
@given(outcomes_recorded=st.integers(min_value=0, max_value=10))
def test_event_ordering_is_always_started_then_optional_recordings_then_terminal(
    outcomes_recorded: int,
) -> None:
    sdk, sink = _sdk()

    with sdk.run(agent_id="a", name="A", version="1") as run:
        for _ in range(outcomes_recorded):
            run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)

    events = sink.events
    assert isinstance(events[0], RunStarted)
    assert isinstance(events[-1], RunCompleted | RunFailed)
    for middle_event in events[1:-1]:
        assert isinstance(middle_event, EvaluationRecorded)
    assert len(events) == outcomes_recorded + 2

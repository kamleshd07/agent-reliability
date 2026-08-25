from __future__ import annotations

import pytest

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


class TestNestedSyncContexts:
    def test_three_level_nesting_has_correct_parent_chain(self) -> None:
        sdk = _sdk()
        with sdk.run(agent_id="research", name="Research", version="1") as research:
            assert research.parent_run_id is None
            with sdk.run(
                agent_id="fundamentals", name="Fundamentals", version="1"
            ) as fundamentals:
                assert fundamentals.parent_run_id == research.run_id
                with sdk.run(agent_id="news", name="News", version="1") as news:
                    assert news.parent_run_id == fundamentals.run_id
                assert current_run() is fundamentals
            assert current_run() is research
        assert current_run() is None

    def test_sibling_runs_share_the_same_parent(self) -> None:
        sdk = _sdk()
        with sdk.run(agent_id="parent", name="Parent", version="1") as parent:
            with sdk.run(agent_id="child-a", name="A", version="1") as a:
                assert a.parent_run_id == parent.run_id
            with sdk.run(agent_id="child-b", name="B", version="1") as b:
                assert b.parent_run_id == parent.run_id
            assert a.run_id != b.run_id

    def test_context_restored_after_child_exception(self) -> None:
        sdk = _sdk()
        with sdk.run(agent_id="parent", name="Parent", version="1") as parent:
            with (
                pytest.raises(ValueError),
                sdk.run(agent_id="child", name="Child", version="1"),
            ):
                raise ValueError("child failed")
            assert current_run() is parent
        assert current_run() is None

    def test_sequential_top_level_runs_have_no_parent(self) -> None:
        sdk = _sdk()
        with sdk.run(agent_id="a", name="A", version="1") as run_a:
            assert run_a.parent_run_id is None
        with sdk.run(agent_id="b", name="B", version="1") as run_b:
            assert run_b.parent_run_id is None

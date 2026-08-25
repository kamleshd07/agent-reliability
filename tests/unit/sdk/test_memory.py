"""docs/SDK_DESIGN.md, "Memory safety": completed runs must not be kept
reachable via the SDK's own internal state after their `with` block
ends. A weakref that dies once our own references are dropped proves
the SDK is not the thing keeping it alive.
"""

from __future__ import annotations

import gc
import weakref

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


def test_completed_run_handle_is_collectible_once_caller_drops_it() -> None:
    sdk = _sdk()
    ref: weakref.ReferenceType[object]

    def scope() -> None:
        nonlocal ref
        with sdk.run(agent_id="a", name="A", version="1") as run:
            ref = weakref.ref(run)

    scope()
    gc.collect()
    assert ref() is None, (
        "the SDK itself is retaining a reference to a completed run handle"
    )


def test_current_run_context_var_does_not_leak_across_unrelated_calls() -> None:
    sdk = _sdk()
    with sdk.run(agent_id="a", name="A", version="1"):
        pass
    # A brand-new, unrelated `.run()` call must not see a stale parent.
    with sdk.run(agent_id="b", name="B", version="1") as run:
        assert run.parent_run_id is None
    assert current_run() is None

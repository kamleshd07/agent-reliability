from __future__ import annotations

from dataclasses import dataclass

import pytest

from agent_reliability.domain import AgentRun, RunStatus
from agent_reliability.ports.events import InstrumentationEvent
from agent_reliability.sdk import AgentReliability
from tests.fakes.clock import BrokenClock, FakeClock
from tests.fakes.diagnostics import CollectingDiagnosticHandler
from tests.fakes.id_generator import SequentialRunIdGenerator


@dataclass
class RecordingScope:
    calls: list[object]

    def finish(self, *, status: RunStatus, exception_type: str | None) -> None:
        self.calls.append(("bridge.finish", status, exception_type))


class RecordingBridge:
    def __init__(self, calls: list[object]) -> None:
        self.calls = calls
        self.runs: list[AgentRun] = []

    def start(self, run: AgentRun) -> RecordingScope:
        self.runs.append(run)
        self.calls.append(("bridge.start", run.run_id))
        return RecordingScope(self.calls)


class OrderedSink:
    def __init__(self, calls: list[object]) -> None:
        self.calls = calls

    def emit(self, event: InstrumentationEvent) -> None:
        self.calls.append(("sink", type(event).__name__))


class BrokenStartBridge:
    def start(self, run: AgentRun) -> RecordingScope:
        raise RuntimeError("sensitive start failure")


class WrongReturnTypeBridge:
    """A bridge whose ``start()`` is shaped correctly but returns
    something that does not implement ``RunContextScope`` (e.g. missing
    ``finish()``) — the SDK must reject this itself, since nothing
    downstream can call ``.finish()`` on it safely."""

    def start(self, run: AgentRun) -> object:
        return "not a scope"


class BrokenFinishScope:
    def finish(self, *, status: RunStatus, exception_type: str | None) -> None:
        raise RuntimeError("sensitive finish failure")


class BrokenFinishBridge:
    def start(self, run: AgentRun) -> BrokenFinishScope:
        return BrokenFinishScope()


class InterruptingFinishScope:
    def finish(self, *, status: RunStatus, exception_type: str | None) -> None:
        raise KeyboardInterrupt


class InterruptingFinishBridge:
    def start(self, run: AgentRun) -> InterruptingFinishScope:
        return InterruptingFinishScope()


def _sdk(*, bridge: object, sink: object, diagnostics: object) -> AgentReliability:
    return AgentReliability(
        run_context_bridge=bridge,  # type: ignore[arg-type]
        sink=sink,  # type: ignore[arg-type]
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator(),
        diagnostic_handler=diagnostics,  # type: ignore[arg-type]
    )


@pytest.mark.contract
def test_bridge_surrounds_event_delivery_and_application_body() -> None:
    calls: list[object] = []
    bridge = RecordingBridge(calls)
    sdk = _sdk(
        bridge=bridge,
        sink=OrderedSink(calls),
        diagnostics=CollectingDiagnosticHandler(),
    )

    with sdk.run(agent_id="agent", name="Agent", version="1"):
        calls.append("body")

    assert calls == [
        ("bridge.start", "run-1"),
        ("sink", "RunStarted"),
        "body",
        ("sink", "RunCompleted"),
        ("bridge.finish", RunStatus.COMPLETED, None),
    ]


@pytest.mark.contract
def test_bridge_failure_does_not_disable_agent_reliability_events() -> None:
    calls: list[object] = []
    diagnostics = CollectingDiagnosticHandler()
    sdk = _sdk(
        bridge=BrokenStartBridge(),
        sink=OrderedSink(calls),
        diagnostics=diagnostics,
    )

    with sdk.run(agent_id="agent", name="Agent", version="1"):
        calls.append("body")

    assert calls == [
        ("sink", "RunStarted"),
        "body",
        ("sink", "RunCompleted"),
    ]
    assert len(diagnostics.diagnostics) == 1
    diagnostic = diagnostics.diagnostics[0]
    assert diagnostic.component == "run_context_bridge"
    assert diagnostic.operation == "start"
    assert diagnostic.run_id == "run-1"


@pytest.mark.contract
def test_bridge_cleanup_failure_does_not_replace_user_exception() -> None:
    diagnostics = CollectingDiagnosticHandler()
    sdk = _sdk(
        bridge=BrokenFinishBridge(),
        sink=OrderedSink([]),
        diagnostics=diagnostics,
    )
    original = ValueError("private application detail")

    with (
        pytest.raises(ValueError) as exc_info,
        sdk.run(agent_id="agent", name="Agent", version="1"),
    ):
        raise original

    assert exc_info.value is original
    assert len(diagnostics.diagnostics) == 1
    diagnostic = diagnostics.diagnostics[0]
    assert diagnostic.component == "run_context_bridge"
    assert diagnostic.operation == "finish"
    assert diagnostic.run_id == "run-1"


@pytest.mark.contract
def test_bridge_returning_wrong_type_is_diagnosed_and_does_not_disable_events() -> None:
    calls: list[object] = []
    diagnostics = CollectingDiagnosticHandler()
    sdk = _sdk(
        bridge=WrongReturnTypeBridge(),
        sink=OrderedSink(calls),
        diagnostics=diagnostics,
    )

    with sdk.run(agent_id="agent", name="Agent", version="1"):
        calls.append("body")

    assert calls == [
        ("sink", "RunStarted"),
        "body",
        ("sink", "RunCompleted"),
    ]
    assert len(diagnostics.diagnostics) == 1
    diagnostic = diagnostics.diagnostics[0]
    assert diagnostic.component == "run_context_bridge"
    assert diagnostic.operation == "start"
    assert isinstance(diagnostic.exception, TypeError)
    assert "RunContextScope" in str(diagnostic.exception)


@pytest.mark.contract
def test_degraded_run_never_calls_bridge() -> None:
    calls: list[object] = []
    bridge = RecordingBridge(calls)
    sdk = AgentReliability(
        run_context_bridge=bridge,
        clock=BrokenClock(),
        run_id_generator=SequentialRunIdGenerator(),
        diagnostic_handler=CollectingDiagnosticHandler(),
    )

    with sdk.run(agent_id="agent", name="Agent", version="1") as run:
        assert run.run_id is None

    assert bridge.runs == []
    assert calls == []


@pytest.mark.contract
def test_bridge_control_signal_propagates_after_sdk_context_restoration() -> None:
    from agent_reliability.sdk import current_run

    sdk = _sdk(
        bridge=InterruptingFinishBridge(),
        sink=OrderedSink([]),
        diagnostics=CollectingDiagnosticHandler(),
    )

    with (
        pytest.raises(KeyboardInterrupt),
        sdk.run(agent_id="agent", name="Agent", version="1"),
    ):
        pass

    assert current_run() is None

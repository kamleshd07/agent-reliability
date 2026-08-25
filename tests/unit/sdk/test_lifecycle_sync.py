from __future__ import annotations

import pytest

from agent_reliability.domain import EvaluationOutcome, RunStatus
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


class TestNormalCompletion:
    def test_emits_started_then_completed(self) -> None:
        sdk, sink = _sdk()
        with sdk.run(agent_id="a", name="A", version="1") as run:
            assert run.run_id == "run-1"
            assert run.parent_run_id is None

        assert [type(e).__name__ for e in sink.events] == ["RunStarted", "RunCompleted"]
        started, completed = sink.events
        assert isinstance(started, RunStarted)
        assert isinstance(completed, RunCompleted)
        assert started.run_id == completed.run_id == "run-1"
        assert started.agent.agent_id == "a"

    def test_context_is_current_inside_and_cleared_after(self) -> None:
        sdk, _ = _sdk()
        assert current_run() is None
        with sdk.run(agent_id="a", name="A", version="1") as run:
            assert current_run() is run
        assert current_run() is None


class TestExceptionPreservation:
    def test_original_exception_propagates_unchanged(self) -> None:
        sdk, _sink = _sdk()

        class MyError(ValueError):
            pass

        original = MyError("boom")
        with (
            pytest.raises(MyError) as excinfo,
            sdk.run(agent_id="a", name="A", version="1"),
        ):
            raise original

        assert excinfo.value is original
        assert str(excinfo.value) == "boom"

    def test_emits_run_failed_with_exception_type_only(self) -> None:
        sdk, sink = _sdk()
        with pytest.raises(ValueError), sdk.run(agent_id="a", name="A", version="1"):
            raise ValueError("sensitive detail: user@example.com")

        failed = sink.events[-1]
        assert isinstance(failed, RunFailed)
        assert failed.status is RunStatus.FAILED
        assert failed.exception_type == "ValueError"
        # The exception message itself must never appear in the event.
        assert not hasattr(failed, "message")

    def test_context_restored_after_exception(self) -> None:
        sdk, _ = _sdk()
        with pytest.raises(ValueError), sdk.run(agent_id="a", name="A", version="1"):
            raise ValueError("boom")
        assert current_run() is None


class TestRecording:
    def test_record_pass_emits_evaluation_recorded(self) -> None:
        sdk, sink = _sdk()
        with sdk.run(agent_id="a", name="A", version="1") as run:
            run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)

        recorded = sink.events[1]
        assert isinstance(recorded, EvaluationRecorded)
        assert recorded.indicator == "task_success"
        assert recorded.outcome is EvaluationOutcome.PASS
        assert recorded.run_id == "run-1"

    def test_record_unknown_passes_through_intact(self) -> None:
        sdk, sink = _sdk()
        with sdk.run(agent_id="a", name="A", version="1") as run:
            run.record(indicator="policy_compliance", outcome=EvaluationOutcome.UNKNOWN)

        recorded = sink.events[1]
        assert isinstance(recorded, EvaluationRecorded)
        assert recorded.outcome is EvaluationOutcome.UNKNOWN

    def test_record_after_close_raises_runtime_error(self) -> None:
        sdk, _ = _sdk()
        with sdk.run(agent_id="a", name="A", version="1") as run:
            pass
        with pytest.raises(RuntimeError, match="closed"):
            run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)

    def test_record_empty_indicator_raises_value_error(self) -> None:
        sdk, _ = _sdk()
        with (
            sdk.run(agent_id="a", name="A", version="1") as run,
            pytest.raises(ValueError, match="indicator"),
        ):
            run.record(indicator="", outcome=EvaluationOutcome.PASS)

    def test_record_wrong_outcome_type_raises_type_error(self) -> None:
        sdk, _ = _sdk()
        with (
            sdk.run(agent_id="a", name="A", version="1") as run,
            pytest.raises(TypeError, match="EvaluationOutcome"),
        ):
            run.record(indicator="task_success", outcome="pass")  # type: ignore[arg-type]


class TestInvalidUse:
    def test_run_with_empty_agent_id_raises_before_entering_context(self) -> None:
        sdk, _ = _sdk()
        with pytest.raises(ValueError, match="agent_id"):
            sdk.run(agent_id="", name="A", version="1")
        assert current_run() is None

    def test_handle_properties_reflect_identity(self) -> None:
        sdk, _ = _sdk()
        with sdk.run(agent_id="a", name="A", version="1", environment="staging") as run:
            assert run.agent.agent_id == "a"
            assert run.agent.environment == "staging"

    @pytest.mark.parametrize(
        ("argument", "message"),
        [
            ("sink", "EventSink"),
            ("clock", "Clock"),
            ("run_id_generator", "RunIdGenerator"),
            ("diagnostic_handler", "DiagnosticHandler"),
            ("run_context_bridge", "RunContextBridge"),
        ],
    )
    def test_wrong_sdk_dependency_type_raises_immediately(
        self, argument: str, message: str
    ) -> None:
        with pytest.raises(TypeError, match=message):
            AgentReliability(**{argument: object()})  # type: ignore[arg-type]

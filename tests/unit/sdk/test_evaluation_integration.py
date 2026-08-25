from __future__ import annotations

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation import (
    EqualityEvaluator,
    EvaluationExecutionFailure,
    EvaluationResult,
    EvaluatorIdentity,
)
from agent_reliability.ports import EvaluationRecorded
from agent_reliability.sdk import AgentReliability, EvaluatorRunner
from tests.fakes.clock import BrokenClock, FakeClock
from tests.fakes.diagnostics import CollectingDiagnosticHandler
from tests.fakes.id_generator import SequentialRunIdGenerator
from tests.fakes.sinks import RecordingSink


def _runtime() -> tuple[AgentReliability, RecordingSink]:
    sink = RecordingSink()
    return (
        AgentReliability(
            sink=sink,
            clock=FakeClock(),
            run_id_generator=SequentialRunIdGenerator(),
        ),
        sink,
    )


def test_completed_result_records_indicator_outcome_and_provenance() -> None:
    sdk, sink = _runtime()
    evaluator = EqualityEvaluator(EvaluatorIdentity("refund-result", "3"), 42)
    result = EvaluatorRunner(clock=FakeClock()).evaluate(evaluator, 42)
    assert isinstance(result, EvaluationResult)

    with sdk.run(agent_id="refund-agent", name="Refund", version="4.8") as run:
        run.record_evaluation(indicator="task_success", result=result)

    recorded = sink.events[1]
    assert isinstance(recorded, EvaluationRecorded)
    assert recorded.run_id == "run-1"
    assert recorded.indicator == "task_success"
    assert recorded.outcome is EvaluationOutcome.PASS
    assert recorded.provenance == result.provenance
    assert recorded.reason_code == "equal"
    assert recorded.recorded_at > recorded.provenance.evaluated_at


def test_manual_recording_remains_distinct_and_compatible() -> None:
    sdk, sink = _runtime()
    with sdk.run(agent_id="a", name="A", version="1") as run:
        run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)

    recorded = sink.events[1]
    assert isinstance(recorded, EvaluationRecorded)
    assert recorded.outcome is EvaluationOutcome.PASS
    assert recorded.provenance is None
    assert recorded.reason_code is None


def test_evaluation_input_is_absent_from_result_and_recorded_event() -> None:
    secret = "PRIVATE_REFUND_RECORD_123"
    evaluator = EqualityEvaluator(
        EvaluatorIdentity("refund-result", "1"),
        {"approved": True},
    )
    value = {"approved": True, "secret": secret}
    result = EvaluatorRunner(clock=FakeClock()).evaluate(evaluator, value)
    assert isinstance(result, EvaluationResult)

    sdk, sink = _runtime()
    with sdk.run(agent_id="a", name="A", version="1") as run:
        run.record_evaluation(indicator="task_success", result=result)

    recorded = sink.events[1]
    assert secret not in repr(result)
    assert secret not in repr(recorded)
    assert not hasattr(result, "input")
    assert not hasattr(recorded, "input")


def test_safe_evaluator_failure_does_not_break_application_or_emit_agent_failure() -> (
    None
):
    class BrokenEvaluator:
        identity = EvaluatorIdentity("broken-rule", "1")
        deterministic = True

        def evaluate(self, value: object):  # type: ignore[no-untyped-def]
            raise RuntimeError("evaluator dependency unavailable")

    diagnostics = CollectingDiagnosticHandler()
    runner = EvaluatorRunner(clock=FakeClock(), diagnostic_handler=diagnostics)
    sdk, sink = _runtime()
    application_continued = False
    with sdk.run(agent_id="a", name="A", version="1"):
        failure = runner.evaluate(BrokenEvaluator(), object())
        application_continued = True

    assert application_continued is True
    assert isinstance(failure, EvaluationExecutionFailure)
    assert [type(event).__name__ for event in sink.events] == [
        "RunStarted",
        "RunCompleted",
    ]
    assert len(diagnostics.diagnostics) == 1


def test_broken_sdk_clock_at_record_evaluation_does_not_raise_and_skips_the_event() -> (
    None
):
    """Mirrors ``test_broken_clock_at_record_does_not_raise_and_skips_the_event``
    in test_failure_isolation.py, but for ``record_evaluation`` — the SDK's own
    (post-start) clock read inside ``_safe_record_evaluation`` must be isolated
    exactly like the one inside ``_safe_record``, not just the evaluator's own
    clock passed to ``EvaluatorRunner``."""

    class ClockThatBreaksAfterFirstCall:
        def __init__(self) -> None:
            self._delegate = FakeClock()
            self._calls = 0

        def now(self):  # type: ignore[no-untyped-def]
            self._calls += 1
            if self._calls > 1:  # first call (RunStarted) succeeds
                raise RuntimeError("sdk clock broke mid-run")
            return self._delegate.now()

    diagnostics = CollectingDiagnosticHandler()
    sink = RecordingSink()
    sdk = AgentReliability(
        sink=sink,
        clock=ClockThatBreaksAfterFirstCall(),
        run_id_generator=SequentialRunIdGenerator(),
        diagnostic_handler=diagnostics,
    )
    result = EvaluatorRunner(clock=FakeClock()).evaluate(
        EqualityEvaluator(EvaluatorIdentity("exact-result", "1"), 1), 1
    )
    assert isinstance(result, EvaluationResult)

    with sdk.run(agent_id="a", name="A", version="1") as run:
        run.record_evaluation(indicator="task_success", result=result)  # must not raise

    # RunStarted delivered; EvaluationRecorded and RunCompleted both
    # skipped because the SDK's own clock kept failing, but nothing raised.
    assert [type(event).__name__ for event in sink.events] == ["RunStarted"]
    assert len(diagnostics.diagnostics) >= 1
    assert all(d.component == "clock" for d in diagnostics.diagnostics)


def test_degraded_run_accepts_valid_record_evaluation_as_safe_no_op() -> None:
    sink = RecordingSink()
    sdk = AgentReliability(
        sink=sink,
        clock=BrokenClock(),
        run_id_generator=SequentialRunIdGenerator(),
    )
    result = EvaluatorRunner(clock=FakeClock()).evaluate(
        EqualityEvaluator(EvaluatorIdentity("exact-result", "1"), 1), 1
    )
    assert isinstance(result, EvaluationResult)
    with sdk.run(agent_id="a", name="A", version="1") as run:
        run.record_evaluation(indicator="task_success", result=result)
    assert sink.events == []


def test_execution_failure_cannot_be_recorded_as_an_evaluation_result() -> None:
    failure = EvaluatorRunner(clock=BrokenClock()).evaluate(
        EqualityEvaluator(EvaluatorIdentity("exact-result", "1"), 1), 1
    )
    assert isinstance(failure, EvaluationExecutionFailure)
    sdk, _ = _runtime()
    with sdk.run(agent_id="a", name="A", version="1") as run:
        try:
            run.record_evaluation(
                indicator="task_success",
                result=failure,  # type: ignore[arg-type]
            )
        except TypeError as exc:
            assert "EvaluationResult" in str(exc)
        else:
            raise AssertionError("execution failure must not be recordable")


def test_record_evaluation_validates_closed_handle_and_indicator() -> None:
    sdk, _ = _runtime()
    result = EvaluatorRunner(clock=FakeClock()).evaluate(
        EqualityEvaluator(EvaluatorIdentity("exact-result", "1"), 1), 1
    )
    assert isinstance(result, EvaluationResult)
    with sdk.run(agent_id="a", name="A", version="1") as run:
        try:
            run.record_evaluation(indicator="", result=result)
        except ValueError as exc:
            assert "indicator" in str(exc)
        else:
            raise AssertionError("empty indicator must fail")
    try:
        run.record_evaluation(indicator="task_success", result=result)
    except RuntimeError as exc:
        assert "closed" in str(exc)
    else:
        raise AssertionError("closed handle must fail")

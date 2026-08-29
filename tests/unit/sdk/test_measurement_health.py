from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation import (
    EqualityEvaluator,
    EvaluationExecutionFailure,
    EvaluationFailureStage,
    EvaluatorIdentity,
)
from agent_reliability.measurement import (
    MeasurementHealth,
    MeasurementHealthReason,
    MeasurementHealthReport,
)
from agent_reliability.sdk import AgentReliability, EvaluatorRunner
from tests.fakes.clock import BrokenClock, FakeClock
from tests.fakes.diagnostics import BrokenDiagnosticHandler
from tests.fakes.id_generator import BrokenRunIdGenerator, SequentialRunIdGenerator
from tests.fakes.sinks import BrokenSink, RecordingSink


def _sdk(**overrides: object) -> AgentReliability:
    arguments: dict[str, object] = {
        "sink": RecordingSink(),
        "clock": FakeClock(),
        "run_id_generator": SequentialRunIdGenerator(),
    }
    arguments.update(overrides)
    return AgentReliability(**arguments)  # type: ignore[arg-type]


def test_success_and_unknown_are_healthy() -> None:
    for outcome in (EvaluationOutcome.PASS, EvaluationOutcome.UNKNOWN):
        with _sdk().run(agent_id="a", name="A", version="1") as run:
            run.record(indicator="task_success", outcome=outcome)
        assert run.measurement_health == MeasurementHealthReport()


@pytest.mark.parametrize("dependency", [BrokenClock(), BrokenRunIdGenerator()])
def test_initialization_failure_is_unavailable_and_body_runs(
    dependency: object,
) -> None:
    body_ran = False
    keyword = "clock" if isinstance(dependency, BrokenClock) else "run_id_generator"
    with _sdk(**{keyword: dependency}).run(agent_id="a", name="A", version="1") as run:
        body_ran = True
    assert body_ran
    assert run.measurement_health.health is MeasurementHealth.UNAVAILABLE
    assert run.measurement_health.reasons == frozenset(
        {MeasurementHealthReason.RUN_INITIALIZATION_FAILURE}
    )


def test_sink_and_post_start_clock_failures_are_degraded() -> None:
    with _sdk(sink=BrokenSink()).run(agent_id="a", name="A", version="1") as sink_run:
        pass
    assert sink_run.measurement_health.health is MeasurementHealth.DEGRADED

    class BreakAfterStart:
        def __init__(self) -> None:
            self.calls = 0

        def now(self):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError("secret must not become health data")
            return FakeClock().now()

    with _sdk(clock=BreakAfterStart()).run(
        agent_id="a", name="A", version="1"
    ) as clock_run:
        clock_run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)
    assert clock_run.measurement_health.health is MeasurementHealth.DEGRADED
    assert MeasurementHealthReason.EVIDENCE_TIMESTAMP_FAILURE in (
        clock_run.measurement_health.reasons
    )


def test_evaluator_failure_is_not_unknown_and_can_be_associated_with_run() -> None:
    class BrokenEvaluator:
        identity = EvaluatorIdentity("judge", "1")
        deterministic = True

        def evaluate(self, value: object):  # type: ignore[no-untyped-def]
            raise RuntimeError("planted-secret")

    failure = EvaluatorRunner(clock=FakeClock()).evaluate(BrokenEvaluator(), object())
    assert isinstance(failure, EvaluationExecutionFailure)
    with _sdk().run(agent_id="a", name="A", version="1") as run:
        run.record_evaluation_failure(failure=failure)
    assert run.measurement_health.health is MeasurementHealth.UNAVAILABLE
    assert MeasurementHealthReason.EVALUATOR_EXECUTION_FAILURE in (
        run.measurement_health.reasons
    )


def test_timestamp_failure_has_distinct_reason() -> None:
    result = EvaluatorRunner(clock=BrokenClock()).evaluate(
        EqualityEvaluator(EvaluatorIdentity("judge", "1"), "ok"), "ok"
    )
    assert isinstance(result, EvaluationExecutionFailure)
    assert result.stage is EvaluationFailureStage.TIMESTAMP
    with _sdk().run(agent_id="a", name="A", version="1") as run:
        run.record_evaluation_failure(failure=result)
    assert run.measurement_health.reasons == frozenset(
        {MeasurementHealthReason.EVALUATION_TIMESTAMP_FAILURE}
    )
    with pytest.raises(RuntimeError, match="closed"):
        run.record_evaluation_failure(failure=result)


def test_evaluation_failure_association_rejects_wrong_type() -> None:
    with (
        _sdk().run(agent_id="a", name="A", version="1") as run,
        pytest.raises(TypeError, match="EvaluationExecutionFailure"),
    ):
        run.record_evaluation_failure(failure=object())  # type: ignore[arg-type]


def test_diagnostic_and_optional_bridge_failures_do_not_change_health() -> None:
    class BrokenBridge:
        def start(self, run):  # type: ignore[no-untyped-def]
            raise RuntimeError("bridge start failed")

    with _sdk(
        sink=BrokenSink(),
        diagnostic_handler=BrokenDiagnosticHandler(),
        run_context_bridge=BrokenBridge(),
    ).run(agent_id="a", name="A", version="1") as run:
        pass
    assert run.measurement_health.reasons == frozenset(
        {MeasurementHealthReason.EVENT_DELIVERY_FAILURE}
    )

    class BrokenFinishScope:
        def finish(self, *, status, exception_type):  # type: ignore[no-untyped-def]
            raise RuntimeError("bridge finish failed")

    class FinishBridge:
        def start(self, run):  # type: ignore[no-untyped-def]
            return BrokenFinishScope()

    with _sdk(run_context_bridge=FinishBridge()).run(
        agent_id="a", name="A", version="1"
    ) as finish_run:
        pass
    assert finish_run.measurement_health.health is MeasurementHealth.HEALTHY


def test_policy_result_and_failures_are_application_owned() -> None:
    @dataclass(frozen=True)
    class Decision:
        mode: str

    class Policy:
        def evaluate(self, *, measurement_health: MeasurementHealthReport) -> Decision:
            return Decision("application-choice")

    with _sdk().run(agent_id="a", name="A", version="1") as run:
        assert run.evaluate_measurement_policy(Policy()) == Decision(
            "application-choice"
        )

        class BrokenPolicy:
            def evaluate(self, *, measurement_health: MeasurementHealthReport) -> None:
                raise LookupError("application policy failed")

        with pytest.raises(LookupError, match="application policy failed"):
            run.evaluate_measurement_policy(BrokenPolicy())


async def test_async_runs_and_nested_runs_are_isolated_and_run_local() -> None:
    async def one(broken: bool) -> tuple[str, MeasurementHealth]:
        sdk = _sdk(sink=BrokenSink()) if broken else _sdk()
        async with sdk.run(agent_id=str(broken), name="A", version="1") as run:
            await asyncio.sleep(0)
        return str(broken), run.measurement_health.health

    assert dict(await asyncio.gather(one(False), one(True))) == {
        "False": MeasurementHealth.HEALTHY,
        "True": MeasurementHealth.DEGRADED,
    }

    with _sdk().run(agent_id="parent", name="P", version="1") as parent:
        with _sdk(
            sink=BrokenSink(),
            run_id_generator=SequentialRunIdGenerator("child"),
        ).run(agent_id="child", name="C", version="1") as child:
            pass
        assert child.measurement_health.health is MeasurementHealth.DEGRADED
        assert parent.measurement_health.health is MeasurementHealth.HEALTHY

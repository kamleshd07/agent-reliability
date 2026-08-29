from __future__ import annotations

import asyncio
import gc
import weakref
from fractions import Fraction

from agent_reliability.domain import (
    EvaluationOutcome,
    ObjectiveDirection,
    Slo,
    UnknownPolicy,
)
from agent_reliability.evaluation import (
    EqualityEvaluator,
    EvaluationDecision,
    EvaluationExecutionFailure,
    EvaluationResult,
    EvaluatorIdentity,
)
from agent_reliability.measurement import (
    MeasurementHealth,
    MeasurementHealthReason,
    MeasurementHealthReport,
)
from agent_reliability.ports import Clock, EventSink, RunContextBridge
from agent_reliability.reliability import (
    AggregationConflict,
    ReliabilityObservation,
    evaluate_reliability,
)
from agent_reliability.sdk import (
    AgentReliability,
    DiagnosticHandler,
    EvaluatorRunner,
    current_run,
)
from tests.fakes.clock import BrokenClock, FakeClock
from tests.fakes.diagnostics import BrokenDiagnosticHandler, CollectingDiagnosticHandler
from tests.fakes.id_generator import SequentialRunIdGenerator
from tests.fakes.sinks import BrokenSink, RecordingSink


class _BrokenEvaluator:
    identity = EvaluatorIdentity("broken-check", "1")
    deterministic = True

    def evaluate(self, value: object) -> EvaluationDecision:
        raise RuntimeError("evaluator failed")


class _UnknownEvaluator:
    identity = EvaluatorIdentity("unknown-check", "1")
    deterministic = True

    def evaluate(self, value: object) -> EvaluationDecision:
        return EvaluationDecision(EvaluationOutcome.UNKNOWN, "insufficient_evidence")


class _BrokenBridge:
    def start(self, run: object) -> object:
        raise RuntimeError("bridge failed")


class _BrokenFinishScope:
    def finish(self, *, status: object, exception_type: str | None) -> None:
        raise RuntimeError("bridge finish failed")


class _BrokenFinishBridge:
    def start(self, run: object) -> _BrokenFinishScope:
        return _BrokenFinishScope()


def _sdk(
    prefix: str,
    *,
    sink: EventSink | None = None,
    clock: Clock | None = None,
    run_context_bridge: RunContextBridge | None = None,
    diagnostic_handler: DiagnosticHandler | None = None,
) -> AgentReliability:
    return AgentReliability(
        sink=sink if sink is not None else RecordingSink(),
        clock=clock if clock is not None else FakeClock(),
        run_id_generator=SequentialRunIdGenerator(prefix),
        run_context_bridge=run_context_bridge,
        diagnostic_handler=diagnostic_handler,
    )


def _failure() -> EvaluationExecutionFailure:
    result = EvaluatorRunner(
        clock=FakeClock(), diagnostic_handler=BrokenDiagnosticHandler()
    ).evaluate(_BrokenEvaluator(), object())
    assert isinstance(result, EvaluationExecutionFailure)
    return result


def test_evaluator_failure_plus_diagnostic_failure_is_non_recursive() -> None:
    failure = _failure()
    body_ran = False
    with _sdk("combo").run(agent_id="a", name="A", version="1") as run:
        body_ran = True
        run.record_evaluation_failure(failure=failure)
    assert body_ran
    assert run.measurement_health.health is MeasurementHealth.UNAVAILABLE
    assert run.measurement_health.reasons == frozenset(
        {MeasurementHealthReason.EVALUATOR_EXECUTION_FAILURE}
    )


def test_sink_plus_bridge_failures_compose_without_changing_bridge_semantics() -> None:
    diagnostics = CollectingDiagnosticHandler()
    with _sdk(
        "combined",
        sink=BrokenSink(),
        run_context_bridge=_BrokenBridge(),
        diagnostic_handler=diagnostics,
    ).run(agent_id="a", name="A", version="1") as run:
        pass
    assert run.measurement_health.reasons == frozenset(
        {MeasurementHealthReason.EVENT_DELIVERY_FAILURE}
    )
    assert {(item.component, item.operation) for item in diagnostics.diagnostics} == {
        ("run_context_bridge", "start"),
        ("sink", "emit"),
    }


def test_clock_plus_diagnostic_failure_keeps_body_running() -> None:
    body_ran = False
    with _sdk(
        "clock",
        clock=BrokenClock(),
        diagnostic_handler=BrokenDiagnosticHandler(),
    ).run(agent_id="a", name="A", version="1") as run:
        body_ran = True
    assert body_ran
    assert run.measurement_health.health is MeasurementHealth.UNAVAILABLE


def test_failure_order_does_not_change_final_health() -> None:
    snapshots: list[MeasurementHealthReport] = []
    for evaluator_first in (True, False):
        with _sdk("order", sink=BrokenSink()).run(
            agent_id="a", name="A", version="1"
        ) as run:
            if evaluator_first:
                run.record_evaluation_failure(failure=_failure())
                run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)
            else:
                run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)
                run.record_evaluation_failure(failure=_failure())
        snapshots.append(run.measurement_health)
    assert snapshots[0] == snapshots[1]
    assert snapshots[0].health is MeasurementHealth.UNAVAILABLE
    assert snapshots[0].reasons == frozenset(
        {
            MeasurementHealthReason.EVENT_DELIVERY_FAILURE,
            MeasurementHealthReason.EVALUATOR_EXECUTION_FAILURE,
        }
    )


def test_parent_child_siblings_and_deep_nesting_remain_run_local() -> None:
    with _sdk("parent", sink=BrokenSink()).run(
        agent_id="parent", name="Parent", version="1"
    ) as parent:
        with (
            _sdk("healthy-child").run(
                agent_id="healthy", name="Healthy", version="1"
            ) as healthy_child,
            _sdk("grandchild", sink=BrokenSink()).run(
                agent_id="grandchild", name="Grandchild", version="1"
            ) as grandchild,
        ):
            assert current_run() is grandchild
        with _sdk("unavailable-child", clock=BrokenClock()).run(
            agent_id="unavailable", name="Unavailable", version="1"
        ) as unavailable_child:
            assert current_run() is parent
        with _sdk("second-child").run(
            agent_id="second", name="Second", version="1"
        ) as second_child:
            pass

    assert parent.measurement_health.health is MeasurementHealth.DEGRADED
    assert healthy_child.measurement_health.health is MeasurementHealth.HEALTHY
    assert grandchild.measurement_health.health is MeasurementHealth.DEGRADED
    assert unavailable_child.measurement_health.health is MeasurementHealth.UNAVAILABLE
    assert second_child.measurement_health.health is MeasurementHealth.HEALTHY
    assert current_run() is None


async def test_many_mixed_async_runs_have_no_context_or_health_leakage() -> None:
    gate = asyncio.Event()

    async def execute(index: int) -> tuple[int, MeasurementHealth]:
        mode = index % 4
        sink: EventSink | None = None
        bridge: RunContextBridge | None = None
        if mode == 1:
            sink = BrokenSink()
        elif mode == 2:
            bridge = _BrokenBridge()
        sdk = _sdk(f"async-{index}", sink=sink, run_context_bridge=bridge)
        async with sdk.run(agent_id=str(index), name="A", version="1") as run:
            await gate.wait()
            assert current_run() is run
            if mode == 3:
                run.record_evaluation_failure(failure=_failure())
        return index, run.measurement_health.health

    tasks = [asyncio.create_task(execute(index)) for index in range(64)]
    await asyncio.sleep(0)
    gate.set()
    results = dict(await asyncio.gather(*tasks))
    for index, health in results.items():
        expected = {
            0: MeasurementHealth.HEALTHY,
            1: MeasurementHealth.DEGRADED,
            2: MeasurementHealth.HEALTHY,
            3: MeasurementHealth.UNAVAILABLE,
        }[index % 4]
        assert health is expected
    assert current_run() is None


async def test_nested_async_child_degradation_does_not_change_parent() -> None:
    async with _sdk("async-parent").run(
        agent_id="parent", name="Parent", version="1"
    ) as parent:
        async with _sdk("async-child", sink=BrokenSink()).run(
            agent_id="child", name="Child", version="1"
        ) as child:
            await asyncio.sleep(0)
            assert current_run() is child
        assert current_run() is parent
        assert child.measurement_health.health is MeasurementHealth.DEGRADED
        assert parent.measurement_health.health is MeasurementHealth.HEALTHY
    assert current_run() is None


def test_multiple_evaluators_keep_outcomes_and_partial_failure_distinct() -> None:
    runner = EvaluatorRunner(clock=FakeClock())
    decisions = [
        runner.evaluate(
            EqualityEvaluator(EvaluatorIdentity("task-success", "1"), True), True
        ),
        runner.evaluate(
            EqualityEvaluator(EvaluatorIdentity("safety-check", "1"), True), False
        ),
        runner.evaluate(_UnknownEvaluator(), object()),
        runner.evaluate(_BrokenEvaluator(), object()),
    ]
    assert [
        item.outcome for item in decisions if isinstance(item, EvaluationResult)
    ] == [EvaluationOutcome.PASS, EvaluationOutcome.FAIL, EvaluationOutcome.UNKNOWN]

    observations: list[ReliabilityObservation] = []
    with _sdk("multi").run(agent_id="a", name="A", version="1") as run:
        for indicator, decision in zip(
            ("task_success", "safety_check", "grounding_check", "schema_validity"),
            decisions,
            strict=True,
        ):
            if isinstance(decision, EvaluationResult):
                run.record_evaluation(indicator=indicator, result=decision)
                observations.append(
                    ReliabilityObservation.from_evaluation(
                        indicator=indicator, result=decision
                    )
                )
            else:
                run.record_evaluation_failure(failure=decision)
    assert len(observations) == 3
    assert run.measurement_health.health is MeasurementHealth.UNAVAILABLE


def test_multiple_successful_evaluators_leave_measurement_healthy() -> None:
    runner = EvaluatorRunner(clock=FakeClock())
    with _sdk("all-pass").run(agent_id="a", name="A", version="1") as run:
        for name in ("task-success", "safety-check", "schema-check", "grounding"):
            result = runner.evaluate(
                EqualityEvaluator(EvaluatorIdentity(name, "1"), True), True
            )
            assert isinstance(result, EvaluationResult)
            assert result.outcome is EvaluationOutcome.PASS
            run.record_evaluation(indicator=name, result=result)
    assert run.measurement_health.health is MeasurementHealth.HEALTHY


def test_provenance_conflict_and_sink_degradation_remain_independent() -> None:
    runner = EvaluatorRunner(clock=FakeClock())
    results = [
        runner.evaluate(
            EqualityEvaluator(EvaluatorIdentity("judge", version), True), True
        )
        for version in ("1", "2")
    ]
    assert all(isinstance(result, EvaluationResult) for result in results)
    completed = [result for result in results if isinstance(result, EvaluationResult)]

    with _sdk("export", sink=BrokenSink()).run(
        agent_id="a", name="A", version="1"
    ) as run:
        for result in completed:
            run.record_evaluation(indicator="task_success", result=result)
    conflict = evaluate_reliability(
        indicator="task_success",
        observations=[
            ReliabilityObservation.from_evaluation(
                indicator="task_success", result=result
            )
            for result in completed
        ],
        slo=Slo("task-success", Fraction(9, 10), ObjectiveDirection.AT_LEAST),
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    assert isinstance(conflict, AggregationConflict)
    assert conflict.measurement_health.health is MeasurementHealth.UNAVAILABLE
    assert run.measurement_health.health is MeasurementHealth.DEGRADED


def test_manual_missing_provenance_is_healthy_by_released_definition() -> None:
    observation = ReliabilityObservation.manual(
        indicator="task_success", outcome=EvaluationOutcome.PASS
    )
    report = evaluate_reliability(
        indicator="task_success",
        observations=[observation],
        slo=Slo("task-success", Fraction(1), ObjectiveDirection.AT_LEAST),
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    assert not isinstance(report, AggregationConflict)
    assert report.measurement_health.health is MeasurementHealth.HEALTHY


def test_caller_created_report_cannot_overwrite_live_run_health() -> None:
    claimed_healthy = MeasurementHealthReport()
    with _sdk("trust", sink=BrokenSink()).run(
        agent_id="a", name="A", version="1"
    ) as run:
        assert claimed_healthy.health is MeasurementHealth.HEALTHY
    assert run.measurement_health.health is MeasurementHealth.DEGRADED
    assert run.measurement_health != claimed_healthy


def test_repeated_failure_does_not_grow_reason_history() -> None:
    with _sdk("bounded", sink=BrokenSink()).run(
        agent_id="a", name="A", version="1"
    ) as run:
        for _ in range(10_000):
            run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)
    assert run.measurement_health.reasons == frozenset(
        {MeasurementHealthReason.EVENT_DELIVERY_FAILURE}
    )


def test_evaluator_failure_does_not_retain_input_or_exception() -> None:
    class Payload:
        pass

    class SensitiveFailure(RuntimeError):
        pass

    class FailingEvaluator:
        identity = EvaluatorIdentity("retention-check", "1")
        deterministic = True

        def evaluate(self, value: object) -> EvaluationDecision:
            raise SensitiveFailure(value)

    payload = Payload()
    reference = weakref.ref(payload)
    result = EvaluatorRunner(
        clock=FakeClock(), diagnostic_handler=BrokenDiagnosticHandler()
    ).evaluate(FailingEvaluator(), payload)
    assert isinstance(result, EvaluationExecutionFailure)
    del payload
    gc.collect()
    assert reference() is None


def test_broken_finish_bridge_does_not_change_healthy_local_evidence() -> None:
    with _sdk("finish", run_context_bridge=_BrokenFinishBridge()).run(
        agent_id="a", name="A", version="1"
    ) as run:
        pass
    assert run.measurement_health.health is MeasurementHealth.HEALTHY

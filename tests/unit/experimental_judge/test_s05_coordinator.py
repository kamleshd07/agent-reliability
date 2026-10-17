"""P29-S05: JudgeCoordinator and EvaluationScope (AC01-AC08)."""

from __future__ import annotations

import asyncio
import math
import threading
from decimal import Decimal
from typing import Any

import pytest

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.domain.measurement_health import (
    MeasurementHealth,
)
from agent_reliability.evaluation import EqualityEvaluator, EvaluatorIdentity
from agent_reliability.experimental.judge import (
    BudgetTracker,
    EvaluationDisposition,
    IndicatorBinding,
    JudgeBudget,
    JudgeCoordinator,
    JudgeInvocationReport,
    JudgeLimits,
    LLMJudge,
    ProviderReply,
    SamplingPolicy,
    SyncLLMJudge,
)
from agent_reliability.experimental.judge.testing import (
    HANG,
    FakeProvider,
    FakeSyncProvider,
    judge_reply,
)
from agent_reliability.ports.events import EvaluationRecorded
from agent_reliability.sdk import AgentReliability
from tests.fakes.p29_judge import (
    SECRET,
    HealthSink,
    LegacyHandle,
    good_reply,
    grounded_request,
    named_rubrics,
)

pytestmark = pytest.mark.unit

GR = named_rubrics()["gr-cit"]


def make_judge(provider: Any, **kw: Any) -> LLMJudge:
    kw.setdefault("jitter", lambda: 0.0)
    return LLMJudge(rubric=GR, provider=provider, model_label="coord", **kw)


class Collect:
    def __init__(self) -> None:
        self.reports: list[JudgeInvocationReport] = []

    def on_report(self, report: JudgeInvocationReport) -> None:
        self.reports.append(report)


def sdk_with(sink: HealthSink | None = None) -> tuple[AgentReliability, HealthSink]:
    sink = sink or HealthSink()
    return AgentReliability(sink=sink), sink  # type: ignore[arg-type]


def start_run(sdk: AgentReliability) -> Any:
    return sdk.run(agent_id="a", name="Agent", version="1")


def results(sink: HealthSink) -> list[EvaluationRecorded]:
    return [e for e in sink.events if isinstance(e, EvaluationRecorded)]


# ---------------------------------------------------------------- AC01 sampling


def test_p29_s05_ac01_sampling_is_pure_function_of_salt_and_run_id() -> None:
    policy = SamplingPolicy(rate=0.37, salt="s")
    ids = [f"run-{i}" for i in range(500)]
    assert [policy.decide(i) for i in ids] == [policy.decide(i) for i in ids]
    assert SamplingPolicy(rate=0.37, salt="t").decide("x") in (True, False)


def test_p29_s05_ac01_observed_rate_within_statistical_bound() -> None:
    n, rate = 20_000, 0.3
    policy = SamplingPolicy(rate=rate, salt="stat")
    observed = sum(policy.decide(f"run-{i}") for i in range(n)) / n
    sigma = math.sqrt(rate * (1 - rate) / n)
    assert abs(observed - rate) < 5 * sigma  # stated bound: 5 standard errors


def test_p29_s05_ac01_rate_zero_never_one_always_and_invalid_rejected() -> None:
    ids = [f"r{i}" for i in range(1000)]
    assert not any(SamplingPolicy(rate=0).decide(i) for i in ids)
    assert all(SamplingPolicy(rate=1).decide(i) for i in ids)
    for bad in (math.nan, -0.1, 1.1, math.inf):
        with pytest.raises(ValueError):
            SamplingPolicy(rate=bad)


def test_p29_s05_ac01_unsampled_records_nothing_and_is_observed() -> None:
    sdk, sink = sdk_with()
    provider = FakeProvider([good_reply()])
    observer = Collect()
    coordinator = JudgeCoordinator(
        [
            IndicatorBinding(
                "groundedness", make_judge(provider), SamplingPolicy(rate=0)
            )
        ],
        observer=observer,
    )

    async def go() -> EvaluationDisposition:
        with start_run(sdk) as run, coordinator.scope(run) as scope:
            return await scope.evaluate("groundedness", grounded_request())

    assert asyncio.run(go()) is EvaluationDisposition.SKIPPED_UNSAMPLED
    assert provider.call_count == 0
    assert results(sink) == [] and sink.failures == []
    assert [r.kind for r in observer.reports] == ["skipped_unsampled"]
    cov = coordinator.coverage().indicators[0]
    assert (cov.unsampled, cov.attempted) == (1, 0)


# ---------------------------------------------------------------- AC02 dedupe


def test_p29_s05_ac02_second_evaluation_raises_and_records_nothing() -> None:
    sdk, sink = sdk_with()
    provider = FakeProvider([good_reply(), good_reply()])
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", make_judge(provider))]
    )

    async def go() -> None:
        with start_run(sdk) as run:
            async with coordinator.scope(run) as scope:
                await scope.evaluate("groundedness", grounded_request())
                with pytest.raises(ValueError):
                    await scope.evaluate("groundedness", grounded_request())

    asyncio.run(go())
    assert len(results(sink)) == 1
    assert provider.call_count == 1


def test_p29_s05_ac02_dedupe_is_per_scope_not_global() -> None:
    sdk, sink = sdk_with()
    judge = SyncLLMJudge(
        rubric=GR,
        provider=FakeSyncProvider([good_reply(), good_reply()]),
        model_label="c",
    )
    coordinator = JudgeCoordinator([IndicatorBinding("groundedness", judge)])
    for _ in range(2):
        with start_run(sdk) as run, coordinator.scope(run) as scope:
            assert scope.evaluate_sync("groundedness", grounded_request()) is (
                EvaluationDisposition.RECORDED_RESULT
            )
    assert len(results(sink)) == 2


# ---------------------------------------------------------------- AC03 limits


def test_p29_s05_ac03_max_concurrency_reached_and_never_exceeded() -> None:
    sdk, sink = sdk_with()
    state = {"now": 0, "peak": 0}

    async def slow(call: Any) -> ProviderReply:
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.02)
        state["now"] -= 1
        return ProviderReply(good_reply())

    from agent_reliability.experimental.judge import CallableProvider

    judge = make_judge(CallableProvider(slow, provider_label="slow"))
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge)], max_concurrency=3, max_pending=64
    )

    async def one() -> EvaluationDisposition:
        with start_run(sdk) as run:
            async with coordinator.scope(run) as scope:
                return await scope.evaluate("groundedness", grounded_request())

    async def go() -> list[EvaluationDisposition]:
        return await asyncio.gather(*(one() for _ in range(12)))

    out = asyncio.run(go())
    assert all(d is EvaluationDisposition.RECORDED_RESULT for d in out)
    assert state["peak"] == 3
    assert len(results(sink)) == 12


def test_p29_s05_ac03_max_pending_sheds_with_overloaded_evidence() -> None:
    sdk, sink = sdk_with()
    gate = asyncio.Event()
    started = {"n": 0}

    async def held(call: Any) -> ProviderReply:
        started["n"] += 1
        await gate.wait()
        return ProviderReply(good_reply())

    from agent_reliability.experimental.judge import CallableProvider

    observer = Collect()
    judge = make_judge(CallableProvider(held, provider_label="held"))
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge)],
        max_concurrency=1,
        max_pending=2,
        observer=observer,
    )

    async def one() -> EvaluationDisposition:
        with start_run(sdk) as run:
            async with coordinator.scope(run) as scope:
                return await scope.evaluate("groundedness", grounded_request())

    async def go() -> list[EvaluationDisposition]:
        tasks = [asyncio.ensure_future(one()) for _ in range(5)]
        for _ in range(20):
            await asyncio.sleep(0)
        assert started["n"] == 1  # 1 running, 2 waiting, 2 shed
        gate.set()
        return await asyncio.gather(*tasks)

    out = asyncio.run(go())
    assert out.count(EvaluationDisposition.RECORDED_RESULT) == 3
    assert out.count(EvaluationDisposition.RECORDED_FAILURE) == 2
    assert sorted(f[2] for f in sink.failures) == ["JudgeOverloadedError"] * 2
    shed = [r for r in observer.reports if r.exception_type == "JudgeOverloadedError"]
    assert len(shed) == 2 and all(r.attempts == 0 for r in shed)
    assert coordinator.coverage().indicators[0].failures_by_class == (
        ("JudgeOverloadedError", 2),
    )


def test_p29_s05_ac03_max_evaluations_per_run_enforced() -> None:
    sdk, sink = sdk_with()
    bindings = [
        IndicatorBinding(f"i{n}", make_judge(FakeProvider([good_reply()])))
        for n in range(2)
    ]
    coordinator = JudgeCoordinator(bindings, max_evaluations_per_run=1)

    async def go() -> None:
        with start_run(sdk) as run:
            async with coordinator.scope(run) as scope:
                await scope.evaluate("i0", grounded_request())
                with pytest.raises(ValueError, match="max_evaluations_per_run"):
                    await scope.evaluate("i1", grounded_request())

    asyncio.run(go())
    assert len(results(sink)) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_concurrency": 0},
        {"max_concurrency": 65},
        {"max_concurrency": True},
        {"max_pending": 0},
        {"max_pending": 10_001},
        {"max_evaluations_per_run": 0},
        {"max_evaluations_per_run": 65},
        {"drain_timeout_seconds": 0},
        {"drain_timeout_seconds": math.nan},
        {"drain_timeout_seconds": True},
    ],
)
def test_p29_s05_coordinator_parameter_bounds(kwargs: dict[str, Any]) -> None:
    binding = IndicatorBinding("groundedness", make_judge(FakeProvider([])))
    with pytest.raises((ValueError, TypeError)):
        JudgeCoordinator([binding], **kwargs)
    for good in (
        {"max_concurrency": 64, "max_pending": 10_000, "max_evaluations_per_run": 64},
        {"max_concurrency": 1, "max_pending": 1, "max_evaluations_per_run": 1},
    ):
        JudgeCoordinator([binding], **good)


def test_p29_s05_binding_validation() -> None:
    judge = make_judge(FakeProvider([]))
    with pytest.raises(ValueError):
        IndicatorBinding("", judge)
    with pytest.raises(ValueError):
        IndicatorBinding("x" * 201, judge)
    with pytest.raises(ValueError):
        IndicatorBinding("bad\nname", judge)
    IndicatorBinding("x" * 200, judge)
    with pytest.raises(TypeError):
        IndicatorBinding("x", object())
    with pytest.raises(TypeError):
        IndicatorBinding("x", judge, sampling=0.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        JudgeCoordinator([IndicatorBinding("a", judge), IndicatorBinding("a", judge)])
    with pytest.raises(TypeError):
        JudgeCoordinator([])
    with pytest.raises(TypeError):
        JudgeCoordinator([IndicatorBinding("a", judge)], observer=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        JudgeCoordinator([IndicatorBinding("a", judge)], runner="r")  # type: ignore[arg-type]


# ---------------------------------------------------------------- AC05 cancel/drain


def test_p29_s05_ac05_cancelling_a_scope_records_nothing_and_propagates() -> None:
    sdk, sink = sdk_with()
    cancelled = {"flag": False}

    async def hang(call: Any) -> ProviderReply:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled["flag"] = True
            raise
        return ProviderReply("x")

    from agent_reliability.experimental.judge import CallableProvider

    observer = Collect()
    judge = make_judge(CallableProvider(hang, provider_label="hang"))
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge)], observer=observer
    )

    async def body() -> None:
        with start_run(sdk) as run:
            async with coordinator.scope(run) as scope:
                scope.submit("groundedness", grounded_request())
                await asyncio.sleep(0.01)
                await asyncio.Event().wait()

    async def go() -> None:
        task = asyncio.ensure_future(body())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        leftover = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        assert leftover == []

    asyncio.run(go())
    assert cancelled["flag"] is True
    assert results(sink) == [] and sink.failures == []
    kinds = [r.kind for r in observer.reports]
    assert kinds == ["cancelled"]


def test_p29_s05_ac05_drain_timeout_records_timeout_failure_while_run_open() -> None:
    sdk, sink = sdk_with()
    judge = make_judge(
        FakeProvider([HANG]), limits=JudgeLimits(provider_timeout_seconds=60)
    )
    observer = Collect()
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge)],
        drain_timeout_seconds=0.05,
        observer=observer,
    )

    async def go() -> MeasurementHealth:
        with start_run(sdk) as run:
            async with coordinator.scope(run) as scope:
                scope.submit("groundedness", grounded_request())
            leftover = [
                t for t in asyncio.all_tasks() if t is not asyncio.current_task()
            ]
            assert leftover == []
            return run.measurement_health.health  # type: ignore[no-any-return]

    assert asyncio.run(go()) is MeasurementHealth.UNAVAILABLE
    assert [f[2] for f in sink.failures] == ["JudgeTimeoutError"]
    assert [r.kind for r in observer.reports] == ["failure"]
    assert observer.reports[0].exception_type == "JudgeTimeoutError"


def test_p29_s05_ac05_submit_drains_normally_before_exit() -> None:
    sdk, sink = sdk_with()
    bindings = [
        IndicatorBinding(f"i{n}", make_judge(FakeProvider([good_reply()])))
        for n in range(3)
    ]
    coordinator = JudgeCoordinator(bindings)

    async def go() -> None:
        with start_run(sdk) as run:
            async with coordinator.scope(run) as scope:
                for n in range(3):
                    scope.submit(f"i{n}", grounded_request())

    asyncio.run(go())
    assert sorted(e.indicator for e in results(sink)) == ["i0", "i1", "i2"]


def test_p29_s05_ac05_sync_drain_timeout_and_late_completion_discarded() -> None:
    sdk, sink = sdk_with()
    release = threading.Event()
    entered = threading.Event()

    def blocking(call: Any) -> ProviderReply:
        entered.set()
        release.wait(5)
        return ProviderReply(good_reply())

    from agent_reliability.experimental.judge import CallableSyncProvider

    judge = SyncLLMJudge(
        rubric=GR,
        provider=CallableSyncProvider(blocking, provider_label="blk"),
        model_label="c",
        limits=JudgeLimits(provider_timeout_seconds=60),
    )
    observer = Collect()
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge)],
        drain_timeout_seconds=0.05,
        observer=observer,
    )
    dispositions: list[EvaluationDisposition] = []
    with start_run(sdk) as run:
        with coordinator.scope(run) as scope:
            worker = threading.Thread(
                target=lambda: dispositions.append(
                    scope.evaluate_sync("groundedness", grounded_request())
                ),
                daemon=True,
            )
            worker.start()
            assert entered.wait(2)
        # scope drained: the in-flight evaluation was converted to timeout evidence
        assert [f[2] for f in sink.failures] == ["JudgeTimeoutError"]
        release.set()
        worker.join(5)
        assert not worker.is_alive()
    assert results(sink) == []  # the late PASS was discarded
    assert [f[2] for f in sink.failures] == ["JudgeTimeoutError"]
    assert dispositions == [EvaluationDisposition.RECORDED_FAILURE]
    kinds = sorted(r.kind for r in observer.reports)
    assert kinds == ["cancelled", "failure"]
    assert coordinator.coverage().indicators[0].late_discarded == 1
    assert threading.active_count() <= 2


def test_p29_s05_scope_misuse() -> None:
    sdk, _ = sdk_with()
    judge = make_judge(FakeProvider([good_reply()]))
    coordinator = JudgeCoordinator([IndicatorBinding("groundedness", judge)])
    with start_run(sdk) as run:
        scope = coordinator.scope(run)

        async def not_entered() -> None:
            await scope.evaluate("groundedness", grounded_request())

        with pytest.raises(RuntimeError):
            asyncio.run(not_entered())
        with scope:
            pass
        with pytest.raises(RuntimeError):  # used after the scope is closed
            asyncio.run(not_entered())
        with pytest.raises(RuntimeError), scope:  # entered twice
            pass
    with pytest.raises(TypeError):
        coordinator.scope("not a handle")  # type: ignore[arg-type]


# ---------------------------------------------------------------- AC06 budget


def test_p29_s05_ac06_shared_budget_across_concurrent_evaluations() -> None:
    sdk, sink = sdk_with()
    tracker = BudgetTracker(JudgeBudget(max_tokens_per_window=100))

    async def one(coordinator: JudgeCoordinator) -> EvaluationDisposition:
        with start_run(sdk) as run:
            async with coordinator.scope(run) as scope:
                return await scope.evaluate("groundedness", grounded_request())

    def build() -> JudgeCoordinator:
        provider = FakeProvider(
            [ProviderReply(good_reply(), input_tokens=30, output_tokens=20)] * 20,
            reports_tokens=True,
        )
        judge = make_judge(provider, budget=tracker)
        return JudgeCoordinator(
            [IndicatorBinding("groundedness", judge)], max_concurrency=2
        )

    coordinator = build()

    async def go() -> None:
        await asyncio.gather(*(one(coordinator) for _ in range(10)))

    asyncio.run(go())
    successes = len(results(sink))
    failures = [f for f in sink.failures if f[2] == "JudgeBudgetExceededError"]
    # limit 100 / 50 per call: 2 complete, plus at most max_concurrency in flight
    assert 2 <= successes <= 4
    assert len(failures) == 10 - successes
    assert tracker.totals()[0] <= 100 + 2 * 50  # documented overshoot bound
    cov = coordinator.coverage().indicators[0]
    assert dict(cov.failures_by_class)["JudgeBudgetExceededError"] == len(failures)


def test_p29_s05_ac06_cost_budget_object_shared_between_judges() -> None:
    tracker = BudgetTracker(
        JudgeBudget(
            max_cost_per_window=Decimal("0.001"),
            input_price_per_1k_tokens=Decimal("1"),
            output_price_per_1k_tokens=Decimal("1"),
        )
    )
    tracker.record(1, 0)
    assert tracker.totals()[1] == Decimal("0.001")
    with pytest.raises(Exception, match="budget"):
        tracker.check()


# ---------------------------------------------------------------- AC07 reports


def test_p29_s05_ac07_reports_are_content_free_and_reason_is_opt_in() -> None:
    sdk, _sink = sdk_with()
    reply = judge_reply("pass", "supported_by_context", "high", [0], reason="because")
    observer = Collect()
    from agent_reliability.experimental.judge import JudgePolicy

    off = make_judge(FakeProvider([reply]))
    on = make_judge(FakeProvider([reply]), policy=JudgePolicy(capture_reason=True))
    coordinator = JudgeCoordinator(
        [IndicatorBinding("a", off), IndicatorBinding("b", on)], observer=observer
    )

    async def go() -> None:
        with start_run(sdk) as run:
            async with coordinator.scope(run) as scope:
                await scope.evaluate("a", grounded_request(answer=SECRET))
                await scope.evaluate("b", grounded_request(answer=SECRET))

    asyncio.run(go())
    by_indicator = {r.indicator: r for r in observer.reports}
    assert by_indicator["a"].reason_text is None
    assert by_indicator["b"].reason_text == "because"
    for report in observer.reports:
        assert SECRET not in repr(report) and "because" not in repr(report)
        assert report.outcome is EvaluationOutcome.PASS
        assert report.reason_code == "groundedness.supported_by_context"
        assert (
            report.attempts == 1
            and report.latency_ms >= 0
            and report.queue_wait_ms >= 0
        )


def test_p29_s05_ac07_observer_exceptions_are_suppressed_and_counted() -> None:
    sdk, sink = sdk_with()

    class Boom:
        def on_report(self, report: JudgeInvocationReport) -> None:
            raise RuntimeError(SECRET)

    judge = make_judge(FakeProvider([good_reply()]))
    coordinator = JudgeCoordinator([IndicatorBinding("a", judge)], observer=Boom())

    async def go() -> EvaluationDisposition:
        with start_run(sdk) as run:
            async with coordinator.scope(run) as scope:
                return await scope.evaluate("a", grounded_request())

    assert asyncio.run(go()) is EvaluationDisposition.RECORDED_RESULT
    assert coordinator.coverage().observer_errors == 1
    assert len(results(sink)) == 1


# ---------------------------------------------------------------- AC08 recording paths


def test_p29_s05_ac08_results_and_failures_reach_the_sink_with_indicator() -> None:
    sdk, sink = sdk_with()
    ok = make_judge(FakeProvider([good_reply()]))
    bad = make_judge(FakeProvider([RuntimeError(SECRET)]))
    observer = Collect()
    coordinator = JudgeCoordinator(
        [IndicatorBinding("ok", ok), IndicatorBinding("bad", bad)], observer=observer
    )

    async def go() -> MeasurementHealth:
        with start_run(sdk) as run:
            async with coordinator.scope(run) as scope:
                assert await scope.evaluate("ok", grounded_request()) is (
                    EvaluationDisposition.RECORDED_RESULT
                )
                assert await scope.evaluate("bad", grounded_request()) is (
                    EvaluationDisposition.RECORDED_FAILURE
                )
            return run.measurement_health.health  # type: ignore[no-any-return]

    assert asyncio.run(go()) is MeasurementHealth.UNAVAILABLE
    (event,) = results(sink)
    assert event.provenance is not None and event.provenance.deterministic is False
    assert event.reason_code == "groundedness.supported_by_context"
    assert [(f[1], f[2]) for f in sink.failures] == [("bad", "JudgeProviderError")]
    failure_report = next(r for r in observer.reports if r.kind == "failure")
    assert failure_report.failure_evidence_delivered is True
    assert coordinator.coverage().failure_evidence_not_delivered == 0


def test_p29_s05_ac08_handle_without_indicator_falls_back_to_local_health() -> None:
    sdk, sink = sdk_with()
    bad = make_judge(FakeProvider([RuntimeError(SECRET)]))
    observer = Collect()
    coordinator = JudgeCoordinator([IndicatorBinding("bad", bad)], observer=observer)

    async def go() -> tuple[LegacyHandle, MeasurementHealth]:
        with start_run(sdk) as run:
            legacy = LegacyHandle(run)
            async with coordinator.scope(legacy) as scope:  # type: ignore[arg-type]
                await scope.evaluate("bad", grounded_request())
            return legacy, run.measurement_health.health

    legacy, health = asyncio.run(go())
    assert len(legacy.failure_calls) == 1  # called without ``indicator=``
    assert sink.failures == []  # nothing delivered on the wire path
    assert health is MeasurementHealth.UNAVAILABLE  # local run health only
    (report,) = observer.reports
    assert report.failure_evidence_delivered is False
    assert coordinator.coverage().failure_evidence_not_delivered == 1


def test_p29_s05_ac08_event_sink_only_failure_is_local_health_only() -> None:
    from tests.fakes.sinks import RecordingSink

    plain = RecordingSink()
    sdk = AgentReliability(sink=plain)
    bad = make_judge(FakeProvider([RuntimeError("x")]))
    coordinator = JudgeCoordinator([IndicatorBinding("bad", bad)])

    async def go() -> MeasurementHealth:
        with start_run(sdk) as run:
            async with coordinator.scope(run) as scope:
                await scope.evaluate("bad", grounded_request())
            return run.measurement_health.health  # type: ignore[no-any-return]

    assert asyncio.run(go()) is MeasurementHealth.UNAVAILABLE
    assert not any(isinstance(e, EvaluationRecorded) for e in plain.events)


def test_p29_s05_ac08_degraded_run_skips_without_provider_call() -> None:
    class BadIds:
        def generate(self) -> str:
            raise RuntimeError("no ids")

    sdk = AgentReliability(run_id_generator=BadIds())  # type: ignore[arg-type]
    provider = FakeProvider([good_reply()])
    observer = Collect()
    coordinator = JudgeCoordinator(
        [IndicatorBinding("a", make_judge(provider))], observer=observer
    )

    async def go() -> EvaluationDisposition:
        with start_run(sdk) as run:
            assert run.run_id is None
            async with coordinator.scope(run) as scope:
                return await scope.evaluate("a", grounded_request())

    assert asyncio.run(go()) is EvaluationDisposition.SKIPPED_RUN_NOT_RECORDING
    assert provider.call_count == 0
    assert [r.kind for r in observer.reports] == ["skipped_run_not_recording"]


def test_p29_s05_ac08_closed_run_surfaces_runtime_error() -> None:
    sdk, _sink = sdk_with()
    judge = make_judge(FakeProvider([good_reply()]))
    coordinator = JudgeCoordinator([IndicatorBinding("a", judge)])

    async def go() -> None:
        with start_run(sdk) as run:
            pass
        async with coordinator.scope(run) as scope:
            await scope.evaluate("a", grounded_request())

    with pytest.raises(RuntimeError, match="closed run"):
        asyncio.run(go())


def test_p29_s05_ac08_deterministic_model_backed_binding_rejected() -> None:
    class Fake:
        identity = EvaluatorIdentity("model-ish", "1")
        deterministic = True
        model_backed = True

        def evaluate(self, value: Any) -> Any: ...

    with pytest.raises(ValueError, match="model-backed"):
        IndicatorBinding("x", Fake())
    det = EqualityEvaluator(EvaluatorIdentity("eq", "1"), 1)
    IndicatorBinding("exact-match", det)  # a plain deterministic evaluator is allowed
    with pytest.raises(ValueError, match="task-completion-evidence"):
        IndicatorBinding("task-completion-evidence", det)


def test_p29_s05_dimension_mismatch_is_unrecorded_programmer_error() -> None:
    from tests.fakes.p29_judge import correctness_request

    sdk, sink = sdk_with()
    provider = FakeProvider([good_reply()])
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", make_judge(provider))]
    )

    async def go() -> None:
        with start_run(sdk) as run:
            async with coordinator.scope(run) as scope:
                with pytest.raises(ValueError):
                    await scope.evaluate("groundedness", correctness_request())
                with pytest.raises(ValueError):
                    await scope.evaluate("unbound", grounded_request())
                with pytest.raises(TypeError):
                    await scope.evaluate("groundedness", "text")  # type: ignore[arg-type]
                # the failed attempts consumed nothing: a valid call still works
                assert await scope.evaluate("groundedness", grounded_request()) is (
                    EvaluationDisposition.RECORDED_RESULT
                )

    asyncio.run(go())
    assert sink.failures == [] and len(results(sink)) == 1


def test_p29_s05_async_and_sync_entry_points_are_not_interchangeable() -> None:
    sdk, _ = sdk_with()
    a = make_judge(FakeProvider([]))
    s = SyncLLMJudge(rubric=GR, provider=FakeSyncProvider([]), model_label="c")
    coordinator = JudgeCoordinator([IndicatorBinding("a", a), IndicatorBinding("s", s)])
    with start_run(sdk) as run, coordinator.scope(run) as scope:
        with pytest.raises(TypeError):
            scope.evaluate_sync("a", grounded_request())

        async def wrong() -> None:
            await scope.evaluate("s", grounded_request())

        with pytest.raises(TypeError):
            asyncio.run(wrong())

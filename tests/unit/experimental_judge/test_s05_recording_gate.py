"""P29-S05-AC04 and AC09: serialized recording and concurrency consistency."""

from __future__ import annotations

import asyncio
import hashlib
import pathlib
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from agent_reliability.domain.measurement_health import (
    MeasurementHealth,
    MeasurementHealthReason,
)
from agent_reliability.experimental.judge import (
    CallableProvider,
    CallableSyncProvider,
    EvaluationDisposition,
    IndicatorBinding,
    JudgeCoordinator,
    JudgeInvocationReport,
    LLMJudge,
    ProviderReply,
    SyncLLMJudge,
)
from agent_reliability.ports.events import EvaluationRecorded
from agent_reliability.sdk import AgentReliability
from tests.fakes.p29_baseline import load_baseline
from tests.fakes.p29_judge import (
    HealthSink,
    OverlapHandle,
    good_reply,
    grounded_request,
    named_rubrics,
)

pytestmark = pytest.mark.unit

GR = named_rubrics()["gr-cit"]
N = 64
ROOT = pathlib.Path(__file__).resolve().parents[3]


class Probe:
    """Observer + provider instrumentation: nothing may run under the gate."""

    def __init__(self) -> None:
        self.handle: Any = None
        self.reports: list[JudgeInvocationReport] = []
        self.gate_held_in_provider = 0
        self.gate_held_in_observer = 0
        self.nonces: list[str] = []
        self.now = 0
        self.peak = 0
        self._lock = threading.Lock()

    def on_report(self, report: JudgeInvocationReport) -> None:
        if self.handle is not None and threading.get_ident() in self.handle.holders:
            self.gate_held_in_observer += 1
        with self._lock:
            self.reports.append(report)

    def enter(self, call: Any) -> None:
        if self.handle is not None and threading.get_ident() in self.handle.holders:
            self.gate_held_in_provider += 1
        match = re.search(r"<<<BEGIN ([0-9a-f]{16})", call.user)
        with self._lock:
            if match:
                self.nonces.append(match.group(1))
            self.now += 1
            self.peak = max(self.peak, self.now)

    def leave(self) -> None:
        with self._lock:
            self.now -= 1


def _fails(i: int) -> bool:
    return i % 3 == 0  # a third fail, the rest pass


def _build_async(probe: Probe, hold: float) -> list[IndicatorBinding]:
    bindings = []
    for i in range(N):

        async def fn(call: Any, i: int = i) -> ProviderReply:
            probe.enter(call)
            try:
                await asyncio.sleep(hold)
                if _fails(i):
                    raise RuntimeError("provider down")
                return ProviderReply(good_reply())
            finally:
                probe.leave()

        judge = LLMJudge(
            rubric=GR,
            provider=CallableProvider(fn, provider_label=f"p{i}"),
            model_label="stress",
            jitter=lambda: 0.0,
        )
        bindings.append(IndicatorBinding(f"ind-{i:02d}", judge))
    return bindings


def _build_sync(probe: Probe, hold: float) -> list[IndicatorBinding]:
    bindings = []
    for i in range(N):

        def fn(call: Any, i: int = i) -> ProviderReply:
            probe.enter(call)
            try:
                threading.Event().wait(hold)
                if _fails(i):
                    raise RuntimeError("provider down")
                return ProviderReply(good_reply())
            finally:
                probe.leave()

        judge = SyncLLMJudge(
            rubric=GR,
            provider=CallableSyncProvider(fn, provider_label=f"p{i}"),
            model_label="stress",
            jitter=lambda: 0.0,
        )
        bindings.append(IndicatorBinding(f"ind-{i:02d}", judge))
    return bindings


def _check(
    sink: HealthSink,
    handle: OverlapHandle,
    probe: Probe,
    coordinator: JudgeCoordinator,
    dispositions: list[EvaluationDisposition],
) -> None:
    expected_fail = sum(_fails(i) for i in range(N))
    results = [e for e in sink.events if isinstance(e, EvaluationRecorded)]
    # AC09(a): no overlap; exactly-once; counts and health consistent.
    assert handle.overlaps == 0
    assert sink.overlaps == 0
    assert len(results) == N - expected_fail
    assert len({e.indicator for e in results}) == len(results)
    assert len(sink.failures) == expected_fail
    assert len({f[1] for f in sink.failures}) == expected_fail
    assert handle.calls == N
    assert handle.measurement_health.health is MeasurementHealth.UNAVAILABLE
    assert handle.measurement_health.reasons == frozenset(
        {MeasurementHealthReason.EVALUATOR_EXECUTION_FAILURE}
    )
    assert len(dispositions) == N
    # AC04: counters consistent, nonces never reused.
    total = coordinator.coverage().total
    assert (total.attempted, total.execution_failures) == (N, expected_fail)
    assert total.passed == N - expected_fail
    assert len(probe.nonces) == len(set(probe.nonces)) == N + 0
    # AC09(b): no provider call or observer callback ran under the gate.
    assert probe.gate_held_in_provider == 0
    assert probe.gate_held_in_observer == 0
    assert len(probe.reports) == N


@pytest.mark.parametrize("delay", [0.0, 0.002])
def test_p29_s05_ac09_async_64_concurrent_evaluations_one_handle(delay: float) -> None:
    sink = HealthSink(delay=delay)  # (e) slow-but-bounded sink inside the gate
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    probe = Probe()
    coordinator = JudgeCoordinator(
        _build_async(probe, 0.01),
        max_concurrency=16,
        max_pending=N,
        max_evaluations_per_run=N,
        observer=probe,
    )

    async def go() -> tuple[OverlapHandle, list[EvaluationDisposition]]:
        with sdk.run(agent_id="a", name="A", version="1") as run:
            handle = OverlapHandle(run, delay=delay)
            async with coordinator.scope(handle) as scope:  # type: ignore[arg-type]
                probe.handle = handle
                out = await asyncio.gather(
                    *(
                        scope.evaluate(f"ind-{i:02d}", grounded_request())
                        for i in range(N)
                    )
                )
            handle.closed = True
            return handle, list(out)

    handle, dispositions = asyncio.run(go())
    _check(sink, handle, probe, coordinator, dispositions)
    assert probe.peak == 16  # concurrent execution still reaches max_concurrency
    assert handle.calls_after_close == 0


@pytest.mark.parametrize("delay", [0.0, 0.002])
def test_p29_s05_ac09_sync_64_evaluations_from_8_threads_one_handle(
    delay: float,
) -> None:
    sink = HealthSink(delay=delay)
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    probe = Probe()
    coordinator = JudgeCoordinator(
        _build_sync(probe, 0.01),
        max_concurrency=8,
        max_pending=N,
        max_evaluations_per_run=N,
        observer=probe,
    )
    with sdk.run(agent_id="a", name="A", version="1") as run:
        handle = OverlapHandle(run, delay=delay)
        with coordinator.scope(handle) as scope:  # type: ignore[arg-type]
            probe.handle = handle
            with ThreadPoolExecutor(max_workers=8) as pool:
                dispositions = list(
                    pool.map(
                        lambda i: scope.evaluate_sync(
                            f"ind-{i:02d}", grounded_request()
                        ),
                        range(N),
                    )
                )
        handle.closed = True
    _check(sink, handle, probe, coordinator, dispositions)
    assert probe.peak == 8
    assert handle.calls_after_close == 0


def test_p29_s05_ac09_mixed_async_tasks_and_threads_share_one_gate() -> None:
    sink = HealthSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    probe = Probe()
    bindings = _build_async(probe, 0.005)[:32] + _build_sync(probe, 0.005)[32:]
    coordinator = JudgeCoordinator(
        bindings,
        max_concurrency=8,
        max_pending=N,
        max_evaluations_per_run=N,
        observer=probe,
    )

    async def go() -> tuple[OverlapHandle, list[EvaluationDisposition]]:
        with sdk.run(agent_id="a", name="A", version="1") as run:
            handle = OverlapHandle(run, delay=0.0005)
            async with coordinator.scope(handle) as scope:  # type: ignore[arg-type]
                probe.handle = handle
                loop = asyncio.get_running_loop()
                async_tasks = [
                    scope.evaluate(f"ind-{i:02d}", grounded_request())
                    for i in range(32)
                ]
                with ThreadPoolExecutor(max_workers=8) as pool:
                    sync_futures = [
                        loop.run_in_executor(
                            pool,
                            lambda i=i: scope.evaluate_sync(
                                f"ind-{i:02d}", grounded_request()
                            ),
                        )
                        for i in range(32, N)
                    ]
                    out = await asyncio.gather(*async_tasks, *sync_futures)
            return handle, list(out)

    handle, dispositions = asyncio.run(go())
    _check(sink, handle, probe, coordinator, dispositions)


def test_p29_s05_ac09_c_nothing_reaches_the_handle_after_drain() -> None:
    """Covered end to end by the sync drain test; here the gate itself is checked."""
    sink = HealthSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    binding = _build_sync(Probe(), 0.0)[1]  # i=1 passes
    coordinator = JudgeCoordinator([binding])
    with sdk.run(agent_id="a", name="A", version="1") as run:
        handle = OverlapHandle(run)
        scope = coordinator.scope(handle)  # type: ignore[arg-type]
        with scope:
            pass
        with pytest.raises(RuntimeError):
            scope.evaluate_sync("ind-01", grounded_request())
    assert handle.calls == 0


def test_p29_s05_ac09_d_runhandle_runner_and_context_are_unchanged_by_p29() -> None:
    baseline = load_baseline()
    for name in (
        "src/agent_reliability/sdk/context.py",
        "src/agent_reliability/sdk/evaluator_runner.py",
        "src/agent_reliability/ports/event_sink.py",
    ):
        digest = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        assert digest == baseline[name], name  # HEAD is NOT the baseline for context.py


def test_p29_s05_ac04_no_lost_updates_across_64_tasks_in_separate_runs() -> None:
    sink = HealthSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    probe = Probe()

    async def fn(call: Any) -> ProviderReply:
        probe.enter(call)
        await asyncio.sleep(0.001)
        probe.leave()
        return ProviderReply(good_reply())

    judge = LLMJudge(
        rubric=GR, provider=CallableProvider(fn, provider_label="p"), model_label="m"
    )
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge)],
        max_concurrency=5,
        max_pending=N,
        observer=probe,
    )

    async def one() -> EvaluationDisposition:
        with sdk.run(agent_id="a", name="A", version="1") as run:
            async with coordinator.scope(run) as scope:
                return await scope.evaluate("groundedness", grounded_request())

    async def go() -> list[EvaluationDisposition]:
        return await asyncio.gather(*(one() for _ in range(N)))

    out = asyncio.run(go())
    assert out == [EvaluationDisposition.RECORDED_RESULT] * N
    cov = coordinator.coverage().indicators[0]
    assert (cov.attempted, cov.passed, cov.provider_calls) == (N, N, N)
    assert len(set(probe.nonces)) == N
    assert probe.peak <= 5
    assert len([e for e in sink.events if isinstance(e, EvaluationRecorded)]) == N

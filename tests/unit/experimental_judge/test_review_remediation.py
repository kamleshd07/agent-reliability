"""Regression tests for the independent review findings.

See docs/P29_INDEPENDENT_REVIEW.md.

Each test was mutation-checked: it fails against the unfixed code (see
docs/P29_REVIEW_REMEDIATION_REPORT.md for the mutants and results).
"""

from __future__ import annotations

import asyncio
import gc
import http.server
import pathlib
import threading
from typing import Any

import pytest

from agent_reliability.experimental.judge import (
    CallableProvider,
    CallableSyncProvider,
    EvaluationDisposition,
    IndicatorBinding,
    JudgeCoordinator,
    JudgeLimits,
    JudgeProviderUnavailableError,
    JudgeTimeoutError,
    LLMJudge,
    ProviderReply,
    SyncLLMJudge,
)
from agent_reliability.experimental.judge import coordinator as coordinator_module
from agent_reliability.experimental.judge.coordinator import _Admission
from agent_reliability.experimental.judge.testing import HANG, FakeProvider
from agent_reliability.sdk import AgentReliability
from agent_reliability.sdk.evaluator_runner import EvaluatorRunner
from tests.fakes.p29_judge import (
    HealthSink,
    OverlapHandle,
    good_reply,
    grounded_request,
    named_rubrics,
    run_virtual,
)

pytestmark = pytest.mark.unit

GR = named_rubrics()["gr-cit"]
ROOT = pathlib.Path(__file__).resolve().parents[3]


class Quiet:
    def handle(self, diagnostic: Any) -> None:
        return None


def quiet_runner() -> EvaluatorRunner:
    return EvaluatorRunner(diagnostic_handler=Quiet())  # type: ignore[arg-type]


def sync_judge(fn: Any) -> SyncLLMJudge:
    return SyncLLMJudge(
        rubric=GR,
        provider=CallableSyncProvider(fn, provider_label="p"),
        model_label="rem",
        jitter=lambda: 0.0,
        sleep=lambda _s: None,
    )


def in_thread(target: Any, seconds: float = 5.0) -> None:
    """Run ``target`` in a daemon thread; a hang becomes a test failure."""
    errors: list[BaseException] = []

    def runner() -> None:
        try:
            target()
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(seconds)
    assert not thread.is_alive(), "deadlock or hang detected"
    if errors:
        raise errors[0]


# ----------------------------------------------------------------------- F-1


def test_f1_submit_outside_a_running_loop_raises_with_no_state_change() -> None:
    sink = HealthSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    provider = FakeProvider([good_reply()])
    judge = LLMJudge(rubric=GR, provider=provider, model_label="rem")
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge)],
        runner=quiet_runner(),
        drain_timeout_seconds=10,  # the unfixed code would block this long at exit
    )
    seen: dict[str, Any] = {}

    def scenario() -> None:
        with sdk.run(agent_id="a", name="A", version="1") as run:
            with coordinator.scope(run) as scope:
                with pytest.raises(RuntimeError):
                    scope.submit("groundedness", grounded_request())
                seen["seen"] = set(scope._seen)
                seen["inflight"] = dict(scope._inflight)
            seen["health"] = run.measurement_health.health.value

    in_thread(scenario, seconds=4.0)  # exit must not drain a ghost entry
    assert seen["seen"] == set() and seen["inflight"] == {}
    assert seen["health"] == "healthy"  # no spurious JudgeTimeoutError failure
    assert sink.failures == [] and provider.call_count == 0
    assert coordinator.coverage().total.attempted == 0


def test_f1_the_indicator_stays_usable_after_a_rejected_submit() -> None:
    sink = HealthSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    judge = LLMJudge(
        rubric=GR, provider=FakeProvider([good_reply()]), model_label="rem"
    )
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge)], runner=quiet_runner()
    )
    with sdk.run(agent_id="a", name="A", version="1") as run:
        scope = coordinator.scope(run)
        with scope:
            with pytest.raises(RuntimeError):
                scope.submit("groundedness", grounded_request())

            async def later() -> EvaluationDisposition:
                return await scope.evaluate("groundedness", grounded_request())

            assert asyncio.run(later()) is EvaluationDisposition.RECORDED_RESULT


# ----------------------------------------------------------------------- F-3


def test_f3_sink_reentering_the_scope_gets_runtime_error_not_a_deadlock() -> None:
    errors: list[BaseException] = []

    class ReentrantSink(HealthSink):
        scope: Any = None

        def emit(self, event: Any) -> None:
            super().emit(event)
            if type(event).__name__ == "EvaluationRecorded" and self.scope is not None:
                try:
                    self.scope.evaluate_sync("again", grounded_request())
                except BaseException as exc:
                    errors.append(exc)

    sink = ReentrantSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    first = sync_judge(lambda c: ProviderReply(good_reply()))
    second = sync_judge(lambda c: ProviderReply(good_reply()))
    coordinator = JudgeCoordinator(
        [IndicatorBinding("first", first), IndicatorBinding("again", second)],
        runner=quiet_runner(),
    )
    out: list[EvaluationDisposition] = []

    def scenario() -> None:
        with (
            sdk.run(agent_id="a", name="A", version="1") as run,
            coordinator.scope(run) as scope,
        ):
            sink.scope = scope
            out.append(scope.evaluate_sync("first", grounded_request()))

    in_thread(scenario)
    assert out == [EvaluationDisposition.RECORDED_RESULT]
    assert len(errors) == 1 and isinstance(errors[0], RuntimeError)
    assert "re-entrant" in str(errors[0])


def test_f3_the_gate_is_released_after_a_reentry_attempt() -> None:
    sdk = AgentReliability(sink=HealthSink())  # type: ignore[arg-type]
    coordinator = JudgeCoordinator(
        [IndicatorBinding("a", sync_judge(lambda c: ProviderReply(good_reply())))],
        runner=quiet_runner(),
    )
    with sdk.run(agent_id="a", name="A", version="1") as run:
        scope = coordinator.scope(run)
        with scope:
            assert scope._holder is None and not scope._gate.locked()
            assert scope.evaluate_sync("a", grounded_request()) is (
                EvaluationDisposition.RECORDED_RESULT
            )
            assert scope._holder is None and not scope._gate.locked()


# ----------------------------------------------------------------------- F-4


class _Server:
    def __init__(self, handler: type[http.server.BaseHTTPRequestHandler]) -> None:
        self.server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/x"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)


def test_f4_default_post_json_refuses_redirects_and_never_forwards_credentials() -> (
    None
):
    from examples import judge_providers as providers

    received: list[dict[str, str]] = []

    class Target(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            received.append(dict(self.headers))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args: Any) -> None:
            return None

    target = _Server(Target)

    class Redirector(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(302)  # urllib follows 302 for POST (as GET) by default
            self.send_header("Location", target.url)
            self.end_headers()

        def log_message(self, *args: Any) -> None:
            return None

    redirector = _Server(Redirector)
    try:
        with pytest.raises(providers.HttpStatusError) as caught:
            providers.default_post_json(
                redirector.url, {"x-api-key": "KEY123"}, {"q": 1}, 5.0
            )
    finally:
        redirector.close()
        target.close()
    assert caught.value.status == 302
    assert received == []  # the second origin saw nothing: no credential forwarded


def test_f4_default_post_json_caps_the_response_size() -> None:
    from examples import judge_providers as providers

    class Big(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            payload = b'{"pad":"' + b"x" * (providers.MAX_RESPONSE_BYTES + 10) + b'"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: Any) -> None:
            return None

    server = _Server(Big)
    try:
        with pytest.raises(ValueError, match="too large"):
            providers.default_post_json(server.url, {}, {}, 5.0)
    finally:
        server.close()


def test_f4_default_post_json_still_works_for_a_plain_response() -> None:
    from examples import judge_providers as providers

    class Ok(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, *args: Any) -> None:
            return None

    server = _Server(Ok)
    try:
        assert providers.default_post_json(server.url, {}, {}, 5.0) == {"ok": True}
        with pytest.raises(ValueError):
            providers.default_post_json("http://remote.example.invalid/x", {}, {}, 1.0)
    finally:
        server.close()


# ----------------------------------------------------------------------- F-6


def test_f6_drain_recording_is_serialized_against_a_concurrent_completion() -> None:
    """Kills P01: timeout recording at drain must hold the gate."""
    sink = HealthSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    release = threading.Event()
    entered = threading.Barrier(3)

    def block(call: Any) -> ProviderReply:
        entered.wait(5)
        release.wait(10)
        return ProviderReply(good_reply())

    coordinator = JudgeCoordinator(
        [
            IndicatorBinding("i1", sync_judge(block)),
            IndicatorBinding("i2", sync_judge(block)),
            IndicatorBinding("late", sync_judge(lambda c: ProviderReply(good_reply()))),
        ],
        runner=quiet_runner(),
        drain_timeout_seconds=0.05,
    )
    results: dict[str, Any] = {}

    def call(name: str) -> None:
        try:
            results[name] = coordinator_scope.evaluate_sync(name, grounded_request())
        except BaseException as exc:
            results[name] = exc

    with sdk.run(agent_id="a", name="A", version="1") as run:
        handle = OverlapHandle(run, delay=0.15)
        coordinator_scope = coordinator.scope(handle)  # type: ignore[arg-type]
        with coordinator_scope:
            threads = [
                threading.Thread(target=call, args=(n,), daemon=True)
                for n in ("i1", "i2")
            ]
            for t in threads:
                t.start()
            entered.wait(5)

            def late() -> None:
                handle.first_record.wait(5)  # drain has started recording
                call("late")

            late_thread = threading.Thread(target=late, daemon=True)
            late_thread.start()
        late_thread.join(5)
        release.set()
        for t in threads:
            t.join(5)
    assert (
        handle.overlaps == 0
    )  # unguarded drain recording overlaps the late completion
    assert isinstance(results["late"], RuntimeError)  # the closed scope refuses it
    assert sorted(f[1] for f in sink.failures) == ["i1", "i2"]
    assert handle.calls == 2  # exactly the two timeout records


def test_f6_admission_abandoning_a_queued_waiter_and_fifo_order() -> None:
    """Kills P03 (no abandon) and P04 (FIFO bypass) at the admission level."""
    loop = asyncio.new_event_loop()
    try:
        adm = _Admission(1, 5)
        assert adm.begin(loop)[0] == "run"
        waiters = [adm.begin(loop)[1] for _ in range(3)]
        w1, w2, w3 = waiters
        assert w1 is not None and w2 is not None and w3 is not None
        adm.abandon(w1)  # cancelled while queued: removed, nothing granted
        assert not w1.granted
        adm.release()
        assert (w1.granted, w2.granted, w3.granted) == (False, True, False)  # FIFO
        adm.release()
        assert w3.granted
        adm.release()
        assert adm._running == 0 and not adm._waiters
    finally:
        loop.close()


def test_f6_admission_cancelled_after_grant_hands_the_slot_on() -> None:
    """Kills P02: a granted-but-cancelled waiter must give its slot to the next one."""
    loop = asyncio.new_event_loop()
    try:
        adm = _Admission(1, 5)
        assert adm.begin(loop)[0] == "run"
        w1 = adm.begin(loop)[1]
        w2 = adm.begin(loop)[1]
        assert w1 is not None and w2 is not None
        adm.release()  # grants w1
        assert w1.granted and not w2.granted
        adm.abandon(w1)  # w1's task was cancelled before it resumed
        assert w2.granted and adm._running == 1
        adm.release()
        assert adm._running == 0 and not adm._waiters
        # queue limits and shedding still hold afterwards
        assert adm.begin(loop)[0] == "run"
        assert [adm.begin(loop)[0] for _ in range(6)] == ["wait"] * 5 + ["shed"]
    finally:
        loop.close()


def test_f6_cancelling_queued_evaluations_returns_admission_to_idle() -> None:
    sink = HealthSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    gate = {"event": None}

    async def hold(call: Any) -> ProviderReply:
        await gate["event"].wait()  # type: ignore[attr-defined]
        return ProviderReply(good_reply())

    judge = LLMJudge(
        rubric=GR,
        provider=CallableProvider(hold, provider_label="h"),
        model_label="rem",
    )
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge)],
        runner=quiet_runner(),
        max_concurrency=1,
        max_pending=10,
    )

    async def one() -> EvaluationDisposition:
        with sdk.run(agent_id="a", name="A", version="1") as run:
            async with coordinator.scope(run) as scope:
                return await scope.evaluate("groundedness", grounded_request())

    async def go() -> list[Any]:
        gate["event"] = asyncio.Event()  # type: ignore[assignment]
        tasks = [asyncio.ensure_future(one()) for _ in range(6)]
        for _ in range(30):
            await asyncio.sleep(0)
        tasks[2].cancel()  # queued
        tasks[4].cancel()  # queued
        for _ in range(5):
            await asyncio.sleep(0)
        gate["event"].set()  # type: ignore[attr-defined]
        return await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 5)

    out = asyncio.run(go())
    assert isinstance(out[2], asyncio.CancelledError)
    assert isinstance(out[4], asyncio.CancelledError)
    done = [o for o in out if o is EvaluationDisposition.RECORDED_RESULT]
    assert len(done) == 4  # nothing hangs behind a dead waiter
    admission = coordinator._admission
    assert admission._running == 0 and not admission._waiters
    assert coordinator.coverage().total.cancelled == 2


# ----------------------------------------------------------------------- F-10


def test_f10_a_sync_waiter_interrupted_while_queued_abandons_its_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = threading.Event()
    started = threading.Event()

    def blocking(call: Any) -> ProviderReply:
        started.set()
        release.wait(10)
        return ProviderReply(good_reply())

    sdk = AgentReliability(sink=HealthSink())  # type: ignore[arg-type]
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", sync_judge(blocking))],
        runner=quiet_runner(),
        max_concurrency=1,
        max_pending=5,
        drain_timeout_seconds=5,
    )

    class Interrupt(BaseException):
        pass

    class BoomEvent:
        def wait(self, timeout: float | None = None) -> bool:
            raise Interrupt

        def set(self) -> None:
            return None

    original = coordinator_module._Waiter

    class BoomWaiter(original):  # type: ignore[valid-type, misc]
        def __init__(self, loop: Any) -> None:
            super().__init__(loop)
            self.event = BoomEvent()  # type: ignore[assignment]

    def holder() -> None:
        with (
            sdk.run(agent_id="a", name="A", version="1") as run,
            coordinator.scope(run) as scope,
        ):
            scope.evaluate_sync("groundedness", grounded_request())

    holder_thread = threading.Thread(target=holder, daemon=True)
    holder_thread.start()
    assert started.wait(5)
    monkeypatch.setattr(coordinator_module, "_Waiter", BoomWaiter)
    try:
        with (
            sdk.run(agent_id="a", name="A", version="1") as run,
            coordinator.scope(run) as scope,
            pytest.raises(Interrupt),
        ):
            scope.evaluate_sync("groundedness", grounded_request())
    finally:
        monkeypatch.setattr(coordinator_module, "_Waiter", original)
        release.set()
        holder_thread.join(5)
    admission = coordinator._admission
    assert not admission._waiters  # the dead waiter is gone
    assert admission._running == 0  # and no slot is stuck


# ----------------------------------------------------------------------- F-12


def test_f12_removing_the_provider_timeout_fails_instead_of_hanging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The virtual-time guard turns an unbounded wait into an assertion failure."""

    async def hang_forever() -> Any:
        await asyncio.Event().wait()

    with pytest.raises(AssertionError, match="unbounded wait"):
        run_virtual(hang_forever, guard=30.0)
    provider = FakeProvider([HANG, HANG])
    judge = LLMJudge(
        rubric=GR,
        provider=provider,
        model_label="rem",
        limits=JudgeLimits(provider_timeout_seconds=5, evaluation_deadline_seconds=60),
        jitter=lambda: 0.0,
    )

    async def go() -> Any:
        return await EvaluatorRunner(diagnostic_handler=Quiet()).evaluate_async(  # type: ignore[arg-type]
            judge, grounded_request()
        )

    result, elapsed = run_virtual(go, guard=120.0)
    assert result.exception_type == "JudgeTimeoutError" and elapsed < 30
    assert JudgeTimeoutError and JudgeProviderUnavailableError


# ------------------------------------------------------------------ F-13 items


def test_f13_invalid_jitter_is_a_clear_value_error() -> None:
    for bad in (-0.1, 1.5, float("nan"), "x", True):
        judge = LLMJudge(
            rubric=GR,
            provider=FakeProvider([JudgeProviderUnavailableError()] * 2),
            model_label="rem",
            jitter=lambda bad=bad: bad,  # type: ignore[misc]
        )
        with pytest.raises(ValueError, match="jitter must return a number in"):
            asyncio.run(judge.evaluate(grounded_request()))


def test_f13_capability_cache_holds_no_strong_reference_to_handle_classes() -> None:
    class Dynamic:
        def record_evaluation_failure(self, *, failure: Any) -> None: ...

    assert coordinator_module._supports_indicator(Dynamic()) is False
    assert Dynamic in coordinator_module._CAPABILITY_CACHE
    del Dynamic
    gc.collect()
    assert (
        len(
            [k for k in coordinator_module._CAPABILITY_CACHE if k.__name__ == "Dynamic"]
        )
        == 0
    )

"""Every test here proves one instance of the core M2/M2.1 safety
property: a broken instrumentation dependency must never break, or
replace the exception of, the application code being instrumented, and
must never silently prevent that code from running at all. See
docs/adr/0004-instrumentation-failure-isolation.md and
docs/adr/0005-instrumentation-initialization-degraded-mode.md.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from agent_reliability.adapters import UuidRunIdGenerator
from agent_reliability.domain import EvaluationOutcome
from agent_reliability.sdk import (
    AgentReliability,
    LoggingDiagnosticHandler,
    SdkDiagnostic,
    current_run,
)
from tests.fakes.clock import BrokenClock, FakeClock
from tests.fakes.diagnostics import BrokenDiagnosticHandler, CollectingDiagnosticHandler
from tests.fakes.id_generator import BrokenRunIdGenerator, SequentialRunIdGenerator
from tests.fakes.sinks import BrokenNTimesSink, BrokenSink, RecordingSink


class TestBrokenSinkDuringNormalOperation:
    def test_broken_sink_does_not_prevent_run_body_from_executing(self) -> None:
        sdk = AgentReliability(
            sink=BrokenSink(),
            clock=FakeClock(),
            run_id_generator=SequentialRunIdGenerator(),
        )
        body_ran = False
        with sdk.run(agent_id="a", name="A", version="1"):
            body_ran = True
        assert body_ran is True

    def test_broken_sink_does_not_prevent_record_from_completing(self) -> None:
        sdk = AgentReliability(
            sink=BrokenSink(),
            clock=FakeClock(),
            run_id_generator=SequentialRunIdGenerator(),
        )
        with sdk.run(agent_id="a", name="A", version="1") as run:
            run.record(
                indicator="task_success", outcome=EvaluationOutcome.PASS
            )  # must not raise

    def test_broken_sink_is_reported_via_diagnostics(self) -> None:
        diagnostics = CollectingDiagnosticHandler()
        sdk = AgentReliability(
            sink=BrokenSink(),
            clock=FakeClock(),
            run_id_generator=SequentialRunIdGenerator(),
            diagnostic_handler=diagnostics,
        )
        with sdk.run(agent_id="a", name="A", version="1"):
            pass

        assert len(diagnostics.diagnostics) == 2  # RunStarted emit + RunCompleted emit
        assert all(d.component == "sink" for d in diagnostics.diagnostics)
        assert all(d.operation == "emit" for d in diagnostics.diagnostics)
        assert all(
            isinstance(d.exception, RuntimeError) for d in diagnostics.diagnostics
        )

    def test_broken_sink_does_not_prevent_the_users_own_exception_from_propagating(
        self,
    ) -> None:
        sdk = AgentReliability(
            sink=BrokenSink(),
            clock=FakeClock(),
            run_id_generator=SequentialRunIdGenerator(),
        )
        original = ValueError("boom")
        with (
            pytest.raises(ValueError) as excinfo,
            sdk.run(agent_id="a", name="A", version="1"),
        ):
            raise original
        assert excinfo.value is original

    def test_transient_sink_failure_does_not_corrupt_later_delivery(self) -> None:
        sink = BrokenNTimesSink(n=1)  # RunStarted fails, RunCompleted succeeds
        sdk = AgentReliability(
            sink=sink, clock=FakeClock(), run_id_generator=SequentialRunIdGenerator()
        )
        with sdk.run(agent_id="a", name="A", version="1"):
            pass
        assert len(sink.events) == 1
        assert type(sink.events[0]).__name__ == "RunCompleted"


class TestBrokenClockDuringNormalOperation:
    def test_broken_clock_at_enter_degrades_and_body_runs(self) -> None:
        diagnostics = CollectingDiagnosticHandler()
        sink = RecordingSink()
        sdk = AgentReliability(
            sink=sink,
            clock=BrokenClock(),
            run_id_generator=SequentialRunIdGenerator(),
            diagnostic_handler=diagnostics,
        )
        body_ran = False
        with sdk.run(agent_id="a", name="A", version="1") as run:
            body_ran = True
            assert run.run_id is None
            assert run.parent_run_id is None
            run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)
        assert body_ran is True
        assert sink.events == []
        assert len(diagnostics.diagnostics) == 1
        assert diagnostics.diagnostics[0].component == "clock"
        assert diagnostics.diagnostics[0].operation == "now"

    def test_degraded_run_diagnoses_once_not_once_per_record_call(self) -> None:
        """The single diagnostic delivered at ``__enter__`` explains the
        degradation; repeated no-op ``record()`` calls on the same
        degraded run do not each re-diagnose it — that would be noise,
        not new information. See ADR-0005."""
        diagnostics = CollectingDiagnosticHandler()
        sdk = AgentReliability(
            sink=RecordingSink(),
            clock=BrokenClock(),
            run_id_generator=SequentialRunIdGenerator(),
            diagnostic_handler=diagnostics,
        )
        with sdk.run(agent_id="a", name="A", version="1") as run:
            for _ in range(5):
                run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)
        assert len(diagnostics.diagnostics) == 1
        assert diagnostics.diagnostics[0].component == "clock"

    def test_broken_clock_at_record_does_not_raise_and_skips_the_event(self) -> None:
        class ClockThatBreaksAfterFirstCall:
            def __init__(self) -> None:
                self._delegate = FakeClock()
                self._calls = 0

            def now(self):  # type: ignore[no-untyped-def]
                self._calls += 1
                if self._calls > 1:  # first call (RunStarted) succeeds
                    raise RuntimeError("clock broke mid-run")
                return self._delegate.now()

        diagnostics = CollectingDiagnosticHandler()
        sink = RecordingSink()
        sdk = AgentReliability(
            sink=sink,
            clock=ClockThatBreaksAfterFirstCall(),
            run_id_generator=SequentialRunIdGenerator(),
            diagnostic_handler=diagnostics,
        )
        with sdk.run(agent_id="a", name="A", version="1") as run:
            run.record(
                indicator="task_success", outcome=EvaluationOutcome.PASS
            )  # must not raise

        # RunStarted delivered; EvaluationRecorded and RunCompleted both
        # skipped because the clock kept failing, but nothing raised.
        assert [type(e).__name__ for e in sink.events] == ["RunStarted"]
        assert len(diagnostics.diagnostics) >= 1
        assert all(d.component == "clock" for d in diagnostics.diagnostics)

    def test_broken_clock_at_exit_does_not_replace_the_users_exception(self) -> None:
        class ClockThatBreaksOnSecondCall:
            def __init__(self) -> None:
                self._delegate = FakeClock()
                self._calls = 0

            def now(self):  # type: ignore[no-untyped-def]
                self._calls += 1
                if self._calls > 1:
                    raise RuntimeError("clock broke at exit")
                return self._delegate.now()

        sdk = AgentReliability(
            sink=RecordingSink(),
            clock=ClockThatBreaksOnSecondCall(),
            run_id_generator=SequentialRunIdGenerator(),
        )
        original = ValueError("boom")
        with (
            pytest.raises(ValueError) as excinfo,
            sdk.run(agent_id="a", name="A", version="1"),
        ):
            raise original
        assert excinfo.value is original


class TestBrokenRunIdGenerator:
    def test_broken_id_generator_at_enter_degrades_and_body_runs(self) -> None:
        diagnostics = CollectingDiagnosticHandler()
        sink = RecordingSink()
        sdk = AgentReliability(
            sink=sink,
            clock=FakeClock(),
            run_id_generator=BrokenRunIdGenerator(),
            diagnostic_handler=diagnostics,
        )
        body_ran = False
        with sdk.run(agent_id="a", name="A", version="1") as run:
            body_ran = True
            assert run.run_id is None
            run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)
        assert body_ran is True
        assert sink.events == []
        assert len(diagnostics.diagnostics) == 1
        assert diagnostics.diagnostics[0].component == "run_id_generator"
        assert diagnostics.diagnostics[0].operation == "generate"

    def test_invalid_generated_id_degrades_without_fake_telemetry(self) -> None:
        class InvalidRunIdGenerator:
            def generate(self) -> str:
                return ""

        diagnostics = CollectingDiagnosticHandler()
        sink = RecordingSink()
        sdk = AgentReliability(
            sink=sink,
            clock=FakeClock(),
            run_id_generator=InvalidRunIdGenerator(),
            diagnostic_handler=diagnostics,
        )
        with sdk.run(agent_id="a", name="A", version="1") as run:
            assert run.run_id is None
            run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)
        assert sink.events == []
        assert len(diagnostics.diagnostics) == 1
        assert diagnostics.diagnostics[0].component == "sdk"
        assert diagnostics.diagnostics[0].operation == "start"


def test_internal_context_setup_failure_degrades_without_emitting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent_reliability.sdk.client as client_module

    class BrokenContext:
        def set(self, value: object) -> None:
            raise RuntimeError("context setup failed")

    diagnostics = CollectingDiagnosticHandler()
    sink = RecordingSink()
    sdk = AgentReliability(
        sink=sink,
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator(),
        diagnostic_handler=diagnostics,
    )
    monkeypatch.setattr(client_module, "_current_run", BrokenContext())
    with sdk.run(agent_id="a", name="A", version="1") as run:
        assert run.run_id is None
        run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)
    assert sink.events == []
    assert len(diagnostics.diagnostics) == 1
    assert diagnostics.diagnostics[0].component == "sdk"
    assert diagnostics.diagnostics[0].operation == "start"


@pytest.mark.parametrize("dependency", ["clock", "run_id_generator"])
def test_degraded_run_preserves_exact_application_exception(dependency: str) -> None:
    kwargs = (
        {"clock": BrokenClock(), "run_id_generator": SequentialRunIdGenerator()}
        if dependency == "clock"
        else {"clock": FakeClock(), "run_id_generator": BrokenRunIdGenerator()}
    )
    sdk = AgentReliability(sink=RecordingSink(), **kwargs)  # type: ignore[arg-type]
    original = ValueError("application failure identity must survive")
    with (
        pytest.raises(ValueError) as excinfo,
        sdk.run(agent_id="a", name="A", version="1"),
    ):
        raise original
    assert excinfo.value is original
    assert type(excinfo.value) is ValueError
    assert str(excinfo.value) == "application failure identity must survive"


class TestDegradedContext:
    def test_degraded_handle_preserves_programmer_error_and_closed_semantics(
        self,
    ) -> None:
        sdk = AgentReliability(
            sink=RecordingSink(),
            clock=BrokenClock(),
            run_id_generator=SequentialRunIdGenerator(),
        )
        with sdk.run(agent_id="a", name="A", version="1") as run:
            with pytest.raises(ValueError, match="indicator"):
                run.record(indicator="", outcome=EvaluationOutcome.PASS)
            with pytest.raises(TypeError, match="EvaluationOutcome"):
                run.record(indicator="valid", outcome="pass")  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="closed"):
            run.record(indicator="valid", outcome=EvaluationOutcome.PASS)

    def test_sync_child_degradation_does_not_replace_parent_context(self) -> None:
        parent_sdk = AgentReliability(
            sink=RecordingSink(),
            clock=FakeClock(),
            run_id_generator=SequentialRunIdGenerator(),
        )
        child_sdk = AgentReliability(
            sink=RecordingSink(),
            clock=BrokenClock(),
            run_id_generator=SequentialRunIdGenerator(),
        )
        with parent_sdk.run(agent_id="p", name="Parent", version="1") as parent:
            with child_sdk.run(agent_id="c", name="Child", version="1") as child:
                assert child.run_id is None
                assert child.parent_run_id is None
                assert current_run() is parent
            assert current_run() is parent
        assert current_run() is None

    async def test_async_child_degradation_does_not_replace_parent_context(
        self,
    ) -> None:
        parent_sdk = AgentReliability(
            sink=RecordingSink(),
            clock=FakeClock(),
            run_id_generator=SequentialRunIdGenerator(),
        )
        child_sdk = AgentReliability(
            sink=RecordingSink(),
            clock=FakeClock(),
            run_id_generator=BrokenRunIdGenerator(),
        )
        async with parent_sdk.run(agent_id="p", name="Parent", version="1") as parent:
            async with child_sdk.run(agent_id="c", name="Child", version="1") as child:
                await asyncio.sleep(0)
                assert child.run_id is None
                assert current_run() is parent
            assert current_run() is parent
        assert current_run() is None

    def test_sync_run_started_inside_degraded_block_skips_it_in_parent_chain(
        self,
    ) -> None:
        """A degraded run is never installed as ``current_run()`` (it has
        no run id to be a parent of), so a normal run started inside its
        body parents to the nearest *real* run instead — the degraded run
        is transparent in the parent chain. See ADR-0005."""
        outer_sdk = AgentReliability(
            sink=RecordingSink(),
            clock=FakeClock(),
            run_id_generator=UuidRunIdGenerator(),
        )
        degraded_sdk = AgentReliability(
            sink=RecordingSink(),
            clock=BrokenClock(),
            run_id_generator=UuidRunIdGenerator(),
        )
        inner_sdk = AgentReliability(
            sink=RecordingSink(),
            clock=FakeClock(),
            run_id_generator=UuidRunIdGenerator(),
        )
        with outer_sdk.run(agent_id="outer", name="O", version="1") as outer:
            with degraded_sdk.run(
                agent_id="degraded", name="D", version="1"
            ) as degraded:
                assert degraded.run_id is None
                assert current_run() is outer
                with inner_sdk.run(agent_id="inner", name="I", version="1") as inner:
                    assert inner.parent_run_id == outer.run_id
            assert current_run() is outer
        assert current_run() is None

    async def test_async_run_started_inside_degraded_block_skips_it_in_parent_chain(
        self,
    ) -> None:
        outer_sdk = AgentReliability(
            sink=RecordingSink(),
            clock=FakeClock(),
            run_id_generator=UuidRunIdGenerator(),
        )
        degraded_sdk = AgentReliability(
            sink=RecordingSink(),
            clock=FakeClock(),
            run_id_generator=BrokenRunIdGenerator(),
        )
        inner_sdk = AgentReliability(
            sink=RecordingSink(),
            clock=FakeClock(),
            run_id_generator=UuidRunIdGenerator(),
        )
        async with outer_sdk.run(agent_id="outer", name="O", version="1") as outer:
            async with degraded_sdk.run(
                agent_id="degraded", name="D", version="1"
            ) as degraded:
                assert degraded.run_id is None
                assert current_run() is outer
                async with inner_sdk.run(
                    agent_id="inner", name="I", version="1"
                ) as inner:
                    await asyncio.sleep(0)
                    assert inner.parent_run_id == outer.run_id
            assert current_run() is outer
        assert current_run() is None

    @pytest.mark.parametrize("dependency", ["clock", "run_id_generator"])
    async def test_async_degraded_body_and_record_are_safe(
        self, dependency: str
    ) -> None:
        sink = RecordingSink()
        kwargs = (
            {"clock": BrokenClock(), "run_id_generator": SequentialRunIdGenerator()}
            if dependency == "clock"
            else {"clock": FakeClock(), "run_id_generator": BrokenRunIdGenerator()}
        )
        sdk = AgentReliability(sink=sink, **kwargs)  # type: ignore[arg-type]
        async with sdk.run(agent_id="a", name="A", version="1") as run:
            await asyncio.sleep(0)
            run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)
        assert sink.events == []


class TestInitializationBaseExceptions:
    @pytest.mark.parametrize(
        "signal",
        [KeyboardInterrupt(), SystemExit(), GeneratorExit(), asyncio.CancelledError()],
    )
    def test_run_id_generator_base_exception_is_not_suppressed(
        self, signal: BaseException
    ) -> None:
        class SignallingGenerator:
            def generate(self) -> str:
                raise signal

        sdk = AgentReliability(
            sink=RecordingSink(),
            clock=FakeClock(),
            run_id_generator=SignallingGenerator(),
        )
        with (
            pytest.raises(type(signal)),
            sdk.run(agent_id="a", name="A", version="1"),
        ):
            pytest.fail("body must not run after a BaseException control signal")

    def test_sink_base_exception_propagates_without_leaking_context(self) -> None:
        class InterruptingSink:
            def emit(self, event: object) -> None:
                raise KeyboardInterrupt

        sdk = AgentReliability(
            sink=InterruptingSink(),
            clock=FakeClock(),
            run_id_generator=SequentialRunIdGenerator(),
        )
        with (
            pytest.raises(KeyboardInterrupt),
            sdk.run(agent_id="a", name="A", version="1"),
        ):
            pytest.fail("body must not run after a BaseException control signal")
        assert current_run() is None


class TestBrokenDiagnosticHandler:
    def test_broken_diagnostic_handler_during_initialization_does_not_propagate(
        self,
    ) -> None:
        sdk = AgentReliability(
            sink=RecordingSink(),
            clock=BrokenClock(),
            run_id_generator=SequentialRunIdGenerator(),
            diagnostic_handler=BrokenDiagnosticHandler(),
        )
        with sdk.run(agent_id="a", name="A", version="1") as run:
            run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)

    def test_broken_diagnostic_handler_does_not_propagate(self) -> None:
        sdk = AgentReliability(
            sink=BrokenSink(),
            clock=FakeClock(),
            run_id_generator=SequentialRunIdGenerator(),
            diagnostic_handler=BrokenDiagnosticHandler(),
        )
        # Neither the broken sink nor the broken diagnostic handler may raise.
        with sdk.run(agent_id="a", name="A", version="1") as run:
            run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)

    def test_broken_diagnostic_handler_does_not_replace_the_users_exception(
        self,
    ) -> None:
        sdk = AgentReliability(
            sink=BrokenSink(),
            clock=FakeClock(),
            run_id_generator=SequentialRunIdGenerator(),
            diagnostic_handler=BrokenDiagnosticHandler(),
        )
        original = ValueError("boom")
        with (
            pytest.raises(ValueError) as excinfo,
            sdk.run(agent_id="a", name="A", version="1"),
        ):
            raise original
        assert excinfo.value is original


class TestFinishBackstops:
    def test_handle_close_failure_does_not_replace_application_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        diagnostics = CollectingDiagnosticHandler()
        sdk = AgentReliability(
            sink=RecordingSink(),
            clock=FakeClock(),
            run_id_generator=SequentialRunIdGenerator(),
            diagnostic_handler=diagnostics,
        )
        original = ValueError("application exception")

        def broken_close(self: object) -> None:
            raise RuntimeError("close failed")

        with (
            pytest.raises(ValueError) as excinfo,
            sdk.run(agent_id="a", name="A", version="1") as run,
        ):
            monkeypatch.setattr(type(run), "_close", broken_close)
            raise original
        assert excinfo.value is original
        assert current_run() is None
        assert diagnostics.diagnostics[-1].component == "sdk"
        assert diagnostics.diagnostics[-1].operation == "finish"

    def test_context_reset_failure_is_diagnosed_and_suppressed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import agent_reliability.sdk.client as client_module
        import agent_reliability.sdk.context as context_module

        class BrokenResetContext:
            def reset(self, token: object) -> None:
                raise RuntimeError("reset failed")

        diagnostics = CollectingDiagnosticHandler()
        sdk = AgentReliability(
            sink=RecordingSink(),
            clock=FakeClock(),
            run_id_generator=SequentialRunIdGenerator(),
            diagnostic_handler=diagnostics,
        )
        session = sdk.run(agent_id="a", name="A", version="1")
        with session:
            saved_token = session._token
            monkeypatch.setattr(client_module, "_current_run", BrokenResetContext())

        assert saved_token is not None
        context_module._current_run.reset(saved_token)
        assert current_run() is None
        assert diagnostics.diagnostics[-1].component == "sdk"
        assert diagnostics.diagnostics[-1].operation == "finish"


class TestDefaultDiagnosticHandlerDoesNotCrash:
    def test_default_logging_handler_survives_a_broken_sink(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        sdk = AgentReliability(
            sink=BrokenSink(),
            clock=FakeClock(),
            run_id_generator=SequentialRunIdGenerator(),
        )
        with (
            caplog.at_level("WARNING", logger="agent_reliability.sdk"),
            sdk.run(agent_id="a", name="A", version="1"),
        ):
            pass
        assert any("instrumentation failure" in message for message in caplog.messages)

    def test_default_logging_handler_does_not_leak_exception_content(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        secret = "TEST_SECRET_DO_NOT_LOG_12345"
        try:
            raise ValueError(f"request failed with token {secret}")
        except ValueError as exc:
            exception_message = str(exc)
            exception_repr = repr(exc)
            diagnostic = SdkDiagnostic(
                component="sink", operation="emit", run_id="safe-run", exception=exc
            )
            with caplog.at_level(logging.WARNING, logger="agent_reliability.sdk"):
                LoggingDiagnosticHandler().handle(diagnostic)

        captured = caplog.text
        assert "ValueError" in captured
        assert "component=sink" in captured
        assert "operation=emit" in captured
        assert secret not in captured
        assert exception_message not in captured
        assert exception_repr not in captured
        assert "Traceback" not in captured


class TestDefensiveBackstopAroundTerminalEventConstruction:
    """``_emit_terminal_event`` wraps event construction itself (not just
    the sink/clock calls) in a defensive try/except — a last-resort
    guard against a hypothetical internal SDK bug, on top of the
    already-safe clock/sink paths. Proven here by forcing the event
    constructor itself to raise, which nothing else in the SDK guards
    against directly.
    """

    def test_a_broken_event_constructor_does_not_replace_the_users_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import agent_reliability.sdk.client as client_module

        def broken_run_completed(*args: object, **kwargs: object) -> None:
            raise RuntimeError("event construction is broken")

        monkeypatch.setattr(client_module, "RunCompleted", broken_run_completed)
        sdk = AgentReliability(
            sink=RecordingSink(),
            clock=FakeClock(),
            run_id_generator=SequentialRunIdGenerator(),
        )
        with sdk.run(agent_id="a", name="A", version="1"):
            pass  # must not raise despite RunCompleted(...) itself raising

    def test_a_broken_event_constructor_is_reported_via_diagnostics(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import agent_reliability.sdk.client as client_module

        def broken_run_completed(*args: object, **kwargs: object) -> None:
            raise RuntimeError("event construction is broken")

        monkeypatch.setattr(client_module, "RunCompleted", broken_run_completed)
        diagnostics = CollectingDiagnosticHandler()
        sdk = AgentReliability(
            sink=RecordingSink(),
            clock=FakeClock(),
            run_id_generator=SequentialRunIdGenerator(),
            diagnostic_handler=diagnostics,
        )
        with sdk.run(agent_id="a", name="A", version="1"):
            pass
        assert any(
            "event construction is broken" in str(d.exception)
            for d in diagnostics.diagnostics
        )

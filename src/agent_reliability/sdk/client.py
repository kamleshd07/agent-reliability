"""The SDK's public entry point: ``AgentReliability`` and the run
session it returns from ``.run(...)``.

See docs/SDK_DESIGN.md for the full design rationale and
docs/adr/0004-instrumentation-failure-isolation.md and
docs/adr/0005-instrumentation-initialization-degraded-mode.md for exactly
which failures raise, which are suppressed, and which degrade the run
instead — and why.
"""

from __future__ import annotations

import asyncio
import contextlib
from contextvars import Token
from datetime import datetime

from agent_reliability.adapters.event_sinks import NoOpEventSink
from agent_reliability.adapters.system_clock import SystemClock
from agent_reliability.adapters.uuid_run_id_generator import UuidRunIdGenerator
from agent_reliability.domain import (
    AgentIdentity,
    AgentRun,
    EvaluationOutcome,
    RunStatus,
)
from agent_reliability.domain.measurement_health import MeasurementHealthReason
from agent_reliability.evaluation import EvaluationResult
from agent_reliability.ports.clock import Clock
from agent_reliability.ports.event_sink import EventSink
from agent_reliability.ports.events import (
    EvaluationRecorded,
    InstrumentationEvent,
    RunCompleted,
    RunFailed,
    RunStarted,
)
from agent_reliability.ports.id_generator import RunIdGenerator
from agent_reliability.ports.run_context import RunContextBridge, RunContextScope
from agent_reliability.sdk.context import RunHandle, _current_run, current_run
from agent_reliability.sdk.diagnostics import (
    DiagnosticComponent,
    DiagnosticHandler,
    DiagnosticOperation,
    LoggingDiagnosticHandler,
    SdkDiagnostic,
)

__all__ = ["AgentReliability"]


class AgentReliability:
    """The SDK's configuration and entry point.

    Safe to construct once and share; safe to call ``.run(...)`` on
    concurrently from multiple threads or ``asyncio`` tasks, since this
    object holds no mutable per-run state (docs/SDK_DESIGN.md).

    All configuration is programmatic — no config files, no environment
    variable hierarchy (docs/ENGINEERING_PRINCIPLES.md #10). Every
    argument defaults to an in-process, side-effect-free implementation,
    so ``AgentReliability()`` with no arguments is a safe, silent default
    (see ``NoOpEventSink``).
    """

    def __init__(
        self,
        *,
        sink: EventSink | None = None,
        clock: Clock | None = None,
        run_id_generator: RunIdGenerator | None = None,
        diagnostic_handler: DiagnosticHandler | None = None,
        run_context_bridge: RunContextBridge | None = None,
    ) -> None:
        if sink is not None and not isinstance(sink, EventSink):
            raise TypeError("sink must implement EventSink")
        if clock is not None and not isinstance(clock, Clock):
            raise TypeError("clock must implement Clock")
        if run_id_generator is not None and not isinstance(
            run_id_generator, RunIdGenerator
        ):
            raise TypeError("run_id_generator must implement RunIdGenerator")
        if diagnostic_handler is not None and not isinstance(
            diagnostic_handler, DiagnosticHandler
        ):
            raise TypeError("diagnostic_handler must implement DiagnosticHandler")
        if run_context_bridge is not None and not isinstance(
            run_context_bridge, RunContextBridge
        ):
            raise TypeError("run_context_bridge must implement RunContextBridge")
        self._sink: EventSink = sink if sink is not None else NoOpEventSink()
        self._clock: Clock = clock if clock is not None else SystemClock()
        self._run_id_generator: RunIdGenerator = (
            run_id_generator if run_id_generator is not None else UuidRunIdGenerator()
        )
        self._diagnostic_handler: DiagnosticHandler = (
            diagnostic_handler
            if diagnostic_handler is not None
            else LoggingDiagnosticHandler()
        )
        self._run_context_bridge = run_context_bridge

    def run(
        self,
        *,
        agent_id: str,
        name: str,
        version: str,
        environment: str | None = None,
    ) -> RunSession:
        """Start (or, entered as a context manager, scope) one agent run.

        Constructs and validates ``AgentIdentity`` immediately — a
        malformed identity (e.g. an empty ``agent_id``) raises here,
        synchronously, exactly like any other function call that can
        fail (docs/adr/0004-instrumentation-failure-isolation.md). No
        application code is "in flight" yet at this point.

        By contrast, a failure in the run id generator, clock, or
        internal run construction once the returned session is entered
        does **not** raise — it degrades to a no-telemetry ``RunHandle``
        so the ``with``/``async with`` body still executes (see
        docs/adr/0005-instrumentation-initialization-degraded-mode.md).

        Use as ``with sdk.run(...) as run:`` or
        ``async with sdk.run(...) as run:``.
        """
        agent = AgentIdentity(
            agent_id=agent_id, name=name, version=version, environment=environment
        )
        return RunSession(client=self, agent=agent)

    def _report_diagnostic(
        self,
        *,
        component: DiagnosticComponent,
        operation: DiagnosticOperation,
        run_id: str | None,
        exception: Exception,
    ) -> None:
        """The one absolute last resort: if the diagnostic handler
        itself raises, that failure is dropped silently. See
        docs/adr/0004-instrumentation-failure-isolation.md."""
        with contextlib.suppress(Exception):
            self._diagnostic_handler.handle(
                SdkDiagnostic(
                    component=component,
                    operation=operation,
                    run_id=run_id,
                    exception=exception,
                )
            )

    def _safe_emit(
        self,
        event: InstrumentationEvent,
        *,
        run_id: str | None,
        handle: RunHandle | None = None,
    ) -> None:
        try:
            self._sink.emit(event)
        except Exception as exc:
            if handle is not None:
                handle._mark_measurement_health(
                    MeasurementHealthReason.EVENT_DELIVERY_FAILURE
                )
            self._report_diagnostic(
                component="sink", operation="emit", run_id=run_id, exception=exc
            )

    def _safe_now(
        self,
        *,
        component: DiagnosticComponent,
        run_id: str | None,
        handle: RunHandle | None = None,
    ) -> datetime | None:
        try:
            return self._clock.now()
        except Exception as exc:
            if handle is not None:
                handle._mark_measurement_health(
                    MeasurementHealthReason.EVIDENCE_TIMESTAMP_FAILURE
                )
            self._report_diagnostic(
                component=component, operation="now", run_id=run_id, exception=exc
            )
            return None

    def _safe_record(
        self, handle: RunHandle, indicator: str, outcome: EvaluationOutcome
    ) -> None:
        run_id = handle.run_id
        if run_id is None:
            return
        recorded_at = self._safe_now(component="clock", run_id=run_id, handle=handle)
        if recorded_at is None:
            return
        event = EvaluationRecorded(
            run_id=run_id,
            indicator=indicator,
            outcome=outcome,
            recorded_at=recorded_at,
        )
        self._safe_emit(event, run_id=run_id, handle=handle)

    def _safe_record_evaluation(
        self, handle: RunHandle, indicator: str, result: EvaluationResult
    ) -> None:
        run_id = handle.run_id
        if run_id is None:
            return
        recorded_at = self._safe_now(component="clock", run_id=run_id, handle=handle)
        if recorded_at is None:
            return
        event = EvaluationRecorded(
            run_id=run_id,
            indicator=indicator,
            outcome=result.outcome,
            recorded_at=recorded_at,
            provenance=result.provenance,
            reason_code=result.reason_code,
        )
        self._safe_emit(event, run_id=run_id, handle=handle)


class RunSession:
    """The context manager object returned by ``AgentReliability.run(...)``.

    Implements both the sync and async context manager protocols on one
    class, both delegating to the same synchronous internal logic — safe
    because M2 performs no real I/O anywhere in this path (see
    docs/adr/0003-python-sdk-runtime-and-context-architecture.md).
    """

    __slots__ = ("_agent", "_bridge_scope", "_client", "_handle", "_token")

    def __init__(self, client: AgentReliability, agent: AgentIdentity) -> None:
        self._client = client
        self._agent = agent
        self._handle: RunHandle | None = None
        self._token: Token[RunHandle | None] | None = None
        self._bridge_scope: RunContextScope | None = None

    # -- sync protocol --

    def __enter__(self) -> RunHandle:
        return self._start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        # Returning None (falsy) — never suppresses the caller's exception.
        self._finish(exc_type)

    # -- async protocol --
    # No actual asynchronous work happens here (see module docstring) —
    # these exist so the SDK is usable inside `async def` without
    # forcing executor gymnastics.

    async def __aenter__(self) -> RunHandle:
        return self._start()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        # Returning None (falsy) — never suppresses the caller's exception.
        self._finish(exc_type)

    # -- shared internal logic --

    def _start(self) -> RunHandle:
        # A failure anywhere below degrades to a no-telemetry RunHandle
        # instead of raising: __enter__/__aenter__ raising would prevent
        # Python from ever running the `with`/`async with` body, which is
        # the outcome this SDK exists to rule out. See
        # docs/adr/0005-instrumentation-initialization-degraded-mode.md.
        parent = current_run()
        parent_run_id = parent.run_id if parent is not None else None

        try:
            run_id = self._client._run_id_generator.generate()
        except Exception as exc:
            self._client._report_diagnostic(
                component="run_id_generator",
                operation="generate",
                run_id=None,
                exception=exc,
            )
            return self._start_degraded()

        try:
            started_at = self._client._clock.now()
        except Exception as exc:
            self._client._report_diagnostic(
                component="clock", operation="now", run_id=run_id, exception=exc
            )
            return self._start_degraded()

        try:
            run = AgentRun(
                run_id=run_id,
                agent=self._agent,
                started_at=started_at,
                status=RunStatus.STARTED,
                parent_run_id=parent_run_id,
            )
            handle = RunHandle(
                run=run,
                record_callback=self._client._safe_record,
                record_evaluation_callback=self._client._safe_record_evaluation,
            )
            started_event = RunStarted(
                run_id=run_id,
                parent_run_id=parent_run_id,
                agent=self._agent,
                started_at=started_at,
            )
        except Exception as exc:
            self._client._report_diagnostic(
                component="sdk", operation="start", run_id=run_id, exception=exc
            )
            return self._start_degraded()

        try:
            self._token = _current_run.set(handle)
        except Exception as exc:
            self._client._report_diagnostic(
                component="sdk", operation="start", run_id=run_id, exception=exc
            )
            return self._start_degraded()
        self._handle = handle
        try:
            self._start_bridge(run)
            self._client._safe_emit(started_event, run_id=run_id, handle=handle)
        except BaseException:
            # Preserve interpreter/runtime control signals while undoing
            # both contexts established immediately before sink delivery.
            try:
                self._finish_bridge(
                    handle, status=RunStatus.CANCELLED, exception_type=None
                )
            finally:
                try:
                    self._close_handle(handle)
                finally:
                    self._reset_context(handle)
            raise
        return handle

    def _start_degraded(self) -> RunHandle:
        handle = RunHandle._degraded(
            agent=self._agent,
            record_callback=self._client._safe_record,
            record_evaluation_callback=self._client._safe_record_evaluation,
        )
        self._handle = handle
        return handle

    def _finish(self, exc_type: type[BaseException] | None) -> None:
        assert self._handle is not None
        handle = self._handle
        if self._token is None:
            self._close_handle(handle)
            return
        try:
            self._emit_terminal_event(handle, exc_type)
        finally:
            status = self._terminal_status(exc_type)
            exception_type = exc_type.__name__ if exc_type is not None else None
            try:
                self._finish_bridge(
                    handle, status=status, exception_type=exception_type
                )
            finally:
                try:
                    self._close_handle(handle)
                finally:
                    self._reset_context(handle)

    def _start_bridge(self, run: AgentRun) -> None:
        bridge = self._client._run_context_bridge
        if bridge is None:
            return
        try:
            scope = bridge.start(run)
            if not isinstance(scope, RunContextScope):
                raise TypeError(
                    "RunContextBridge.start() must return a RunContextScope"
                )
            self._bridge_scope = scope
        except Exception as exc:
            self._client._report_diagnostic(
                component="run_context_bridge",
                operation="start",
                run_id=run.run_id,
                exception=exc,
            )

    def _finish_bridge(
        self,
        handle: RunHandle,
        *,
        status: RunStatus,
        exception_type: str | None,
    ) -> None:
        scope = self._bridge_scope
        if scope is None:
            return
        try:
            scope.finish(status=status, exception_type=exception_type)
        except Exception as exc:
            self._client._report_diagnostic(
                component="run_context_bridge",
                operation="finish",
                run_id=handle.run_id,
                exception=exc,
            )
        finally:
            self._bridge_scope = None

    @staticmethod
    def _terminal_status(exc_type: type[BaseException] | None) -> RunStatus:
        if exc_type is None:
            return RunStatus.COMPLETED
        if issubclass(exc_type, asyncio.CancelledError):
            return RunStatus.CANCELLED
        return RunStatus.FAILED

    def _close_handle(self, handle: RunHandle) -> None:
        try:
            handle._close()
        except Exception as exc:
            self._client._report_diagnostic(
                component="sdk",
                operation="finish",
                run_id=handle.run_id,
                exception=exc,
            )

    def _reset_context(self, handle: RunHandle) -> None:
        token = self._token
        assert token is not None
        try:
            _current_run.reset(token)
        except Exception as exc:
            self._client._report_diagnostic(
                component="sdk",
                operation="finish",
                run_id=handle.run_id,
                exception=exc,
            )
        finally:
            self._token = None

    def _emit_terminal_event(
        self, handle: RunHandle, exc_type: type[BaseException] | None
    ) -> None:
        # Wrapped defensively as a whole: __exit__/__aexit__ must never
        # raise due to an instrumentation failure, full stop (see
        # docs/adr/0004-instrumentation-failure-isolation.md). Only
        # Exception is caught here — KeyboardInterrupt/SystemExit/
        # asyncio.CancelledError are never suppressed by this SDK.
        try:
            run_id = handle.run_id
            assert run_id is not None
            ended_at = self._client._safe_now(
                component="clock", run_id=run_id, handle=handle
            )
            if ended_at is None:
                return
            event: InstrumentationEvent
            if exc_type is None:
                event = RunCompleted(run_id=run_id, ended_at=ended_at)
            else:
                status = self._terminal_status(exc_type)
                event = RunFailed(
                    run_id=run_id,
                    ended_at=ended_at,
                    status=status,
                    exception_type=exc_type.__name__,
                )
            self._client._safe_emit(event, run_id=run_id, handle=handle)
        except Exception as exc:
            self._client._report_diagnostic(
                component="sdk",
                operation="finish",
                run_id=handle.run_id,
                exception=exc,
            )

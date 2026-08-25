"""OpenTelemetry implementation of the run-context bridge port."""

from __future__ import annotations

from contextlib import AbstractContextManager, suppress

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer

from agent_reliability import __version__
from agent_reliability.domain import AgentRun, RunStatus
from agent_reliability.ports.run_context import RunContextScope

__all__ = ["OpenTelemetryRunContextBridge"]

_INSTRUMENTATION_SCOPE_NAME = "agent_reliability"
_SPAN_NAME = "invoke_agent"
_SCHEMA_VERSION = "1"


class OpenTelemetryRunContextBridge:
    """Creates a current internal span for each initialized SDK run.

    Passing a tracer is useful for explicit provider ownership and tests. If
    omitted, the bridge obtains a tracer from the host-configured global
    provider; it never installs or changes that provider.
    """

    def __init__(self, tracer: Tracer | None = None) -> None:
        if tracer is not None and not isinstance(tracer, Tracer):
            raise TypeError("tracer must implement opentelemetry.trace.Tracer")
        self._tracer = (
            tracer
            if tracer is not None
            else trace.get_tracer(_INSTRUMENTATION_SCOPE_NAME, __version__)
        )

    def start(self, run: AgentRun) -> RunContextScope:
        attributes: dict[str, str] = {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.agent.name": run.agent.name,
            "agent_reliability.schema.version": _SCHEMA_VERSION,
            "agent_reliability.agent.id": run.agent.agent_id,
            "agent_reliability.agent.version": run.agent.version,
            "agent_reliability.run.id": run.run_id,
        }
        if run.agent.environment is not None:
            attributes["agent_reliability.agent.environment"] = run.agent.environment
        if run.parent_run_id is not None:
            attributes["agent_reliability.run.parent_id"] = run.parent_run_id

        span = self._tracer.start_span(
            _SPAN_NAME, kind=SpanKind.INTERNAL, attributes=attributes
        )
        activation = trace.use_span(
            span,
            end_on_exit=False,
            record_exception=False,
            set_status_on_exception=False,
        )
        try:
            activation.__enter__()
        except BaseException:
            # Preserve the activation failure. There is no active scope for
            # the SDK to finish, and the host runtime owns any additional
            # OpenTelemetry diagnostics.
            with suppress(BaseException):
                span.end()
            raise
        return _OpenTelemetryRunContextScope(span=span, activation=activation)


class _OpenTelemetryRunContextScope:
    def __init__(self, *, span: Span, activation: AbstractContextManager[Span]) -> None:
        self._span = span
        self._activation = activation
        self._closed = False

    def finish(self, *, status: RunStatus, exception_type: str | None) -> None:
        if self._closed:
            return

        first_error: BaseException | None = None
        try:
            try:
                self._span.set_attribute("agent_reliability.run.status", status.value)
                if status is RunStatus.FAILED:
                    if exception_type is not None:
                        self._span.set_attribute("error.type", exception_type)
                    self._span.set_status(Status(StatusCode.ERROR))
            except BaseException as exc:
                first_error = exc

            try:
                self._activation.__exit__(None, None, None)
            except BaseException as exc:
                if first_error is None:
                    first_error = exc

            try:
                self._span.end()
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        finally:
            self._closed = True

        if first_error is not None:
            raise first_error

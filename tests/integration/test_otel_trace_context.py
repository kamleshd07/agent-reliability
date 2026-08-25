from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

pytest.importorskip("opentelemetry", reason="requires the 'otel-test' extra")

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import Span, StatusCode, Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

import agent_reliability
from agent_reliability.adapters.otel import OpenTelemetryRunContextBridge
from agent_reliability.domain import AgentIdentity, AgentRun, RunStatus
from agent_reliability.sdk import AgentReliability
from tests.fakes.clock import BrokenClock, FakeClock
from tests.fakes.diagnostics import CollectingDiagnosticHandler
from tests.fakes.id_generator import SequentialRunIdGenerator
from tests.fakes.sinks import RecordingSink


def _agent_run(run_id: str = "manual-run-1") -> AgentRun:
    return AgentRun(
        run_id=run_id,
        agent=AgentIdentity(agent_id="manual-agent", name="Manual", version="1"),
        started_at=datetime.now(UTC),
        status=RunStatus.STARTED,
    )


@dataclass
class OtelHarness:
    tracer: Tracer
    exporter: InMemorySpanExporter


@pytest.fixture
def otel() -> Iterator[OtelHarness]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield OtelHarness(
        tracer=provider.get_tracer("agent-reliability-tests"), exporter=exporter
    )
    provider.shutdown()


def _sdk(otel: OtelHarness, **kwargs: object) -> AgentReliability:
    return AgentReliability(
        run_context_bridge=OpenTelemetryRunContextBridge(otel.tracer),
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator(),
        **kwargs,  # type: ignore[arg-type]
    )


def _by_run_id(otel: OtelHarness) -> dict[str, object]:
    return {
        span.attributes["agent_reliability.run.id"]: span
        for span in otel.exporter.get_finished_spans()
        if "agent_reliability.run.id" in span.attributes
    }


@pytest.mark.integration
def test_standalone_run_creates_one_ended_internal_span(otel: OtelHarness) -> None:
    sdk = _sdk(otel)

    with sdk.run(
        agent_id="research-agent",
        name="Research Agent",
        version="1.0",
        environment="test",
    ):
        current = trace.get_current_span()
        assert current.get_span_context().is_valid

    spans = otel.exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "invoke_agent"
    assert span.kind is trace.SpanKind.INTERNAL
    assert span.parent is None
    assert span.attributes == {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": "Research Agent",
        "agent_reliability.schema.version": "1",
        "agent_reliability.agent.id": "research-agent",
        "agent_reliability.agent.version": "1.0",
        "agent_reliability.agent.environment": "test",
        "agent_reliability.run.id": "run-1",
        "agent_reliability.run.status": "completed",
    }
    assert span.status.status_code is StatusCode.UNSET
    assert span.events == ()


@pytest.mark.integration
def test_scope_finish_is_idempotent(otel: OtelHarness) -> None:
    """``RunContextScope.finish()`` is a public contract method — a
    caller invoking it twice (directly, bypassing the SDK, which never
    does this itself) must not double-end the span or raise."""
    bridge = OpenTelemetryRunContextBridge(otel.tracer)
    scope = bridge.start(_agent_run())

    scope.finish(status=RunStatus.COMPLETED, exception_type=None)
    scope.finish(status=RunStatus.COMPLETED, exception_type=None)  # must be a no-op

    spans = otel.exporter.get_finished_spans()
    assert len(spans) == 1


@pytest.mark.integration
def test_failed_status_without_exception_type_omits_error_type_attribute(
    otel: OtelHarness,
) -> None:
    """``exception_type`` is optional on the port even though the SDK
    always supplies one for a ``FAILED`` status; a direct caller passing
    ``None`` must not get a fabricated ``error.type`` attribute."""
    bridge = OpenTelemetryRunContextBridge(otel.tracer)
    scope = bridge.start(_agent_run())

    scope.finish(status=RunStatus.FAILED, exception_type=None)

    span = otel.exporter.get_finished_spans()[0]
    assert span.status.status_code is StatusCode.ERROR
    assert "error.type" not in span.attributes
    assert span.attributes["agent_reliability.run.status"] == "failed"


@pytest.mark.integration
def test_existing_parent_and_regular_child_have_exact_parentage(
    otel: OtelHarness,
) -> None:
    sdk = _sdk(otel)

    with otel.tracer.start_as_current_span("existing-server") as parent:
        parent_context = trace.get_current_span().get_span_context()
        with (
            sdk.run(agent_id="agent", name="Agent", version="1"),
            otel.tracer.start_as_current_span("database") as child,
        ):
            assert child.parent is not None
        assert trace.get_current_span() is parent
        assert trace.get_current_span().get_span_context() == parent_context

    spans = {span.name: span for span in otel.exporter.get_finished_spans()}
    agent = spans["invoke_agent"]
    assert agent.parent is not None
    assert agent.parent.span_id == spans["existing-server"].context.span_id
    assert spans["database"].parent is not None
    assert spans["database"].parent.span_id == agent.context.span_id


@pytest.mark.integration
def test_host_w3c_propagator_sees_agent_span_as_current(otel: OtelHarness) -> None:
    sdk = _sdk(otel)
    carrier: dict[str, str] = {}

    with sdk.run(agent_id="agent", name="Agent", version="1"):
        agent_context = trace.get_current_span().get_span_context()
        TraceContextTextMapPropagator().inject(carrier)

    extracted = TraceContextTextMapPropagator().extract(carrier)
    propagated = trace.get_current_span(extracted).get_span_context()
    assert carrier.keys() == {"traceparent"}
    assert propagated.trace_id == agent_context.trace_id
    assert propagated.span_id == agent_context.span_id


@pytest.mark.integration
def test_nested_agents_follow_otel_context_without_fabricated_ids(
    otel: OtelHarness,
) -> None:
    sdk = _sdk(otel)

    with (
        sdk.run(agent_id="outer", name="Outer", version="1"),
        sdk.run(agent_id="inner", name="Inner", version="1"),
    ):
        pass

    by_run = _by_run_id(otel)
    outer = by_run["run-1"]
    inner = by_run["run-2"]
    assert outer.parent is None
    assert inner.parent is not None
    assert inner.parent.span_id == outer.context.span_id
    assert inner.context.trace_id == outer.context.trace_id
    assert inner.attributes["agent_reliability.run.parent_id"] == "run-1"
    assert inner.attributes["agent_reliability.run.id"] != format(
        inner.context.span_id, "016x"
    )


@pytest.mark.integration
def test_agent_inside_standard_span_inside_agent(otel: OtelHarness) -> None:
    first = _sdk(otel)
    second = AgentReliability(
        run_context_bridge=OpenTelemetryRunContextBridge(otel.tracer),
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator(prefix="second"),
    )

    with (
        first.run(agent_id="outer", name="Outer", version="1"),
        otel.tracer.start_as_current_span("ordinary"),
        second.run(agent_id="inner", name="Inner", version="1"),
    ):
        pass

    spans = {span.name: span for span in otel.exporter.get_finished_spans()}
    by_run = _by_run_id(otel)
    outer = by_run["run-1"]
    inner = by_run["second-1"]
    ordinary = spans["ordinary"]
    assert ordinary.parent is not None
    assert ordinary.parent.span_id == outer.context.span_id
    assert inner.parent is not None
    assert inner.parent.span_id == ordinary.context.span_id
    # Agent Reliability context is process-local, not scoped per SDK instance.
    assert inner.attributes["agent_reliability.run.parent_id"] == "run-1"


@pytest.mark.integration
def test_exception_is_safe_and_original_object_is_preserved(otel: OtelHarness) -> None:
    sdk = _sdk(otel)
    original = ValueError("secret@example.com credential=do-not-export")

    with (
        pytest.raises(ValueError) as exc_info,
        sdk.run(agent_id="agent", name="Agent", version="1"),
    ):
        raise original

    assert exc_info.value is original
    span = otel.exporter.get_finished_spans()[0]
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description is None
    assert span.attributes["agent_reliability.run.status"] == "failed"
    assert span.attributes["error.type"] == "ValueError"
    assert span.events == ()
    exported = repr(span.attributes) + repr(span.events) + repr(span.status)
    assert "secret@example.com" not in exported
    assert "do-not-export" not in exported


@pytest.mark.integration
async def test_async_tasks_have_no_trace_context_crossover(otel: OtelHarness) -> None:
    sdk = _sdk(otel)
    entered = 0
    both_entered = asyncio.Event()

    async def worker(agent_id: str) -> None:
        nonlocal entered
        async with sdk.run(agent_id=agent_id, name=agent_id, version="1"):
            entered += 1
            if entered == 2:
                both_entered.set()
            await both_entered.wait()
            with otel.tracer.start_as_current_span(f"child-{agent_id}"):
                await asyncio.sleep(0)

    await asyncio.gather(worker("a"), worker("b"))

    spans = otel.exporter.get_finished_spans()
    agents = {
        span.attributes["gen_ai.agent.name"]: span
        for span in spans
        if span.name == "invoke_agent"
    }
    children = {span.name: span for span in spans if span.name.startswith("child-")}
    for agent_id in ("a", "b"):
        child = children[f"child-{agent_id}"]
        assert child.parent is not None
        assert child.parent.span_id == agents[agent_id].context.span_id
    assert agents["a"].context.trace_id != agents["b"].context.trace_id


@pytest.mark.integration
def test_degraded_run_creates_no_span(otel: OtelHarness) -> None:
    sdk = AgentReliability(
        run_context_bridge=OpenTelemetryRunContextBridge(otel.tracer),
        clock=BrokenClock(),
        run_id_generator=SequentialRunIdGenerator(),
    )

    with sdk.run(agent_id="agent", name="Agent", version="1") as run:
        assert run.run_id is None

    assert otel.exporter.get_finished_spans() == ()


@pytest.mark.integration
def test_cancelled_run_ends_span_without_swallowing_cancellation(
    otel: OtelHarness,
) -> None:
    sdk = _sdk(otel)

    with (
        pytest.raises(asyncio.CancelledError),
        sdk.run(agent_id="agent", name="Agent", version="1"),
    ):
        raise asyncio.CancelledError

    span = otel.exporter.get_finished_spans()[0]
    assert span.attributes["agent_reliability.run.status"] == "cancelled"
    assert "error.type" not in span.attributes
    assert span.status.status_code is StatusCode.UNSET


class _BrokenActivation(AbstractContextManager[Span]):
    def __init__(self, *, enter_error: Exception | None = None) -> None:
        self.enter_error = enter_error
        self.exit_error: Exception | None = None

    def __enter__(self) -> Span:
        if self.enter_error is not None:
            raise self.enter_error
        return Mock(spec=Span)

    def __exit__(self, *args: object) -> None:
        if self.exit_error is not None:
            raise self.exit_error


@pytest.mark.integration
def test_span_creation_failure_is_isolated() -> None:
    tracer = Mock(spec=Tracer)
    tracer.start_span.side_effect = RuntimeError("creation broke")
    diagnostics = CollectingDiagnosticHandler()
    sink = RecordingSink()
    sdk = AgentReliability(
        run_context_bridge=OpenTelemetryRunContextBridge(tracer),
        sink=sink,
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator(),
        diagnostic_handler=diagnostics,
    )

    with sdk.run(agent_id="agent", name="Agent", version="1"):
        pass

    assert [type(event).__name__ for event in sink.events] == [
        "RunStarted",
        "RunCompleted",
    ]
    assert [(item.component, item.operation) for item in diagnostics.diagnostics] == [
        ("run_context_bridge", "start")
    ]


@pytest.mark.integration
def test_activation_failure_ends_partial_span_and_is_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer = Mock(spec=Tracer)
    span = Mock(spec=Span)
    tracer.start_span.return_value = span
    activation = _BrokenActivation(enter_error=RuntimeError("activation broke"))
    monkeypatch.setattr(trace, "use_span", Mock(return_value=activation))
    diagnostics = CollectingDiagnosticHandler()
    sdk = AgentReliability(
        run_context_bridge=OpenTelemetryRunContextBridge(tracer),
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator(),
        diagnostic_handler=diagnostics,
    )

    with sdk.run(agent_id="agent", name="Agent", version="1"):
        pass

    span.end.assert_called_once_with()
    assert diagnostics.diagnostics[0].operation == "start"


@pytest.mark.integration
def test_cleanup_failure_still_ends_span_and_preserves_user_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer = Mock(spec=Tracer)
    span = Mock(spec=Span)
    tracer.start_span.return_value = span
    activation = _BrokenActivation()
    activation.exit_error = RuntimeError("detach broke")
    monkeypatch.setattr(trace, "use_span", Mock(return_value=activation))
    diagnostics = CollectingDiagnosticHandler()
    sdk = AgentReliability(
        run_context_bridge=OpenTelemetryRunContextBridge(tracer),
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator(),
        diagnostic_handler=diagnostics,
    )
    original = LookupError("private")

    with (
        pytest.raises(LookupError) as exc_info,
        sdk.run(agent_id="agent", name="Agent", version="1"),
    ):
        raise original

    assert exc_info.value is original
    span.end.assert_called_once_with()
    assert diagnostics.diagnostics[0].operation == "finish"


@pytest.mark.integration
def test_span_end_failure_is_diagnosed_without_failing_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer = Mock(spec=Tracer)
    span = Mock(spec=Span)
    span.end.side_effect = RuntimeError("end broke")
    tracer.start_span.return_value = span
    activation = _BrokenActivation()
    monkeypatch.setattr(trace, "use_span", Mock(return_value=activation))
    diagnostics = CollectingDiagnosticHandler()
    sdk = AgentReliability(
        run_context_bridge=OpenTelemetryRunContextBridge(tracer),
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator(),
        diagnostic_handler=diagnostics,
    )

    with sdk.run(agent_id="agent", name="Agent", version="1"):
        pass

    span.end.assert_called_once_with()
    assert diagnostics.diagnostics[0].operation == "finish"


@pytest.mark.integration
def test_status_attribute_failure_still_exits_activation_and_ends_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure setting ``agent_reliability.run.status`` (the first of
    ``finish()``'s three independent cleanup steps) must not prevent the
    other two — activation exit and span end — from being attempted, per
    ADR-0006 ("attempts every independent cleanup action")."""
    tracer = Mock(spec=Tracer)
    span = Mock(spec=Span)
    span.set_attribute.side_effect = RuntimeError("set_attribute broke")
    tracer.start_span.return_value = span
    activation = _BrokenActivation()
    monkeypatch.setattr(trace, "use_span", Mock(return_value=activation))
    diagnostics = CollectingDiagnosticHandler()
    sdk = AgentReliability(
        run_context_bridge=OpenTelemetryRunContextBridge(tracer),
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator(),
        diagnostic_handler=diagnostics,
    )

    with sdk.run(agent_id="agent", name="Agent", version="1"):
        pass

    span.end.assert_called_once_with()
    assert diagnostics.diagnostics[0].operation == "finish"
    assert str(diagnostics.diagnostics[0].exception) == "set_attribute broke"


@pytest.mark.integration
def test_first_of_multiple_finish_failures_is_reported_but_all_are_attempted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If more than one of ``finish()``'s three cleanup steps fails, only
    the *first* failure is diagnosed/raised, but every step still runs —
    the "first error wins" half of ADR-0006's cleanup contract, otherwise
    unverified by any other test."""
    tracer = Mock(spec=Tracer)
    span = Mock(spec=Span)
    span.set_attribute.side_effect = RuntimeError("set_attribute broke FIRST")
    span.end.side_effect = RuntimeError("end broke THIRD")
    tracer.start_span.return_value = span
    activation = _BrokenActivation()
    activation.exit_error = RuntimeError("detach broke SECOND")
    monkeypatch.setattr(trace, "use_span", Mock(return_value=activation))
    diagnostics = CollectingDiagnosticHandler()
    sdk = AgentReliability(
        run_context_bridge=OpenTelemetryRunContextBridge(tracer),
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator(),
        diagnostic_handler=diagnostics,
    )

    with sdk.run(agent_id="agent", name="Agent", version="1"):
        pass

    span.set_attribute.assert_called()
    span.end.assert_called_once_with()
    assert len(diagnostics.diagnostics) == 1
    assert diagnostics.diagnostics[0].operation == "finish"
    assert str(diagnostics.diagnostics[0].exception) == "set_attribute broke FIRST"


@pytest.mark.integration
def test_explicit_tracer_does_not_replace_global_provider(otel: OtelHarness) -> None:
    before = trace.get_tracer_provider()
    sdk = _sdk(otel)

    with sdk.run(agent_id="agent", name="Agent", version="1"):
        pass

    assert trace.get_tracer_provider() is before


@pytest.mark.integration
def test_wrong_tracer_type_raises_immediately() -> None:
    with pytest.raises(TypeError, match="Tracer"):
        OpenTelemetryRunContextBridge(tracer=object())  # type: ignore[arg-type]


@pytest.mark.integration
def test_default_bridge_uses_stable_instrumentation_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_tracer = Mock(return_value=Mock(spec=Tracer))
    monkeypatch.setattr(trace, "get_tracer", get_tracer)

    OpenTelemetryRunContextBridge()

    get_tracer.assert_called_once_with(
        "agent_reliability", agent_reliability.__version__
    )

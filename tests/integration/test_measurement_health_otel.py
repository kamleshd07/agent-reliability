from __future__ import annotations

from unittest.mock import Mock

import pytest

pytest.importorskip("opentelemetry", reason="requires the 'otel-test' extra")

from opentelemetry import trace
from opentelemetry.trace import Span, Tracer

from agent_reliability.adapters.otel import OpenTelemetryRunContextBridge
from agent_reliability.measurement import MeasurementHealth, MeasurementHealthReason
from agent_reliability.sdk import AgentReliability
from tests.fakes.clock import FakeClock
from tests.fakes.diagnostics import BrokenDiagnosticHandler
from tests.fakes.id_generator import SequentialRunIdGenerator
from tests.fakes.sinks import BrokenSink


class _Activation:
    def __enter__(self) -> Span:
        return Mock(spec=Span)

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


def test_otel_span_never_receives_application_exception_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracer = Mock(spec=Tracer)
    span = Mock(spec=Span)
    tracer.start_span.return_value = span
    monkeypatch.setattr(trace, "use_span", Mock(return_value=_Activation()))
    sdk = AgentReliability(
        run_context_bridge=OpenTelemetryRunContextBridge(tracer),
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator("otel-health"),
    )

    secret = "M9_PRIVATE_PROMPT_SECRET"
    with (
        pytest.raises(LookupError, match=secret),
        sdk.run(agent_id="agent", name="Agent", version="1") as run,
    ):
        raise LookupError(secret)

    assert run.measurement_health.health is MeasurementHealth.HEALTHY
    rendered_calls = repr(span.method_calls)
    assert secret not in rendered_calls
    assert "LookupError" in rendered_calls


def test_otel_bridge_failure_does_not_change_local_measurement_health() -> None:
    tracer = Mock(spec=Tracer)
    tracer.start_span.side_effect = RuntimeError("M9_API_TOKEN_SECRET")
    sdk = AgentReliability(
        run_context_bridge=OpenTelemetryRunContextBridge(tracer),
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator("otel-failure"),
    )
    with sdk.run(agent_id="agent", name="Agent", version="1") as run:
        pass
    assert run.measurement_health.health is MeasurementHealth.HEALTHY


def test_event_sink_plus_otel_failure_has_only_local_delivery_degradation() -> None:
    tracer = Mock(spec=Tracer)
    tracer.start_span.side_effect = RuntimeError("M9_PRIVATE_PROMPT_SECRET")
    sdk = AgentReliability(
        sink=BrokenSink(),
        run_context_bridge=OpenTelemetryRunContextBridge(tracer),
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator("otel-combined"),
        diagnostic_handler=BrokenDiagnosticHandler(),
    )
    body_ran = False
    with sdk.run(agent_id="agent", name="Agent", version="1") as run:
        body_ran = True
    assert body_ran
    assert run.measurement_health.reasons == frozenset(
        {MeasurementHealthReason.EVENT_DELIVERY_FAILURE}
    )

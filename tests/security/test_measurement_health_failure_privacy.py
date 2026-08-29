from __future__ import annotations

import logging

from _pytest.logging import LogCaptureFixture

from agent_reliability.adapters import CompositeEventSink
from agent_reliability.evaluation import (
    EvaluationDecision,
    EvaluationExecutionFailure,
    EvaluatorIdentity,
)
from agent_reliability.measurement import MeasurementHealthReason
from agent_reliability.ports import InstrumentationEvent
from agent_reliability.sdk import AgentReliability, EvaluatorRunner
from tests.fakes.clock import FakeClock
from tests.fakes.id_generator import SequentialRunIdGenerator
from tests.fakes.sinks import RecordingSink


class _SecretEvaluator:
    identity = EvaluatorIdentity("privacy-check", "1")
    deterministic = True

    def evaluate(self, value: object) -> EvaluationDecision:
        raise RuntimeError(f"M9_EVALUATOR_EXCEPTION_SECRET {value!r}")


class _SecretSink:
    def emit(self, event: InstrumentationEvent) -> None:
        raise RuntimeError("M9_API_TOKEN_SECRET")


class _SecretBridge:
    def start(self, run: object) -> object:
        raise RuntimeError("M9_PRIVATE_PROMPT_SECRET")


class _SecretDiagnosticHandler:
    def handle(self, diagnostic: object) -> None:
        raise RuntimeError("M9_DIAGNOSTIC_SECRET")


class _ToolPayload:
    def __repr__(self) -> str:
        return "M9_TOOL_ARGUMENT_SECRET"


def test_combined_failure_secrets_never_enter_public_outputs_or_default_logs(
    caplog: LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="agent_reliability.sdk")
    result = EvaluatorRunner(clock=FakeClock()).evaluate(
        _SecretEvaluator(), _ToolPayload()
    )
    assert isinstance(result, EvaluationExecutionFailure)

    events = RecordingSink()
    sdk = AgentReliability(
        sink=CompositeEventSink([events, _SecretSink()]),
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator("privacy"),
        run_context_bridge=_SecretBridge(),
    )
    with sdk.run(agent_id="agent", name="Agent", version="1") as run:
        run.record_evaluation_failure(failure=result)

    rendered = " ".join(
        [repr(run.measurement_health), str(run.measurement_health), repr(events.events)]
    )
    secrets = (
        "M9_PRIVATE_PROMPT_SECRET",
        "M9_API_TOKEN_SECRET",
        "M9_EVALUATOR_EXCEPTION_SECRET",
        "M9_TOOL_ARGUMENT_SECRET",
    )
    for secret in secrets:
        assert secret not in rendered
        assert secret not in caplog.text
    assert result.exception_type == "RuntimeError"
    assert run.measurement_health.reasons == frozenset(
        {
            MeasurementHealthReason.EVENT_DELIVERY_FAILURE,
            MeasurementHealthReason.EVALUATOR_EXECUTION_FAILURE,
        }
    )


def test_broken_diagnostic_handler_does_not_recurse_or_expose_its_secret(
    caplog: LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="agent_reliability.sdk")
    sdk = AgentReliability(
        sink=_SecretSink(),
        clock=FakeClock(),
        run_id_generator=SequentialRunIdGenerator("diagnostic"),
        diagnostic_handler=_SecretDiagnosticHandler(),
    )
    body_ran = False
    with sdk.run(agent_id="agent", name="Agent", version="1") as run:
        body_ran = True
    assert body_ran
    assert "M9_DIAGNOSTIC_SECRET" not in caplog.text
    assert "M9_API_TOKEN_SECRET" not in caplog.text
    assert run.measurement_health.reasons == frozenset(
        {MeasurementHealthReason.EVENT_DELIVERY_FAILURE}
    )

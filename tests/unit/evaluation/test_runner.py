from __future__ import annotations

import asyncio
import logging

import pytest

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation import (
    EqualityEvaluator,
    EvaluationDecision,
    EvaluationExecutionFailure,
    EvaluationFailureStage,
    EvaluationResult,
    EvaluatorIdentity,
)
from agent_reliability.sdk import EvaluatorRunner
from tests.fakes.clock import BrokenClock, FakeClock
from tests.fakes.diagnostics import BrokenDiagnosticHandler, CollectingDiagnosticHandler


def test_runner_attaches_identity_determinism_and_injected_time() -> None:
    evaluator = EqualityEvaluator(EvaluatorIdentity("exact-result", "3"), "expected")
    result = EvaluatorRunner(clock=FakeClock()).evaluate(evaluator, "expected")
    assert isinstance(result, EvaluationResult)
    assert result.outcome is EvaluationOutcome.PASS
    assert result.provenance.identity is evaluator.identity
    assert result.provenance.deterministic is True
    assert result.provenance.evaluated_at == FakeClock().now()


def test_raw_evaluator_failure_raises_but_safe_runner_returns_failure() -> None:
    secret = "customer-token-DO-NOT-RETAIN"

    class BrokenEvaluator:
        identity = EvaluatorIdentity("broken-rule", "1")
        deterministic = True

        def evaluate(self, value: object) -> EvaluationDecision:
            raise RuntimeError(f"could not evaluate {secret}")

    evaluator = BrokenEvaluator()
    with pytest.raises(RuntimeError, match=secret):
        evaluator.evaluate(object())

    diagnostics = CollectingDiagnosticHandler()
    failure = EvaluatorRunner(
        clock=FakeClock(), diagnostic_handler=diagnostics
    ).evaluate(evaluator, object())
    assert failure == EvaluationExecutionFailure(
        evaluator.identity,
        EvaluationFailureStage.EVALUATION,
        "RuntimeError",
    )
    assert not hasattr(failure, "outcome")
    assert secret not in repr(failure)
    assert diagnostics.diagnostics[0].component == "evaluator"
    assert diagnostics.diagnostics[0].operation == "evaluate"


def test_clock_failure_produces_timestamp_failure_not_result() -> None:
    evaluator = EqualityEvaluator(EvaluatorIdentity("exact-result", "3"), 1)
    failure = EvaluatorRunner(clock=BrokenClock()).evaluate(evaluator, 1)
    assert isinstance(failure, EvaluationExecutionFailure)
    assert failure.stage is EvaluationFailureStage.TIMESTAMP
    assert failure.exception_type == "RuntimeError"


async def test_async_runner_has_explicit_awaited_semantics() -> None:
    class AsyncRule:
        identity = EvaluatorIdentity("async-rule", "1")
        deterministic = False

        async def evaluate(self, value: int) -> EvaluationDecision:
            await asyncio.sleep(0)
            return EvaluationDecision(
                EvaluationOutcome.PASS if value > 0 else EvaluationOutcome.FAIL,
                "positive",
            )

    result = await EvaluatorRunner(clock=FakeClock()).evaluate_async(AsyncRule(), 1)
    assert isinstance(result, EvaluationResult)
    assert result.provenance.deterministic is False


@pytest.mark.parametrize("signal", [KeyboardInterrupt(), SystemExit()])
def test_safe_runner_never_swallows_base_exception(signal: BaseException) -> None:
    class SignallingEvaluator:
        identity = EvaluatorIdentity("signalling-rule", "1")
        deterministic = True

        def evaluate(self, value: object) -> EvaluationDecision:
            raise signal

    with pytest.raises(type(signal)):
        EvaluatorRunner(clock=FakeClock()).evaluate(SignallingEvaluator(), object())


async def test_async_cancellation_is_not_suppressed() -> None:
    class CancelledEvaluator:
        identity = EvaluatorIdentity("cancelled-rule", "1")
        deterministic = False

        async def evaluate(self, value: object) -> EvaluationDecision:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await EvaluatorRunner(clock=FakeClock()).evaluate_async(
            CancelledEvaluator(), object()
        )


def test_default_diagnostic_log_never_renders_input_or_exception_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "BANK_ACCOUNT_987654321"

    class SensitiveInput:
        def __repr__(self) -> str:
            return secret

    class BrokenEvaluator:
        identity = EvaluatorIdentity("privacy-rule", "1")
        deterministic = True

        def evaluate(self, value: SensitiveInput) -> EvaluationDecision:
            raise ValueError(f"bad customer record {secret}")

    with caplog.at_level(logging.WARNING, logger="agent_reliability.sdk"):
        failure = EvaluatorRunner(clock=FakeClock()).evaluate(
            BrokenEvaluator(), SensitiveInput()
        )
    assert isinstance(failure, EvaluationExecutionFailure)
    assert secret not in caplog.text
    assert secret not in repr(failure)
    assert "ValueError" in caplog.text


async def test_concurrent_async_evaluations_do_not_share_framework_state() -> None:
    class EchoEvaluator:
        identity = EvaluatorIdentity("echo-rule", "1")
        deterministic = True

        async def evaluate(self, value: int) -> EvaluationDecision:
            await asyncio.sleep(0)
            return EvaluationDecision(
                EvaluationOutcome.PASS if value % 2 == 0 else EvaluationOutcome.FAIL
            )

    runner = EvaluatorRunner()
    results = await asyncio.gather(
        *(runner.evaluate_async(EchoEvaluator(), value) for value in range(100))
    )
    assert all(isinstance(result, EvaluationResult) for result in results)
    assert [
        result.outcome for result in results if isinstance(result, EvaluationResult)
    ] == [
        EvaluationOutcome.PASS if value % 2 == 0 else EvaluationOutcome.FAIL
        for value in range(100)
    ]


def test_runner_rejects_invalid_dependencies_immediately() -> None:
    with pytest.raises(TypeError, match="Clock"):
        EvaluatorRunner(clock=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="DiagnosticHandler"):
        EvaluatorRunner(diagnostic_handler=object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "evaluator",
    [
        type(
            "BadIdentity",
            (),
            {
                "identity": "wrong",
                "deterministic": True,
                "evaluate": lambda self, value: EvaluationDecision(
                    EvaluationOutcome.PASS
                ),
            },
        )(),
        type(
            "BadDeterminism",
            (),
            {
                "identity": EvaluatorIdentity("bad-determinism", "1"),
                "deterministic": 1,
                "evaluate": lambda self, value: EvaluationDecision(
                    EvaluationOutcome.PASS
                ),
            },
        )(),
        type(
            "BadDecision",
            (),
            {
                "identity": EvaluatorIdentity("bad-decision", "1"),
                "deterministic": True,
                "evaluate": lambda self, value: "pass",
            },
        )(),
    ],
)
def test_runner_turns_malformed_evaluator_contract_into_failure(
    evaluator: object,
) -> None:
    failure = EvaluatorRunner(clock=FakeClock()).evaluate(
        evaluator,
        object(),  # type: ignore[arg-type]
    )
    assert isinstance(failure, EvaluationExecutionFailure)
    assert failure.stage is EvaluationFailureStage.EVALUATION


async def test_async_evaluator_exception_returns_failure() -> None:
    class BrokenAsyncEvaluator:
        identity = EvaluatorIdentity("broken-async", "1")
        deterministic = False

        async def evaluate(self, value: object) -> EvaluationDecision:
            raise RuntimeError("unavailable")

    failure = await EvaluatorRunner(clock=FakeClock()).evaluate_async(
        BrokenAsyncEvaluator(), object()
    )
    assert isinstance(failure, EvaluationExecutionFailure)
    assert failure.stage is EvaluationFailureStage.EVALUATION


def test_broken_diagnostic_handler_is_last_resort_suppressed() -> None:
    class BrokenEvaluator:
        identity = EvaluatorIdentity("broken-rule", "1")
        deterministic = True

        def evaluate(self, value: object) -> EvaluationDecision:
            raise RuntimeError("unavailable")

    failure = EvaluatorRunner(
        clock=FakeClock(), diagnostic_handler=BrokenDiagnosticHandler()
    ).evaluate(BrokenEvaluator(), object())
    assert isinstance(failure, EvaluationExecutionFailure)


def test_pathological_exception_class_name_is_safely_bounded() -> None:
    pathological_error = type("X" * 129, (Exception,), {})

    class BrokenEvaluator:
        identity = EvaluatorIdentity("broken-rule", "1")
        deterministic = True

        def evaluate(self, value: object) -> EvaluationDecision:
            raise pathological_error

    failure = EvaluatorRunner(clock=FakeClock()).evaluate(BrokenEvaluator(), object())
    assert isinstance(failure, EvaluationExecutionFailure)
    assert failure.exception_type == "Exception"

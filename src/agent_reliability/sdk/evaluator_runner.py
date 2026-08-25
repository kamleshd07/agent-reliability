"""Failure-isolated sync and async evaluator execution."""

from __future__ import annotations

import contextlib
from typing import Protocol, TypeVar

from agent_reliability.adapters.system_clock import SystemClock
from agent_reliability.evaluation import (
    AsyncEvaluator,
    EvaluationDecision,
    EvaluationExecutionFailure,
    EvaluationFailureStage,
    EvaluationProvenance,
    EvaluationResult,
    EvaluatorIdentity,
    SyncEvaluator,
)
from agent_reliability.ports.clock import Clock
from agent_reliability.sdk.diagnostics import (
    DiagnosticComponent,
    DiagnosticHandler,
    DiagnosticOperation,
    LoggingDiagnosticHandler,
    SdkDiagnostic,
)

__all__ = ["EvaluatorRunner"]

InputT = TypeVar("InputT")


class _EvaluatorDeclaration(Protocol):
    @property
    def identity(self) -> EvaluatorIdentity: ...

    @property
    def deterministic(self) -> bool: ...


class EvaluatorRunner:
    """Optional safe execution boundary for evaluators.

    Raw evaluator calls retain ordinary exception semantics. This runner
    catches ``Exception`` (never ``BaseException``), reports it through the
    existing diagnostic channel, and returns a distinct execution failure
    instead of manufacturing an outcome.
    """

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        diagnostic_handler: DiagnosticHandler | None = None,
    ) -> None:
        if clock is not None and not isinstance(clock, Clock):
            raise TypeError("clock must implement Clock")
        if diagnostic_handler is not None and not isinstance(
            diagnostic_handler, DiagnosticHandler
        ):
            raise TypeError("diagnostic_handler must implement DiagnosticHandler")
        self._clock = clock if clock is not None else SystemClock()
        self._diagnostic_handler = (
            diagnostic_handler
            if diagnostic_handler is not None
            else LoggingDiagnosticHandler()
        )

    def evaluate(
        self, evaluator: SyncEvaluator[InputT], value: InputT
    ) -> EvaluationResult | EvaluationExecutionFailure:
        identity: EvaluatorIdentity | None = None
        try:
            identity, deterministic = self._declarations(evaluator)
            decision = evaluator.evaluate(value)
            self._validate_decision(decision)
        except Exception as exc:
            return self._failure(identity, EvaluationFailureStage.EVALUATION, exc)
        return self._complete(identity, deterministic, decision)

    async def evaluate_async(
        self, evaluator: AsyncEvaluator[InputT], value: InputT
    ) -> EvaluationResult | EvaluationExecutionFailure:
        identity: EvaluatorIdentity | None = None
        try:
            identity, deterministic = self._declarations(evaluator)
            decision = await evaluator.evaluate(value)
            self._validate_decision(decision)
        except Exception as exc:
            return self._failure(identity, EvaluationFailureStage.EVALUATION, exc)
        return self._complete(identity, deterministic, decision)

    @staticmethod
    def _declarations(
        evaluator: _EvaluatorDeclaration,
    ) -> tuple[EvaluatorIdentity, bool]:
        identity = evaluator.identity
        deterministic = evaluator.deterministic
        if not isinstance(identity, EvaluatorIdentity):
            raise TypeError("evaluator.identity must be EvaluatorIdentity")
        if not isinstance(deterministic, bool):
            raise TypeError("evaluator.deterministic must be bool")
        return identity, deterministic

    @staticmethod
    def _validate_decision(decision: EvaluationDecision) -> None:
        if not isinstance(decision, EvaluationDecision):
            raise TypeError("evaluator.evaluate() must return EvaluationDecision")

    def _complete(
        self,
        identity: EvaluatorIdentity,
        deterministic: bool,
        decision: EvaluationDecision,
    ) -> EvaluationResult | EvaluationExecutionFailure:
        try:
            provenance = EvaluationProvenance(
                identity=identity,
                evaluated_at=self._clock.now(),
                deterministic=deterministic,
            )
            return EvaluationResult(
                outcome=decision.outcome,
                provenance=provenance,
                reason_code=decision.reason_code,
            )
        except Exception as exc:
            return self._failure(identity, EvaluationFailureStage.TIMESTAMP, exc)

    def _failure(
        self,
        identity: EvaluatorIdentity | None,
        stage: EvaluationFailureStage,
        exception: Exception,
    ) -> EvaluationExecutionFailure:
        is_evaluation = stage is EvaluationFailureStage.EVALUATION
        component: DiagnosticComponent = "evaluator" if is_evaluation else "clock"
        operation: DiagnosticOperation = "evaluate" if is_evaluation else "now"
        with contextlib.suppress(Exception):
            self._diagnostic_handler.handle(
                SdkDiagnostic(
                    component=component,
                    operation=operation,
                    run_id=None,
                    exception=exception,
                )
            )
        return EvaluationExecutionFailure(
            identity=identity,
            stage=stage,
            exception_type=self._safe_exception_type(exception),
        )

    @staticmethod
    def _safe_exception_type(exception: Exception) -> str:
        """Return bounded structural data without rendering the exception."""
        name = type(exception).__name__
        if (
            not name
            or len(name) > 128
            or not name.isprintable()
            or any(character.isspace() for character in name)
        ):
            return "Exception"
        return name

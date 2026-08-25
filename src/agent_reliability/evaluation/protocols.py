"""Small structural protocols for typed sync and async evaluators."""

from __future__ import annotations

from typing import Protocol, TypeVar

from agent_reliability.evaluation.identity import EvaluatorIdentity
from agent_reliability.evaluation.result import EvaluationDecision

__all__ = ["AsyncEvaluator", "SyncEvaluator"]

InputT_contra = TypeVar("InputT_contra", contravariant=True)


class SyncEvaluator(Protocol[InputT_contra]):
    """Structural contract for a synchronous evaluator.

    Implementations declare stable identity and determinism metadata, then
    return an :class:`EvaluationDecision`. Use ``EvaluatorRunner`` to attach a
    timestamp and provenance and to isolate evaluator execution failures.
    """

    @property
    def identity(self) -> EvaluatorIdentity: ...

    @property
    def deterministic(self) -> bool: ...

    def evaluate(self, value: InputT_contra) -> EvaluationDecision: ...


class AsyncEvaluator(Protocol[InputT_contra]):
    """Structural contract for an asynchronous evaluator.

    The semantics match :class:`SyncEvaluator`; only ``evaluate`` is awaited.
    Use ``EvaluatorRunner.evaluate_async`` to obtain a provenance-bearing
    result or a distinct execution-failure value.
    """

    @property
    def identity(self) -> EvaluatorIdentity: ...

    @property
    def deterministic(self) -> bool: ...

    async def evaluate(self, value: InputT_contra) -> EvaluationDecision: ...

"""Sync driver ``SyncLLMJudge`` (P29 S04).

Shares the sans-IO engine with the async judge, so decisions and failure
classes are identical by construction. A blocking provider cannot be
interrupted from outside: the driver passes the remaining deadline to the
provider, measures elapsed monotonic time, and classifies an overrun as
``JudgeTimeoutError`` after the call returns; the late reply is discarded.
This module never uses ``asyncio.run`` (ADR-0007: no automatic bridging).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from agent_reliability.evaluation import EvaluationDecision, EvaluatorIdentity
from agent_reliability.experimental.judge._engine import (
    SLEPT,
    Raised,
    Replied,
    Response,
    Sleep,
)
from agent_reliability.experimental.judge.behaviour import (
    JudgeBehaviour,
    behaviour_of,
)
from agent_reliability.experimental.judge.budget import BudgetTracker
from agent_reliability.experimental.judge.judge import build_engine
from agent_reliability.experimental.judge.provider import (
    ProviderCall,
    SyncJudgeProvider,
)
from agent_reliability.experimental.judge.rubric import Rubric
from agent_reliability.experimental.judge.values import (
    EvaluationRequest,
    JudgeBudget,
    JudgeEvaluation,
    JudgeLimits,
    JudgePolicy,
)

__all__ = ["SyncLLMJudge"]


class SyncLLMJudge:
    """Model-backed evaluator over a blocking customer-supplied provider."""

    def __init__(
        self,
        *,
        rubric: Rubric,
        provider: SyncJudgeProvider,
        model_label: str,
        policy: JudgePolicy | None = None,
        limits: JudgeLimits | None = None,
        budget: JudgeBudget | BudgetTracker | None = None,
        retain_cause: bool = False,
        nonce_source: Callable[[], str] | None = None,
        jitter: Callable[[], float] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        complete = getattr(provider, "complete", None)
        if not callable(complete) or not hasattr(provider, "provider_label"):
            raise TypeError("provider must implement SyncJudgeProvider")
        self._identity, self._engine = build_engine(
            rubric=rubric,
            model_label=model_label,
            policy=policy,
            limits=limits,
            budget=budget,
            reports_tokens=getattr(provider, "reports_tokens", False) is True,
            retain_cause=retain_cause,
            nonce_source=nonce_source,
            jitter=jitter,
        )
        self._provider = provider
        self._rubric = rubric
        self._behaviour = behaviour_of(rubric, policy, limits)
        self._monotonic = monotonic
        self._sleep = sleep

    @property
    def identity(self) -> EvaluatorIdentity:
        return self._identity

    @property
    def deterministic(self) -> bool:
        return False

    @property
    def rubric(self) -> Rubric:
        return self._rubric

    @property
    def behaviour(self) -> JudgeBehaviour:
        """Content-free description of what determines this judge's behaviour."""
        return self._behaviour

    def __repr__(self) -> str:
        return f"SyncLLMJudge(identity={self._identity!r})"

    def evaluate(self, value: EvaluationRequest) -> EvaluationDecision:
        return self.evaluate_detailed(value).decision

    def evaluate_detailed(self, value: EvaluationRequest) -> JudgeEvaluation:
        """Like :meth:`evaluate` but also returns content-free counters."""
        gen = self._engine.run(value, self._monotonic)
        try:
            action = next(gen)
            while True:
                response: Response
                if isinstance(action, Sleep):
                    self._sleep(action.seconds)
                    response = SLEPT
                else:
                    response = self._call(action.call)
                action = gen.send(response)
        except StopIteration as stop:
            result: JudgeEvaluation = stop.value
            return result
        finally:
            gen.close()

    def _call(self, call: ProviderCall) -> Replied | Raised:
        started = self._monotonic()
        outcome: Replied | Raised
        try:
            outcome = Replied(self._provider.complete(call))
        except Exception as exc:
            outcome = Raised(exc)
        if self._monotonic() - started > call.deadline_seconds:
            # Overrun: the late reply (or error) is discarded; classify as timeout.
            return Raised(TimeoutError())
        return outcome

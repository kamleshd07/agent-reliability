"""Async ``LLMJudge`` (P29 S03) and the shared judge construction.

``LLMJudge`` satisfies ``AsyncEvaluator[EvaluationRequest]`` and runs unchanged
through ``EvaluatorRunner.evaluate_async``. Every judge failure is an exception
(a ``JudgeError`` subclass) that the runner reduces to an execution failure;
nothing here ever returns a verdict for a failed judgment (I-P29-1).
"""

from __future__ import annotations

import asyncio
import inspect
import random
from collections.abc import Callable

from agent_reliability.evaluation import EvaluationDecision, EvaluatorIdentity
from agent_reliability.experimental.judge._engine import (
    SLEPT,
    CallProvider,
    JudgeEngine,
    Raised,
    Replied,
    Response,
    Sleep,
)
from agent_reliability.experimental.judge.budget import BudgetTracker
from agent_reliability.experimental.judge.identity import (
    compose_identity,
    effective_min_confidence,
)
from agent_reliability.experimental.judge.provider import JudgeProvider, ProviderCall
from agent_reliability.experimental.judge.rubric import Rubric
from agent_reliability.experimental.judge.values import (
    EvaluationRequest,
    JudgeBudget,
    JudgeEvaluation,
    JudgeLimits,
    JudgePolicy,
)

__all__ = ["LLMJudge"]


def build_engine(
    *,
    rubric: Rubric,
    model_label: str,
    policy: JudgePolicy | None,
    limits: JudgeLimits | None,
    budget: JudgeBudget | BudgetTracker | None,
    reports_tokens: bool,
    retain_cause: bool,
    nonce_source: Callable[[], str] | None,
    jitter: Callable[[], float] | None,
) -> tuple[EvaluatorIdentity, JudgeEngine]:
    """Validate shared construction arguments and build identity plus engine."""
    if not isinstance(rubric, Rubric):
        raise TypeError("rubric must be a Rubric")
    policy = policy if policy is not None else JudgePolicy()
    limits = limits if limits is not None else JudgeLimits()
    if not isinstance(policy, JudgePolicy) or not isinstance(limits, JudgeLimits):
        raise TypeError("policy and limits must be JudgePolicy and JudgeLimits")
    if type(retain_cause) is not bool:
        raise TypeError("retain_cause must be a bool")
    if policy.repeats > 1 and "judge_disagreement" not in rubric.reason_codes.unknown:
        raise ValueError(
            "repeats > 1 requires judge_disagreement in the rubric unknown codes"
        )
    tracker: BudgetTracker | None
    if budget is None:
        tracker = None
    elif isinstance(budget, BudgetTracker):
        tracker = budget
    elif isinstance(budget, JudgeBudget):
        tracker = BudgetTracker(budget)
    else:
        raise TypeError("budget must be a JudgeBudget or BudgetTracker")
    if tracker is not None and tracker.budget.enforces_anything and not reports_tokens:
        raise ValueError(
            "a token or monetary budget requires a provider declared with "
            "reports_tokens=True"
        )
    identity = compose_identity(rubric, model_label=model_label, policy=policy)
    engine = JudgeEngine(
        rubric=rubric,
        min_confidence=effective_min_confidence(rubric, policy),
        policy=policy,
        limits=limits,
        tracker=tracker,
        retain_cause=retain_cause,
        nonce_source=nonce_source,
        jitter=jitter if jitter is not None else random.random,
    )
    return identity, engine


class LLMJudge:
    """Model-backed evaluator over a customer-supplied async provider.

    ``deterministic`` is always ``False``. ``retain_cause=True`` chains the
    provider's own exception onto the raised ``JudgeError`` (it may contain
    prompt text) and is documented as sending content-bearing objects to the
    trusted ``DiagnosticHandler``; the default is ``False``.
    """

    def __init__(
        self,
        *,
        rubric: Rubric,
        provider: JudgeProvider,
        model_label: str,
        policy: JudgePolicy | None = None,
        limits: JudgeLimits | None = None,
        budget: JudgeBudget | BudgetTracker | None = None,
        retain_cause: bool = False,
        nonce_source: Callable[[], str] | None = None,
        jitter: Callable[[], float] | None = None,
    ) -> None:
        complete = getattr(provider, "complete", None)
        if not callable(complete) or not hasattr(provider, "provider_label"):
            raise TypeError("provider must implement JudgeProvider")
        if (inspect.isfunction(complete) or inspect.ismethod(complete)) and (
            not inspect.iscoroutinefunction(complete)
        ):
            raise TypeError(
                "provider.complete must be async; use SyncLLMJudge for "
                "blocking providers"
            )
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

    @property
    def identity(self) -> EvaluatorIdentity:
        return self._identity

    @property
    def deterministic(self) -> bool:
        return False

    @property
    def rubric(self) -> Rubric:
        return self._rubric

    def __repr__(self) -> str:
        return f"LLMJudge(identity={self._identity!r})"

    async def evaluate(self, value: EvaluationRequest) -> EvaluationDecision:
        return (await self.evaluate_detailed(value)).decision

    async def evaluate_detailed(self, value: EvaluationRequest) -> JudgeEvaluation:
        """Like :meth:`evaluate` but also returns content-free counters.

        On failure the raised ``JudgeError`` carries the same counters in
        ``.stats``. Intended for a coordinator that reports locally.
        """
        loop = asyncio.get_running_loop()
        gen = self._engine.run(value, loop.time)
        try:
            action = next(gen)
            while True:
                response: Response
                if isinstance(action, Sleep):
                    await asyncio.sleep(action.seconds)
                    response = SLEPT
                else:
                    response = await self._call(action)
                action = gen.send(response)
        except StopIteration as stop:
            result: JudgeEvaluation = stop.value
            return result
        finally:
            gen.close()

    async def _call(self, action: CallProvider) -> Replied | Raised:
        call: ProviderCall = action.call
        try:
            async with asyncio.timeout(call.deadline_seconds):
                reply = await self._provider.complete(call)
            return Replied(reply)
        except Exception as exc:
            # Includes TimeoutError from asyncio.timeout. BaseException
            # (CancelledError, KeyboardInterrupt) is never caught (ADR-0004).
            return Raised(exc)

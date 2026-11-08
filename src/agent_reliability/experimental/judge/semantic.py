"""EXPERIMENTAL: a small developer-facing facade over the judge machinery (P29).

``SemanticChecks`` answers "evaluate what my agent actually said" in a few lines:
it picks the reference rubric for each check, builds the sync or async judge from
the provider you pass, binds one indicator per check, and returns a content-free
``SemanticVerdict`` for every call. It adds no protocol, no wire member and no
dependency: everything goes through ``JudgeCoordinator`` and the existing
evidence path.

What a verdict is, and is not
-----------------------------
* ``determinate``: the judge returned PASS or FAIL. This is a *model opinion about
  one dimension*, never proof of a business outcome (``authoritative`` is always
  ``False``). Keep deterministic checks for anything that can be checked
  deterministically; treat a judge FAIL as a flag for review.
* ``unknown``: the judge ran and could not decide (insufficient evidence, low
  confidence, disagreement), or a required input was missing so no model was called.
* ``evaluator_failure``: the *evaluator* did not produce a judgment (timeout,
  provider error, malformed or oversize output, budget, overload). This says nothing
  about the agent and is never recorded as FAIL.
* ``skipped``: sampling or admission declined the evaluation, or the run is not
  recording. No evidence exists.

Raw evaluated text goes only to the provider object you pass. A verdict carries the
outcome, a closed reason code, a failure class name and counters (latency, tokens):
no prompt, answer or document text.
"""

from __future__ import annotations

import contextvars
import enum
import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.experimental.judge.budget import BudgetTracker
from agent_reliability.experimental.judge.coordinator import (
    EvaluationDisposition,
    EvaluationScope,
    IndicatorBinding,
    JudgeCoordinator,
    JudgeInvocationReport,
    JudgeObserver,
)
from agent_reliability.experimental.judge.executor import ExecutorSyncProvider
from agent_reliability.experimental.judge.judge import LLMJudge
from agent_reliability.experimental.judge.reference import load_reference_rubric
from agent_reliability.experimental.judge.rubric import Rubric
from agent_reliability.experimental.judge.sync import SyncLLMJudge
from agent_reliability.experimental.judge.values import (
    ContentPart,
    ContentRole,
    ContentTrust,
    EvaluationRequest,
    JudgeBudget,
    JudgeDimension,
    JudgeLimits,
    JudgePolicy,
    SamplingPolicy,
)

__all__ = [
    "CHECKS",
    "SemanticChecks",
    "SemanticScope",
    "SemanticStatus",
    "SemanticVerdict",
]

#: check name -> (reference rubric id, dimension)
CHECKS: Final[Mapping[str, tuple[str, JudgeDimension]]] = {
    "groundedness": ("judge-groundedness", JudgeDimension.GROUNDEDNESS),
    "relevance": ("judge-answer-relevance", JudgeDimension.ANSWER_RELEVANCE),
    "correctness": ("judge-answer-correctness", JudgeDimension.ANSWER_CORRECTNESS),
    "requirements": (
        "judge-instruction-adherence",
        JudgeDimension.INSTRUCTION_ADHERENCE,
    ),
    "completion": (
        "judge-task-completion-evidence",
        JudgeDimension.TASK_COMPLETION_EVIDENCE,
    ),
}

#: Optional inputs each check accepts; anything else is rejected (typos are errors).
_INPUTS: Final[Mapping[str, frozenset[str]]] = {
    "groundedness": frozenset({"context", "question"}),
    "relevance": frozenset({"question", "context"}),
    "correctness": frozenset({"reference", "question"}),
    "requirements": frozenset({"requirements", "question"}),
    "completion": frozenset({"evidence", "question"}),
}
#: Inputs that may be marked trusted (operator-authored text only).
_TRUSTABLE: Final = frozenset({"requirements", "reference"})


class SemanticStatus(enum.StrEnum):
    DETERMINATE = "determinate"
    UNKNOWN = "unknown"
    EVALUATOR_FAILURE = "evaluator_failure"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class SemanticVerdict:
    """Content-free result of one semantic check (kept local).

    Only the recorded evidence leaves the process.
    """

    check: str
    indicator: str
    status: SemanticStatus
    outcome: EvaluationOutcome | None
    reason_code: str | None
    failure_class: str | None
    disposition: EvaluationDisposition
    latency_ms: int = 0
    attempts: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None

    #: A model's opinion is never authoritative proof of a business outcome.
    authoritative: bool = field(default=False, init=False)

    @property
    def is_agent_failure_signal(self) -> bool:
        """True only for a determinate FAIL (never an evaluator failure or UNKNOWN)."""
        return (
            self.status is SemanticStatus.DETERMINATE
            and self.outcome is EvaluationOutcome.FAIL
        )


_box: contextvars.ContextVar[list[JudgeInvocationReport] | None] = (
    contextvars.ContextVar("agent_reliability_semantic_box", default=None)
)


class _Collector:
    """Hands each report to the call that caused it, then to the user's observer."""

    def __init__(self, inner: JudgeObserver | None) -> None:
        self._inner = inner

    def on_report(self, report: JudgeInvocationReport) -> None:
        box = _box.get()
        if box is not None:
            box.append(report)
        if self._inner is not None:
            self._inner.on_report(report)


def _is_async_provider(provider: Any) -> bool:
    return inspect.iscoroutinefunction(getattr(provider, "complete", None))


class SemanticChecks:
    """Configure semantic checks once; open a scope per agent run.

    ``provider`` is any ``JudgeProvider`` (async) or ``SyncJudgeProvider`` (blocking)
    object you own; nothing is read from the environment. For a blocking provider the
    deadline is enforced by a bounded helper thread (``enforce_deadline=True``) so a
    provider that never returns cannot block the agent forever. ``rubrics`` replaces
    the reference rubric of a check with your own (same dimension; bump
    ``rubric_version``).
    """

    def __init__(
        self,
        provider: Any,
        *,
        model_label: str,
        checks: Sequence[str] = ("groundedness", "relevance"),
        indicator_prefix: str = "semantic-",
        rubrics: Mapping[str, Rubric] | None = None,
        policy: JudgePolicy | None = None,
        limits: JudgeLimits | None = None,
        budget: JudgeBudget | BudgetTracker | None = None,
        sampling: SamplingPolicy | None = None,
        admission: Any = None,
        max_concurrency: int = 2,
        max_pending: int = 64,
        drain_timeout_seconds: float = 60.0,
        enforce_deadline: bool = True,
        observer: JudgeObserver | None = None,
    ) -> None:
        if not checks or len(set(checks)) != len(checks):
            raise ValueError("checks must be a non-empty sequence of distinct names")
        for name in checks:
            if name not in CHECKS:
                raise ValueError(
                    f"unknown check {name!r}; choose from {sorted(CHECKS)}"
                )
        custom = dict(rubrics or {})
        for name, rubric in custom.items():
            if name not in checks:
                raise ValueError("rubrics may only replace a selected check")
            if rubric.dimension is not CHECKS[name][1]:
                raise ValueError("a replacement rubric must keep the check's dimension")
        self._async = _is_async_provider(provider)
        if (
            not self._async
            and enforce_deadline
            and not isinstance(provider, ExecutorSyncProvider)
        ):
            provider = ExecutorSyncProvider(
                provider, max_threads=max(2, max_concurrency)
            )
        shared_budget = (
            budget
            if isinstance(budget, BudgetTracker)
            else (BudgetTracker(budget) if budget else None)
        )
        self._indicators: dict[str, str] = {}
        self._judges: dict[str, Any] = {}
        bindings: list[IndicatorBinding] = []
        for name in checks:
            rubric = custom.get(name) or load_reference_rubric(CHECKS[name][0])
            judge_cls = LLMJudge if self._async else SyncLLMJudge
            judge = judge_cls(
                rubric=rubric,
                provider=provider,
                model_label=model_label,
                policy=policy,
                limits=limits,
                budget=shared_budget,
            )
            indicator = f"{indicator_prefix}{name}"
            self._indicators[name] = indicator
            self._judges[name] = judge
            gate = admission
            if callable(gate) and not hasattr(gate, "decide"):
                gate = gate(name, judge)  # a factory: build a gate bound to this judge
            bindings.append(
                IndicatorBinding(
                    indicator,
                    judge,
                    sampling=sampling or SamplingPolicy(),
                    admission=gate,
                )
            )
        self._coordinator = JudgeCoordinator(
            bindings,
            max_concurrency=max_concurrency,
            max_pending=max_pending,
            drain_timeout_seconds=drain_timeout_seconds,
            observer=_Collector(observer),
        )

    @property
    def coordinator(self) -> JudgeCoordinator:
        """The underlying coordinator (for ``coverage()`` and advanced use)."""
        return self._coordinator

    @property
    def selected(self) -> frozenset[str]:
        return frozenset(self._indicators)

    @property
    def is_async(self) -> bool:
        return self._async

    def evaluator(self, check: str) -> Any:
        """The judge behind a check (for building a calibration gate bound to it)."""
        return self._judges[check]

    def indicator(self, check: str) -> str:
        return self._indicators[check]

    def scope(self, run: Any) -> SemanticScope:
        """A per-run scope: ``with`` (blocking) or ``async with`` (async provider)."""
        return SemanticScope(self, self._coordinator.scope(run))

    def coverage(self) -> str:
        """Failure and UNKNOWN rates beside the determinate counts."""
        return self._coordinator.coverage().describe()


def _parts(*items: tuple[ContentRole, str | None]) -> tuple[ContentPart, ...]:
    return tuple(ContentPart(role, text) for role, text in items if text is not None)


class SemanticScope:
    """One run's semantic checks; each check is evaluated once per scope."""

    def __init__(self, checks: SemanticChecks, inner: EvaluationScope) -> None:
        self._checks = checks
        self._inner = inner

    # -- context management -------------------------------------------------
    def __enter__(self) -> SemanticScope:
        self._inner.__enter__()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._inner.__exit__(*exc)

    async def __aenter__(self) -> SemanticScope:
        await self._inner.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._inner.__aexit__(*exc)

    # -- requests -----------------------------------------------------------
    def _request(
        self, check: str, answer: str, given: dict[str, Any], trusted: Sequence[str]
    ) -> EvaluationRequest:
        if check not in CHECKS:
            raise ValueError(f"unknown check {check!r}; choose from {sorted(CHECKS)}")
        if check not in self._checks.selected:
            raise ValueError(
                f"check {check!r} was not selected for this SemanticChecks"
            )
        if not isinstance(answer, str):
            raise TypeError("answer must be a str (use '' for an empty reply)")
        unknown = sorted(set(given) - _INPUTS[check])
        if unknown:
            raise ValueError(
                f"unexpected input(s) {unknown} for check {check!r}; "
                f"allowed: {sorted(_INPUTS[check])}"
            )
        unlisted = sorted(set(trusted) - _TRUSTABLE)
        if unlisted:
            raise ValueError(f"only {sorted(_TRUSTABLE)} can be marked trusted")
        context = given.get("context")
        if isinstance(context, str):
            context = [context]
        if context is not None and (
            not isinstance(context, Sequence)
            or not all(isinstance(c, str) for c in context)
        ):
            raise TypeError("context must be a str or a sequence of str")
        requirements = given.get("requirements")
        if isinstance(requirements, (list, tuple)):
            requirements = "\n".join(f"- {r}" for r in requirements)

        def part(role: ContentRole, text: Any, name: str) -> tuple[ContentPart, ...]:
            if text is None:
                return ()
            if not isinstance(text, str):
                raise TypeError(f"{name} must be a str")
            # Requirements and references are sent UNTRUSTED unless the operator
            # authored them and says so: user text must never be operator-trusted.
            trust = ContentTrust.TRUSTED if name in trusted else ContentTrust.UNTRUSTED
            return (ContentPart(role, text, trust),)

        parts = (
            *part(ContentRole.QUESTION, given.get("question"), "question"),
            *part(ContentRole.ANSWER, answer, "answer"),
            *(ContentPart(ContentRole.CONTEXT, c) for c in (context or ())),
            *part(ContentRole.REFERENCE, given.get("reference"), "reference"),
            *part(ContentRole.INSTRUCTIONS, requirements, "requirements"),
            *part(ContentRole.TASK_EVIDENCE, given.get("evidence"), "evidence"),
        )
        return EvaluationRequest(CHECKS[check][1], parts)

    def _verdict(
        self,
        check: str,
        disposition: EvaluationDisposition,
        box: list[JudgeInvocationReport],
    ) -> SemanticVerdict:
        indicator = self._checks.indicator(check)
        report = next((r for r in reversed(box) if r.indicator == indicator), None)
        if (
            disposition
            in (
                EvaluationDisposition.SKIPPED_UNSAMPLED,
                EvaluationDisposition.SKIPPED_RUN_NOT_RECORDING,
                EvaluationDisposition.SKIPPED_BY_ADMISSION,
            )
            or report is None
        ):
            return SemanticVerdict(
                check, indicator, SemanticStatus.SKIPPED, None, None, None, disposition
            )
        common: dict[str, Any] = {
            "latency_ms": report.latency_ms,
            "attempts": report.attempts,
            "input_tokens": report.input_tokens,
            "output_tokens": report.output_tokens,
        }
        if report.kind == "failure" or report.outcome is None:
            return SemanticVerdict(
                check,
                indicator,
                SemanticStatus.EVALUATOR_FAILURE,
                None,
                None,
                # A check still in flight when its scope drained is reported as
                # "cancelled" with no class; the platform records it as a timeout.
                report.exception_type or "JudgeTimeoutError",
                disposition,
                **common,
            )
        status = (
            SemanticStatus.UNKNOWN
            if report.outcome is EvaluationOutcome.UNKNOWN
            else SemanticStatus.DETERMINATE
        )
        return SemanticVerdict(
            check,
            indicator,
            status,
            report.outcome,
            report.reason_code,
            None,
            disposition,
            **common,
        )

    def check(
        self, check: str, answer: str, *, trusted: Sequence[str] = (), **given: Any
    ) -> SemanticVerdict:
        """Blocking evaluation (``SyncJudgeProvider``)."""
        if self._checks.is_async:
            raise TypeError("this SemanticChecks has an async provider: use acheck()")
        request = self._request(check, answer, given, trusted)
        box: list[JudgeInvocationReport] = []
        token = _box.set(box)
        try:
            disposition = self._inner.evaluate_sync(
                self._checks.indicator(check), request
            )
        finally:
            _box.reset(token)
        return self._verdict(check, disposition, box)

    async def acheck(
        self, check: str, answer: str, *, trusted: Sequence[str] = (), **given: Any
    ) -> SemanticVerdict:
        """Async evaluation (``JudgeProvider``); cancellation records nothing."""
        if not self._checks.is_async:
            raise TypeError("this SemanticChecks has a blocking provider: use check()")
        request = self._request(check, answer, given, trusted)
        box: list[JudgeInvocationReport] = []
        token = _box.set(box)
        try:
            disposition = await self._inner.evaluate(
                self._checks.indicator(check), request
            )
        finally:
            _box.reset(token)
        return self._verdict(check, disposition, box)

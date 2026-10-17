"""Shared judge control flow as a sans-IO generator (P29 S03/S04).

The engine yields what must happen (``CallProvider``, ``Sleep``) and receives
what happened (``Replied``, ``Raised``, ``Slept``). The async and sync drivers
perform the I/O and the time accounting; every decision (retries, re-asks,
budget, deadline, classification, mapping) lives here once, which makes
sync/async parity structural.

Privacy rules enforced here: failures are always *new* constant-message
exceptions raised outside any ``except`` block (so ``__context__`` is empty);
a provider exception is chained only when ``retain_cause`` is true.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Final

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation import EvaluationDecision
from agent_reliability.experimental.judge.budget import BudgetTracker
from agent_reliability.experimental.judge.core import (
    ParsedOutput,
    aggregate_repeats,
    build_prompt,
    draw_nonce,
    interpret_reply,
    map_verdict,
    precheck,
    select_parts,
    total_chars,
)
from agent_reliability.experimental.judge.errors import (
    JudgeError,
    JudgeInputLimitError,
    JudgeInvalidOutputError,
    JudgeProviderError,
    JudgeProviderRateLimitedError,
    JudgeProviderRefusedError,
    JudgeProviderUnavailableError,
    JudgeTimeoutError,
)
from agent_reliability.experimental.judge.provider import ProviderCall, ProviderReply
from agent_reliability.experimental.judge.rubric import Rubric
from agent_reliability.experimental.judge.values import (
    Confidence,
    ContentPart,
    ContentRole,
    EvaluationRequest,
    JudgeEvaluation,
    JudgeLimits,
    JudgePolicy,
    JudgeStats,
)

#: Smallest remaining time worth starting an attempt for (seconds).
MIN_ATTEMPT_SECONDS: Final = 0.001
#: Temperature requested from the provider (the provider may ignore it).
REQUESTED_TEMPERATURE: Final = 0.0

_RETRYABLE: Final = (
    JudgeTimeoutError,
    JudgeProviderUnavailableError,
    JudgeProviderRateLimitedError,
)


@dataclass(frozen=True, slots=True)
class CallProvider:
    call: ProviderCall


@dataclass(frozen=True, slots=True)
class Sleep:
    seconds: float


@dataclass(frozen=True, slots=True)
class Replied:
    reply: object


@dataclass(frozen=True, slots=True)
class Raised:
    exc: Exception


class Slept:
    """Marker response to :class:`Sleep`."""


SLEPT: Final = Slept()

Action = CallProvider | Sleep
Response = Replied | Raised | Slept


def classify_provider_exception(exc: Exception) -> JudgeError:
    """Map whatever a provider raised to a fresh constant-message JudgeError."""
    if isinstance(exc, JudgeError):
        if isinstance(exc, JudgeProviderRateLimitedError):
            return JudgeProviderRateLimitedError(exc.retry_after_seconds)
        if isinstance(exc, JudgeTimeoutError):
            return JudgeTimeoutError()
        if isinstance(exc, JudgeProviderUnavailableError):
            return JudgeProviderUnavailableError()
        if isinstance(exc, JudgeProviderRefusedError):
            return JudgeProviderRefusedError()
        return JudgeProviderError()
    if isinstance(exc, TimeoutError):
        return JudgeTimeoutError()
    return JudgeProviderError()


class _Counters:
    __slots__ = ("attempts", "input_tokens", "output_tokens", "repairs")

    def __init__(self) -> None:
        self.attempts = 0
        self.repairs = 0
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None


class JudgeEngine:
    """Immutable configuration plus the control-flow generator."""

    def __init__(
        self,
        *,
        rubric: Rubric,
        min_confidence: Confidence,
        policy: JudgePolicy,
        limits: JudgeLimits,
        tracker: BudgetTracker | None,
        retain_cause: bool,
        nonce_source: Callable[[], str] | None,
        jitter: Callable[[], float],
    ) -> None:
        self._rubric = rubric
        self._min_confidence = min_confidence
        self._policy = policy
        self._limits = limits
        self._tracker = tracker
        self._retain_cause = retain_cause
        self._nonce_source = nonce_source
        self._jitter = jitter

    # The generator is the evaluation. ``now`` is the driver's monotonic clock.
    def run(
        self, request: EvaluationRequest, now: Callable[[], float]
    ) -> Generator[Action, Response, JudgeEvaluation]:
        if not isinstance(request, EvaluationRequest):
            raise TypeError("value must be an EvaluationRequest")
        if request.dimension != self._rubric.dimension:
            raise ValueError("request dimension does not match the rubric")
        started = now()
        counters = _Counters()
        try:
            return (yield from self._evaluate(request, now, started, counters))
        except JudgeError as err:
            err.stats = self._stats(counters, now, started)
            raise

    def _stats(
        self, counters: _Counters, now: Callable[[], float], started: float
    ) -> JudgeStats:
        return JudgeStats(
            attempts=counters.attempts,
            repairs=counters.repairs,
            input_tokens=counters.input_tokens,
            output_tokens=counters.output_tokens,
            latency_ms=max(0, int((now() - started) * 1000)),
        )

    def _evaluate(
        self,
        request: EvaluationRequest,
        now: Callable[[], float],
        started: float,
        counters: _Counters,
    ) -> Generator[Action, Response, JudgeEvaluation]:
        rubric = self._rubric
        dimension = rubric.dimension.value
        selected = select_parts(rubric, request.parts)
        missing_code = precheck(rubric, selected)
        if missing_code is not None:
            decision = EvaluationDecision(
                EvaluationOutcome.UNKNOWN, f"{dimension}.{missing_code}"
            )
            return JudgeEvaluation(decision, self._stats(counters, now, started))
        if total_chars(selected) > self._limits.max_input_chars:
            raise JudgeInputLimitError
        context_count = sum(1 for p in selected if p.role is ContentRole.CONTEXT)
        deadline_at = started + self._limits.evaluation_deadline_seconds
        decisions: list[EvaluationDecision] = []
        reason_text: str | None = None
        confidences: list[Confidence] = []
        for _ in range(self._policy.repeats):
            parsed = yield from self._one_judgment(
                selected, context_count, deadline_at, now, counters
            )
            decisions.append(map_verdict(parsed, dimension, self._min_confidence))
            confidences.append(parsed.confidence)
            if reason_text is None and self._policy.capture_reason:
                reason_text = parsed.reason
        decision = (
            decisions[0]
            if len(decisions) == 1
            else aggregate_repeats(decisions, dimension)
        )
        return JudgeEvaluation(
            decision,
            self._stats(counters, now, started),
            reason_text,
            min(confidences, key=lambda c: c.rank),
        )

    def _one_judgment(
        self,
        selected: tuple[ContentPart, ...],
        context_count: int,
        deadline_at: float,
        now: Callable[[], float],
        counters: _Counters,
    ) -> Generator[Action, Response, ParsedOutput]:
        limits = self._limits
        transient_failures = 0
        repairs = 0
        repair_class: str | None = None
        while True:
            remaining = deadline_at - now()
            if remaining < MIN_ATTEMPT_SECONDS:
                raise JudgeTimeoutError
            if self._tracker is not None:
                self._tracker.check()
            nonce = draw_nonce(selected, self._nonce_source)
            prompt = build_prompt(
                self._rubric, selected, nonce=nonce, repair_error_class=repair_class
            )
            call = ProviderCall(
                system=prompt.system,
                user=prompt.user,
                max_output_tokens=limits.max_output_tokens,
                temperature=REQUESTED_TEMPERATURE,
                json_output=True,
                deadline_seconds=min(limits.provider_timeout_seconds, remaining),
            )
            counters.attempts += 1
            response = yield CallProvider(call)

            failure: JudgeError | None = None
            cause: Exception | None = None
            parsed: ParsedOutput | None = None
            if isinstance(response, Raised):
                failure = classify_provider_exception(response.exc)
                cause = response.exc
            elif isinstance(response, Replied):
                self._account(response.reply, counters)
                try:
                    parsed = interpret_reply(
                        response.reply, self._rubric, limits, context_count
                    )
                except JudgeError as err:
                    failure = err
            else:  # pragma: no cover - driver bug
                failure = JudgeProviderError()
            if parsed is not None:
                return parsed
            assert failure is not None

            if isinstance(failure, JudgeInvalidOutputError):
                if repairs < limits.repair_attempts:
                    repairs += 1
                    counters.repairs += 1
                    repair_class = failure.error_class
                    continue
            elif isinstance(failure, _RETRYABLE):
                transient_failures += 1
                if transient_failures < limits.max_attempts:
                    delay = self._backoff(transient_failures, failure)
                    left = deadline_at - now() - delay
                    if left >= MIN_ATTEMPT_SECONDS:
                        yield Sleep(delay)
                        continue
            # Terminal: raised outside any ``except`` block, no chained context.
            raise failure from (cause if self._retain_cause else None)

    def _backoff(self, failed_attempts: int, failure: JudgeError) -> float:
        ceiling = min(
            self._limits.retry_backoff_cap_seconds,
            0.25 * float(2 ** (failed_attempts - 1)),
        )
        draw = self._jitter()
        if (
            isinstance(draw, bool)
            or not isinstance(draw, (int, float))
            or not 0.0 <= draw <= 1.0
        ):
            raise ValueError("jitter must return a number in [0, 1]")
        delay = draw * ceiling
        if isinstance(failure, JudgeProviderRateLimitedError) and (
            failure.retry_after_seconds is not None
        ):
            delay = max(delay, failure.retry_after_seconds)
        return delay

    def _account(self, reply: object, counters: _Counters) -> None:
        if not isinstance(reply, ProviderReply):
            return
        if reply.input_tokens is not None:
            counters.input_tokens = (counters.input_tokens or 0) + reply.input_tokens
        if reply.output_tokens is not None:
            counters.output_tokens = (counters.output_tokens or 0) + reply.output_tokens
        if self._tracker is not None:
            self._tracker.record(reply.input_tokens, reply.output_tokens)

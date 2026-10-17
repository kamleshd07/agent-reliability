"""``JudgeCoordinator`` and ``EvaluationScope`` (P29 S05, P29-CON-13/13a/13b/14).

Concurrent judge *execution* is never concurrent *recording*: every call that
hands evidence to the shared ``RunHandle`` is made while holding the scope's one
recording gate (a ``threading.Lock``), which is held only around one synchronous
record call plus local bookkeeping. No ``await``, provider call or observer
callback runs while it is held; observer reports are emitted after release.
``RunHandle.record_*`` synchronously invokes the customer's sinks and diagnostic
handler inside the gate, so those components must be non-blocking.
"""

from __future__ import annotations

import asyncio
import collections
import enum
import inspect
import math
import threading
import time
import weakref
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation import (
    EvaluationExecutionFailure,
    EvaluationFailureStage,
    EvaluationResult,
    EvaluatorIdentity,
)
from agent_reliability.experimental.judge.errors import (
    JudgeError,
    JudgeOverloadedError,
    JudgeTimeoutError,
)
from agent_reliability.experimental.judge.judge import LLMJudge
from agent_reliability.experimental.judge.sync import SyncLLMJudge
from agent_reliability.experimental.judge.values import (
    EvaluationRequest,
    JudgeStats,
    SamplingPolicy,
)
from agent_reliability.sdk.context import RunHandle
from agent_reliability.sdk.evaluator_runner import EvaluatorRunner

__all__ = [
    "CoverageReport",
    "EvaluationDisposition",
    "EvaluationScope",
    "IndicatorBinding",
    "IndicatorCoverage",
    "JudgeCoordinator",
    "JudgeInvocationReport",
    "JudgeObserver",
]

ReportKind = Literal[
    "result", "failure", "skipped_unsampled", "skipped_run_not_recording", "cancelled"
]


class EvaluationDisposition(enum.Enum):
    RECORDED_RESULT = "recorded_result"
    RECORDED_FAILURE = "recorded_failure"
    SKIPPED_UNSAMPLED = "skipped_unsampled"
    SKIPPED_RUN_NOT_RECORDING = "skipped_run_not_recording"


@dataclass(frozen=True, slots=True)
class JudgeInvocationReport:
    """Content-free local report (never exported, P29-D08)."""

    indicator: str
    evaluator: EvaluatorIdentity
    kind: ReportKind
    outcome: EvaluationOutcome | None
    reason_code: str | None
    exception_type: str | None
    attempts: int
    repairs: int
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    queue_wait_ms: int
    reason_text: str | None = field(default=None, repr=False)
    #: For ``kind == "failure"``: whether the failure was handed to the handle
    #: together with its indicator (``None`` for other kinds). ``False`` means
    #: "failure evidence not delivered": local run health only (CON-13b).
    failure_evidence_delivered: bool | None = None


@runtime_checkable
class JudgeObserver(Protocol):
    """Local observer; ``on_report`` must not raise or block (errors are counted)."""

    def on_report(self, report: JudgeInvocationReport) -> None: ...


@dataclass(frozen=True, slots=True)
class IndicatorBinding:
    """``indicator -> evaluator`` (+ sampling). No registry, no import by string."""

    indicator: str
    evaluator: Any
    sampling: SamplingPolicy = field(default_factory=SamplingPolicy)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.indicator, str)
            or not 1 <= len(self.indicator) <= 200
            or any(ord(c) < 32 or ord(c) == 127 for c in self.indicator)
        ):
            raise ValueError("indicator must be 1-200 printable characters")
        if not isinstance(self.sampling, SamplingPolicy):
            raise TypeError("sampling must be a SamplingPolicy")
        evaluator = self.evaluator
        identity = getattr(evaluator, "identity", None)
        deterministic = getattr(evaluator, "deterministic", None)
        evaluate = getattr(evaluator, "evaluate", None)
        if (
            not isinstance(identity, EvaluatorIdentity)
            or type(deterministic) is not bool
            or not callable(evaluate)
        ):
            raise TypeError(
                "evaluator must expose identity, deterministic and evaluate"
            )
        if deterministic and _is_model_backed(evaluator):
            raise ValueError("a model-backed evaluator cannot be deterministic")
        if deterministic and self.indicator == "task-completion-evidence":
            raise ValueError(
                "task-completion-evidence is never an authoritative outcome and "
                "cannot use a deterministic evaluator"
            )

    @property
    def is_async(self) -> bool:
        return inspect.iscoroutinefunction(self.evaluator.evaluate)


def _is_model_backed(evaluator: object) -> bool:
    return isinstance(evaluator, (LLMJudge, SyncLLMJudge)) or (
        getattr(evaluator, "model_backed", False) is True
    )


# ---------------------------------------------------------------- coverage


@dataclass(frozen=True, slots=True)
class IndicatorCoverage:
    """Attempts versus determinate versus failed versus unknown versus unsampled.

    Reliability is shown only together with coverage and failure rate. There is
    deliberately no single "healthy" value: failures and UNKNOWN leave the
    reliability denominator (P29-CON-08a).
    """

    indicator: str
    attempted: int = 0
    passed: int = 0
    failed: int = 0
    unknown: int = 0
    execution_failures: int = 0
    failures_by_class: tuple[tuple[str, int], ...] = ()
    unsampled: int = 0
    skipped_run_not_recording: int = 0
    cancelled: int = 0
    late_discarded: int = 0
    provider_calls: int = 0

    @property
    def determinate(self) -> int:
        return self.passed + self.failed

    @property
    def reliability(self) -> float | None:
        return self.passed / self.determinate if self.determinate else None

    @property
    def determinate_rate(self) -> float | None:
        return self.determinate / self.attempted if self.attempted else None

    @property
    def failure_rate(self) -> float | None:
        return self.execution_failures / self.attempted if self.attempted else None

    @property
    def unknown_rate(self) -> float | None:
        return self.unknown / self.attempted if self.attempted else None

    def describe(self) -> str:
        def pct(value: float | None) -> str:
            return "n/a" if value is None else f"{value * 100:.1f}%"

        rel = "n/a" if self.reliability is None else f"{self.reliability:.3f}"
        return (
            f"{self.indicator}: reliability {rel} over {self.determinate} determinate "
            f"of {self.attempted} attempted (determinate {pct(self.determinate_rate)}, "
            f"execution failures {pct(self.failure_rate)}, unknown "
            f"{pct(self.unknown_rate)}); unsampled {self.unsampled}, skipped "
            f"{self.skipped_run_not_recording}, cancelled {self.cancelled}, "
            f"late discarded {self.late_discarded}"
        )


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Local, content-free snapshot of what the coordinator did. Not exported."""

    indicators: tuple[IndicatorCoverage, ...]
    observer_errors: int = 0
    failure_evidence_not_delivered: int = 0

    @property
    def total(self) -> IndicatorCoverage:
        merged: dict[str, int] = {}
        for item in self.indicators:
            for name, count in item.failures_by_class:
                merged[name] = merged.get(name, 0) + count
        return IndicatorCoverage(
            indicator="*",
            attempted=sum(i.attempted for i in self.indicators),
            passed=sum(i.passed for i in self.indicators),
            failed=sum(i.failed for i in self.indicators),
            unknown=sum(i.unknown for i in self.indicators),
            execution_failures=sum(i.execution_failures for i in self.indicators),
            failures_by_class=tuple(sorted(merged.items())),
            unsampled=sum(i.unsampled for i in self.indicators),
            skipped_run_not_recording=sum(
                i.skipped_run_not_recording for i in self.indicators
            ),
            cancelled=sum(i.cancelled for i in self.indicators),
            late_discarded=sum(i.late_discarded for i in self.indicators),
            provider_calls=sum(i.provider_calls for i in self.indicators),
        )

    def describe(self) -> str:
        lines = [i.describe() for i in self.indicators]
        lines.append(
            f"observer errors {self.observer_errors}; failure evidence not delivered "
            f"{self.failure_evidence_not_delivered}"
        )
        return "\n".join(lines)


class _Counters:
    def __init__(self, indicators: Sequence[str]) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = {
            i: {
                "attempted": 0,
                "passed": 0,
                "failed": 0,
                "unknown": 0,
                "execution_failures": 0,
                "by_class": {},
                "unsampled": 0,
                "skipped": 0,
                "cancelled": 0,
                "late": 0,
                "calls": 0,
            }
            for i in indicators
        }
        self.observer_errors = 0
        self.not_delivered = 0

    def count(self, report: JudgeInvocationReport, *, late: bool = False) -> None:
        with self._lock:
            d = self._data[report.indicator]
            d["calls"] += report.attempts
            if late:
                d["late"] += 1
                return
            if report.kind == "result":
                d["attempted"] += 1
                if report.outcome is EvaluationOutcome.PASS:
                    d["passed"] += 1
                elif report.outcome is EvaluationOutcome.FAIL:
                    d["failed"] += 1
                else:
                    d["unknown"] += 1
            elif report.kind == "failure":
                d["attempted"] += 1
                d["execution_failures"] += 1
                name = report.exception_type or "unknown"
                d["by_class"][name] = d["by_class"].get(name, 0) + 1
                if report.failure_evidence_delivered is False:
                    self.not_delivered += 1
            elif report.kind == "skipped_unsampled":
                d["unsampled"] += 1
            elif report.kind == "skipped_run_not_recording":
                d["skipped"] += 1
            elif report.kind == "cancelled":
                d["cancelled"] += 1

    def observer_error(self) -> None:
        with self._lock:
            self.observer_errors += 1

    def snapshot(self) -> CoverageReport:
        with self._lock:
            items = tuple(
                IndicatorCoverage(
                    indicator=name,
                    attempted=d["attempted"],
                    passed=d["passed"],
                    failed=d["failed"],
                    unknown=d["unknown"],
                    execution_failures=d["execution_failures"],
                    failures_by_class=tuple(sorted(d["by_class"].items())),
                    unsampled=d["unsampled"],
                    skipped_run_not_recording=d["skipped"],
                    cancelled=d["cancelled"],
                    late_discarded=d["late"],
                    provider_calls=d["calls"],
                )
                for name, d in self._data.items()
            )
            return CoverageReport(items, self.observer_errors, self.not_delivered)


# --------------------------------------------------------------- admission


class _Waiter:
    __slots__ = ("event", "future", "granted", "loop")

    def __init__(self, loop: asyncio.AbstractEventLoop | None) -> None:
        self.loop = loop
        self.future: asyncio.Future[None] | None = (
            loop.create_future() if loop is not None else None
        )
        self.event = threading.Event()
        self.granted = False

    def grant(self) -> None:
        self.granted = True
        if self.loop is not None and self.future is not None:
            future = self.future

            def _set() -> None:
                if not future.done():
                    future.set_result(None)

            self.loop.call_soon_threadsafe(_set)
        else:
            self.event.set()


class _Admission:
    """Thread- and task-safe FIFO semaphore with a bounded waiting queue."""

    def __init__(self, max_concurrency: int, max_pending: int) -> None:
        self._lock = threading.Lock()
        self._max_concurrency = max_concurrency
        self._max_pending = max_pending
        self._running = 0
        self._waiters: collections.deque[_Waiter] = collections.deque()

    def begin(
        self, loop: asyncio.AbstractEventLoop | None
    ) -> tuple[str, _Waiter | None]:
        with self._lock:
            if self._running < self._max_concurrency and not self._waiters:
                self._running += 1
                return "run", None
            if len(self._waiters) >= self._max_pending:
                return "shed", None
            waiter = _Waiter(loop)
            self._waiters.append(waiter)
            return "wait", waiter

    def release(self) -> None:
        with self._lock:
            if self._waiters:
                self._waiters.popleft().grant()  # hand the slot over
            else:
                self._running -= 1

    def abandon(self, waiter: _Waiter) -> None:
        """A waiting caller was cancelled: drop it or give back a granted slot."""
        with self._lock:
            granted = waiter.granted
            if not granted:
                self._waiters.remove(waiter)
        if granted:
            self.release()


# ----------------------------------------------------------------- scope


_CAPABILITY_CACHE: weakref.WeakKeyDictionary[type, bool] = weakref.WeakKeyDictionary()


def _supports_indicator(run: object) -> bool:
    cls = type(run)
    cached = _CAPABILITY_CACHE.get(cls)
    if cached is None:
        try:
            params = inspect.signature(cls.record_evaluation_failure).parameters  # type: ignore[attr-defined]
            cached = "indicator" in params
        except (AttributeError, TypeError, ValueError):
            cached = False
        _CAPABILITY_CACHE[cls] = cached
    return cached


@dataclass(slots=True)
class _Inflight:
    indicator: str
    identity: EvaluatorIdentity
    timed_out: bool = False
    task: asyncio.Task[Any] | None = None


class _StatsCapture:
    """Wraps an evaluator to capture content-free stats and the optional reason."""

    def __init__(self, evaluator: Any) -> None:
        self._evaluator = evaluator
        self.stats: JudgeStats | None = None
        self.reason_text: str | None = None
        detailed = getattr(evaluator, "evaluate_detailed", None)
        self._detailed = detailed if callable(detailed) else None

    @property
    def identity(self) -> EvaluatorIdentity:
        identity: EvaluatorIdentity = self._evaluator.identity
        return identity

    @property
    def deterministic(self) -> bool:
        deterministic: bool = self._evaluator.deterministic
        return deterministic

    def evaluate(self, value: Any) -> Any:
        if self._detailed is None:
            return self._evaluator.evaluate(value)
        try:
            result = self._detailed(value)
        except JudgeError as err:
            self.stats = err.stats
            raise
        self.stats = result.stats
        self.reason_text = result.reason_text
        return result.decision

    async def evaluate_async(self, value: Any) -> Any:
        if self._detailed is None:
            return await self._evaluator.evaluate(value)
        try:
            result = await self._detailed(value)
        except JudgeError as err:
            self.stats = err.stats
            raise
        self.stats = result.stats
        self.reason_text = result.reason_text
        return result.decision


class _AsyncAdapter:
    def __init__(self, capture: _StatsCapture) -> None:
        self._capture = capture

    @property
    def identity(self) -> EvaluatorIdentity:
        return self._capture.identity

    @property
    def deterministic(self) -> bool:
        return self._capture.deterministic

    async def evaluate(self, value: Any) -> Any:
        return await self._capture.evaluate_async(value)


class EvaluationScope:
    """Per-run evaluation scope: sync and async context manager.

    Use inside ``with sdk.run(...) as run`` and exit it before the run block
    ends; ``__exit__`` drains pending work (bounded), it never closes the run.
    """

    def __init__(self, coordinator: JudgeCoordinator, run: RunHandle) -> None:
        self._c = coordinator
        self._run = run
        self._gate = threading.Lock()  # the single recording gate (CON-13a)
        self._holder: int | None = None  # thread currently inside the gate
        self._cond = threading.Condition()
        self._state: Literal["new", "open", "closed"] = "new"
        self._seen: set[str] = set()
        self._inflight: dict[int, _Inflight] = {}
        self._first_error: BaseException | None = None
        self._supports_indicator = _supports_indicator(run)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Take the recording gate; refuse re-entry instead of deadlocking.

        ``RunHandle.record_*`` runs the customer's sink and diagnostic handler
        inside the gate. If such a callback calls back into the same scope on
        the same thread, waiting for the non-reentrant lock would hang forever,
        so that case raises ``RuntimeError`` (a documented programmer error).
        """
        me = threading.get_ident()
        if self._holder == me:
            raise RuntimeError(
                "re-entrant use of an evaluation scope from inside a recording "
                "callback (sinks and diagnostic handlers must not call the scope)"
            )
        with self._gate:
            self._holder = me
            try:
                yield
            finally:
                self._holder = None

    # -- context management -------------------------------------------------

    def __enter__(self) -> EvaluationScope:
        self._open()
        return self

    async def __aenter__(self) -> EvaluationScope:
        self._open()
        return self

    def _open(self) -> None:
        with self._locked():
            if self._state != "new":
                raise RuntimeError("scope can be entered once")
            self._state = "open"

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is not None and not issubclass(exc_type, Exception):
            self._abort()
            return
        deadline = time.monotonic() + self._c._drain_timeout
        with self._cond:
            while self._inflight:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self._cond.wait(left)
        self._finish_drain()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is not None and issubclass(exc_type, asyncio.CancelledError):
            await self._cancel_all(record=False)
            return
        if exc_type is not None and not issubclass(exc_type, Exception):
            self._abort()
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._c._drain_timeout
        while True:
            with self._cond:
                pending = [e.task for e in self._inflight.values() if e.task]
                remaining = bool(self._inflight)
            if not remaining:
                break
            left = deadline - loop.time()
            if left <= 0:
                break
            if pending:
                await asyncio.wait(pending, timeout=left)
            else:
                await asyncio.sleep(min(0.005, left))
        await self._cancel_all(record=True)
        error, self._first_error = self._first_error, None
        if error is not None and exc_type is None:
            raise error

    def _abort(self) -> None:
        with self._locked():
            self._state = "closed"

    async def _cancel_all(self, *, record: bool) -> None:
        with self._locked():
            entries = list(self._inflight.values())
            for entry in entries:
                entry.timed_out = record  # R19 (record) versus R17 (cancel: nothing)
        tasks = [e.task for e in entries if e.task is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if record:
            self._record_timeouts(entries)
        else:
            self._abort()
            with self._cond:
                self._inflight.clear()
                self._cond.notify_all()

    def _finish_drain(self) -> None:
        with self._locked():
            entries = list(self._inflight.values())
            for entry in entries:
                entry.timed_out = True
        self._record_timeouts(entries)

    def _record_timeouts(self, entries: list[_Inflight]) -> None:
        reports: list[JudgeInvocationReport] = []
        try:
            with self._locked():
                for entry in entries:
                    failure = EvaluationExecutionFailure(
                        identity=entry.identity,
                        stage=EvaluationFailureStage.EVALUATION,
                        exception_type=JudgeTimeoutError.__name__,
                    )
                    delivered = self._record_failure_locked(entry.indicator, failure)
                    reports.append(
                        self._failure_report(entry, failure, delivered, None, 0, 0)
                    )
                self._state = "closed"
        finally:
            with self._cond:
                for entry in entries:
                    self._inflight = {
                        k: v for k, v in self._inflight.items() if v is not entry
                    }
                self._cond.notify_all()
        for report in reports:
            self._c._emit(report)

    # -- public evaluation API ---------------------------------------------

    async def evaluate(
        self, indicator: str, request: EvaluationRequest
    ) -> EvaluationDisposition:
        prepared = self._prepare(indicator, request, want_async=True)
        if isinstance(prepared, EvaluationDisposition):
            return prepared
        return await self._run_async(prepared, request)

    def submit(self, indicator: str, request: EvaluationRequest) -> None:
        # Resolve the loop first: outside a running loop this raises before any
        # state (dedupe set, in-flight entry) is touched.
        loop = asyncio.get_running_loop()
        prepared = self._prepare(indicator, request, want_async=True)
        if isinstance(prepared, EvaluationDisposition):
            return
        entry = prepared[1]

        async def runner() -> None:
            try:
                await self._run_async(prepared, request)
            except asyncio.CancelledError:
                raise
            except BaseException as err:  # surfaced at scope exit
                with self._locked():
                    if self._first_error is None:
                        self._first_error = err

        entry.task = loop.create_task(runner())

    def evaluate_sync(
        self, indicator: str, request: EvaluationRequest
    ) -> EvaluationDisposition:
        prepared = self._prepare(indicator, request, want_async=False)
        if isinstance(prepared, EvaluationDisposition):
            return prepared
        return self._run_sync(prepared, request)

    # -- shared steps -------------------------------------------------------

    def _prepare(
        self, indicator: str, request: EvaluationRequest, *, want_async: bool
    ) -> EvaluationDisposition | tuple[IndicatorBinding, _Inflight, int]:
        binding = (
            self._c._bindings.get(indicator) if isinstance(indicator, str) else None
        )
        if binding is None:
            raise ValueError("indicator is not bound")
        if not isinstance(request, EvaluationRequest):
            raise TypeError("request must be an EvaluationRequest")
        rubric = getattr(binding.evaluator, "rubric", None)
        if rubric is not None and request.dimension != rubric.dimension:
            raise ValueError("request dimension does not match the evaluator rubric")
        if binding.is_async != want_async:
            raise TypeError(
                "use evaluate()/submit() for async evaluators and "
                "evaluate_sync() for sync evaluators"
            )
        identity: EvaluatorIdentity = binding.evaluator.identity
        skip: JudgeInvocationReport | None = None
        entry: _Inflight | None = None
        with self._locked():
            if self._state != "open":
                raise RuntimeError("evaluation scope is not open")
            if indicator in self._seen:
                raise ValueError("indicator was already evaluated in this scope")
            if len(self._seen) >= self._c._max_per_run:
                raise ValueError("max_evaluations_per_run exceeded")
            self._seen.add(indicator)
            run_id = self._run.run_id
            if run_id is None:
                skip = self._skip_report(
                    indicator, identity, "skipped_run_not_recording"
                )
            elif not binding.sampling.decide(run_id):
                skip = self._skip_report(indicator, identity, "skipped_unsampled")
            else:
                entry = _Inflight(indicator, identity)
                with self._cond:
                    self._inflight[id(entry)] = entry
        if skip is not None:
            self._c._emit(skip)
            return (
                EvaluationDisposition.SKIPPED_RUN_NOT_RECORDING
                if skip.kind == "skipped_run_not_recording"
                else EvaluationDisposition.SKIPPED_UNSAMPLED
            )
        assert entry is not None
        return binding, entry, 0

    @staticmethod
    def _skip_report(
        indicator: str, identity: EvaluatorIdentity, kind: ReportKind
    ) -> JudgeInvocationReport:
        return JudgeInvocationReport(
            indicator, identity, kind, None, None, None, 0, 0, None, None, 0, 0
        )

    def _failure_report(
        self,
        entry: _Inflight,
        failure: EvaluationExecutionFailure,
        delivered: bool,
        stats: JudgeStats | None,
        latency_ms: int,
        queue_ms: int,
    ) -> JudgeInvocationReport:
        return JudgeInvocationReport(
            entry.indicator,
            entry.identity,
            "failure",
            None,
            None,
            failure.exception_type,
            stats.attempts if stats else 0,
            stats.repairs if stats else 0,
            stats.input_tokens if stats else None,
            stats.output_tokens if stats else None,
            latency_ms,
            queue_ms,
            None,
            delivered,
        )

    def _record_failure_locked(
        self, indicator: str, failure: EvaluationExecutionFailure
    ) -> bool:
        """Caller holds the gate. Returns whether the indicator was delivered."""
        if self._supports_indicator:
            self._run.record_evaluation_failure(failure=failure, indicator=indicator)
            return True
        self._run.record_evaluation_failure(failure=failure)
        return False

    def _overloaded(self, entry: _Inflight) -> EvaluationExecutionFailure:
        return EvaluationExecutionFailure(
            identity=entry.identity,
            stage=EvaluationFailureStage.EVALUATION,
            exception_type=JudgeOverloadedError.__name__,
        )

    def _complete(
        self,
        entry: _Inflight,
        outcome: EvaluationResult | EvaluationExecutionFailure,
        capture: _StatsCapture | None,
        latency_ms: int,
        queue_ms: int,
    ) -> EvaluationDisposition:
        stats = capture.stats if capture else None
        report: JudgeInvocationReport
        late = False
        try:
            with self._locked():
                if entry.timed_out or self._state == "closed":
                    late = True
                    disposition = EvaluationDisposition.RECORDED_FAILURE
                    report = JudgeInvocationReport(
                        entry.indicator,
                        entry.identity,
                        "cancelled",
                        None,
                        None,
                        None,
                        stats.attempts if stats else 0,
                        stats.repairs if stats else 0,
                        stats.input_tokens if stats else None,
                        stats.output_tokens if stats else None,
                        latency_ms,
                        queue_ms,
                    )
                elif isinstance(outcome, EvaluationResult):
                    self._run.record_evaluation(
                        indicator=entry.indicator, result=outcome
                    )
                    disposition = EvaluationDisposition.RECORDED_RESULT
                    report = JudgeInvocationReport(
                        entry.indicator,
                        entry.identity,
                        "result",
                        outcome.outcome,
                        outcome.reason_code,
                        None,
                        stats.attempts if stats else 1,
                        stats.repairs if stats else 0,
                        stats.input_tokens if stats else None,
                        stats.output_tokens if stats else None,
                        latency_ms,
                        queue_ms,
                        capture.reason_text if capture else None,
                    )
                else:
                    delivered = self._record_failure_locked(entry.indicator, outcome)
                    disposition = EvaluationDisposition.RECORDED_FAILURE
                    report = self._failure_report(
                        entry, outcome, delivered, stats, latency_ms, queue_ms
                    )
        finally:
            with self._cond:
                self._inflight.pop(id(entry), None)
                self._cond.notify_all()
        self._c._emit(report, late=late)
        return disposition

    def _cancelled(self, entry: _Inflight, queue_ms: int) -> None:
        with self._cond:
            self._inflight.pop(id(entry), None)
            self._cond.notify_all()
        if entry.timed_out:
            return  # drain converts it to JudgeTimeoutError evidence (R19)
        self._c._emit(
            JudgeInvocationReport(
                entry.indicator,
                entry.identity,
                "cancelled",
                None,
                None,
                None,
                0,
                0,
                None,
                None,
                0,
                queue_ms,
            )
        )

    async def _run_async(
        self,
        prepared: tuple[IndicatorBinding, _Inflight, int],
        request: EvaluationRequest,
    ) -> EvaluationDisposition:
        binding, entry, _ = prepared
        adm = self._c._admission
        loop = asyncio.get_running_loop()
        t0 = time.monotonic()
        queue_ms = 0
        try:
            mode, waiter = adm.begin(loop)
            if mode == "shed":
                return self._complete(entry, self._overloaded(entry), None, 0, 0)
            if waiter is not None:
                assert waiter.future is not None
                try:
                    await waiter.future
                except asyncio.CancelledError:
                    adm.abandon(waiter)
                    raise
            queue_ms = int((time.monotonic() - t0) * 1000)
            capture = _StatsCapture(binding.evaluator)
            started = time.monotonic()
            try:
                outcome = await self._c._runner.evaluate_async(
                    _AsyncAdapter(capture), request
                )
            finally:
                adm.release()
            latency = int((time.monotonic() - started) * 1000)
        except asyncio.CancelledError:
            self._cancelled(entry, queue_ms)
            raise
        except BaseException:
            with self._cond:
                self._inflight.pop(id(entry), None)
                self._cond.notify_all()
            raise
        return self._complete(entry, outcome, capture, latency, queue_ms)

    def _run_sync(
        self,
        prepared: tuple[IndicatorBinding, _Inflight, int],
        request: EvaluationRequest,
    ) -> EvaluationDisposition:
        binding, entry, _ = prepared
        adm = self._c._admission
        t0 = time.monotonic()
        try:
            mode, waiter = adm.begin(None)
            if mode == "shed":
                return self._complete(entry, self._overloaded(entry), None, 0, 0)
            if waiter is not None:
                try:
                    waiter.event.wait()
                except BaseException:
                    adm.abandon(waiter)  # never leave a dead waiter holding a slot
                    raise
            queue_ms = int((time.monotonic() - t0) * 1000)
            capture = _StatsCapture(binding.evaluator)
            started = time.monotonic()
            try:
                outcome = self._c._runner.evaluate(capture, request)
            finally:
                adm.release()
            latency = int((time.monotonic() - started) * 1000)
        except BaseException:
            with self._cond:
                self._inflight.pop(id(entry), None)
                self._cond.notify_all()
            raise
        return self._complete(entry, outcome, capture, latency, queue_ms)


class JudgeCoordinator:
    """Binds indicators to evaluators and runs them in per-run scopes."""

    def __init__(
        self,
        bindings: Sequence[IndicatorBinding],
        *,
        runner: EvaluatorRunner | None = None,
        max_concurrency: int = 4,
        max_pending: int = 64,
        max_evaluations_per_run: int = 16,
        drain_timeout_seconds: float = 60.0,
        observer: JudgeObserver | None = None,
    ) -> None:
        if not bindings or not all(isinstance(b, IndicatorBinding) for b in bindings):
            raise TypeError("bindings must be a non-empty sequence of IndicatorBinding")
        names = [b.indicator for b in bindings]
        if len(set(names)) != len(names):
            raise ValueError("binding indicators must be unique")
        for value, name, low, high in (
            (max_concurrency, "max_concurrency", 1, 64),
            (max_pending, "max_pending", 1, 10_000),
            (max_evaluations_per_run, "max_evaluations_per_run", 1, 64),
        ):
            if type(value) is not int:
                raise TypeError(f"{name} must be an int")
            if not low <= value <= high:
                raise ValueError(f"{name} must be {low}..{high}")
        if (
            isinstance(drain_timeout_seconds, bool)
            or not isinstance(drain_timeout_seconds, (int, float))
            or not math.isfinite(drain_timeout_seconds)
            or drain_timeout_seconds <= 0
        ):
            raise ValueError("drain_timeout_seconds must be a positive finite number")
        if runner is not None and not isinstance(runner, EvaluatorRunner):
            raise TypeError("runner must be an EvaluatorRunner")
        if observer is not None and not callable(getattr(observer, "on_report", None)):
            raise TypeError("observer must implement JudgeObserver")
        self._bindings = {b.indicator: b for b in bindings}
        self._runner = runner if runner is not None else EvaluatorRunner()
        self._max_per_run = max_evaluations_per_run
        self._drain_timeout = float(drain_timeout_seconds)
        self._observer = observer
        self._admission = _Admission(max_concurrency, max_pending)
        self._counters = _Counters(names)

    def scope(self, run: RunHandle) -> EvaluationScope:
        if not isinstance(run, RunHandle) and not hasattr(run, "record_evaluation"):
            raise TypeError("run must be a RunHandle")
        return EvaluationScope(self, run)

    def coverage(self) -> CoverageReport:
        """Local attempts/determinate/failed/unknown/unsampled counters (SG-3, SG-5)."""
        return self._counters.snapshot()

    def _emit(self, report: JudgeInvocationReport, *, late: bool = False) -> None:
        self._counters.count(report, late=late)
        observer: Callable[[JudgeInvocationReport], None] | None = (
            self._observer.on_report if self._observer is not None else None
        )
        if observer is not None:
            try:
                observer(report)
            except Exception:
                self._counters.observer_error()

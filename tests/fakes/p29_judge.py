"""Shared helpers for the P29 experimental-judge tests (no network, no model)."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

from agent_reliability.experimental.judge import (
    ContentPart,
    ContentRole,
    ContentTrust,
    EvaluationRequest,
    JudgeBudgetExceededError,
    JudgeDimension,
    JudgeProviderError,
    JudgeProviderRateLimitedError,
    JudgeProviderRefusedError,
    JudgeProviderUnavailableError,
    JudgeTimeoutError,
    ProviderFinish,
    ProviderReply,
    Rubric,
)
from agent_reliability.experimental.judge.testing import HANG, judge_reply

T = TypeVar("T")

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "p29"
SECRET = "SECRET_DO_NOT_LEAK_P29_55731"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def named_rubrics() -> dict[str, Rubric]:
    docs = load_fixture("judge_output_vectors.json")["rubrics"]
    return {name: Rubric.from_dict(doc) for name, doc in docs.items()}


def request_from_document(document: dict[str, Any]) -> EvaluationRequest:
    parts = tuple(
        ContentPart(
            ContentRole(p["role"]),
            p["text"],
            ContentTrust(p["trust"]) if "trust" in p else None,
        )
        for p in document["parts"]
    )
    return EvaluationRequest(JudgeDimension(document["dimension"]), parts)


def grounded_request(
    answer: str = "An answer.",
    context: tuple[str, ...] = ("ctx zero", "ctx one"),
    question: str | None = "Q?",
) -> EvaluationRequest:
    parts: list[ContentPart] = []
    if question is not None:
        parts.append(ContentPart(ContentRole.QUESTION, question))
    parts.extend(ContentPart(ContentRole.CONTEXT, c) for c in context)
    parts.append(ContentPart(ContentRole.ANSWER, answer))
    return EvaluationRequest(JudgeDimension.GROUNDEDNESS, tuple(parts))


def correctness_request(
    answer: str = "An answer.", reference: str = "The reference."
) -> EvaluationRequest:
    return EvaluationRequest(
        JudgeDimension.ANSWER_CORRECTNESS,
        (
            ContentPart(ContentRole.REFERENCE, reference),
            ContentPart(ContentRole.ANSWER, answer),
        ),
    )


def good_reply() -> str:
    return judge_reply("pass", "supported_by_context", "high", [0])


def steps_from_vector(script: list[dict[str, Any]]) -> list[Any]:
    """Translate a ``failure_mapping_vectors.json`` script into FakeProvider steps."""
    steps: list[Any] = []
    for item in script:
        if "raise" in item:
            kind = item["raise"]
            if kind == "timeout":
                steps.append(JudgeTimeoutError())
            elif kind == "builtin_timeout":
                steps.append(TimeoutError("took too long " + SECRET))
            elif kind == "unavailable":
                steps.append(JudgeProviderUnavailableError())
            elif kind == "rate_limited":
                steps.append(
                    JudgeProviderRateLimitedError(item.get("retry_after_seconds"))
                )
            elif kind == "refused":
                steps.append(JudgeProviderRefusedError())
            elif kind == "provider":
                steps.append(JudgeProviderError())
            elif kind == "generic":
                steps.append(RuntimeError("provider blew up " + SECRET))
            elif kind == "budget_exceeded_from_provider":
                steps.append(JudgeBudgetExceededError())
            else:  # pragma: no cover - fixture bug
                raise AssertionError(kind)
        elif "reply_chars" in item:
            steps.append(ProviderReply(text="x" * item["reply_chars"]))
        else:
            steps.append(
                ProviderReply(
                    text=item["reply"],
                    finish=ProviderFinish(item.get("finish", "stop")),
                )
            )
    return steps


class VirtualClockLoop(asyncio.SelectorEventLoop):
    """Event loop whose clock jumps instead of sleeping (deterministic timing)."""

    def __init__(self) -> None:
        super().__init__()
        self._virtual_now = 0.0
        real_select = self._selector.select  # type: ignore[attr-defined]

        def virtual_select(timeout: float | None = None) -> Any:
            if timeout is not None and timeout > 0:
                self._virtual_now += timeout
            return real_select(0)

        self._selector.select = virtual_select  # type: ignore[attr-defined,method-assign]

    def time(self) -> float:
        return self._virtual_now


def run_virtual(
    factory: Callable[[], Awaitable[T]], guard: float = 3600.0
) -> tuple[T, float]:
    """Run a coroutine on a virtual-clock loop; return ``(result, virtual_seconds)``."""

    async def main() -> tuple[T, float]:
        loop = asyncio.get_running_loop()
        start = loop.time()
        try:
            # Bounded guard in *virtual* seconds: a regression that removes a
            # timeout fails here instead of hanging the suite.
            result = await asyncio.wait_for(factory(), guard)  # type: ignore[arg-type]
        except TimeoutError:
            raise AssertionError(
                "virtual-time guard exceeded: unbounded wait"
            ) from None
        return result, loop.time() - start

    with asyncio.Runner(loop_factory=VirtualClockLoop) as runner:
        return runner.run(main())


class FakeMonotonic:
    """Manually advanced monotonic clock for the sync driver."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class HealthSink:
    """EventSink + HealthEvidenceSink spy that detects overlapping calls."""

    def __init__(self, delay: float = 0.0) -> None:
        self.events: list[Any] = []
        self.failures: list[tuple[str, str, str]] = []
        self.health: list[Any] = []
        self.overlaps = 0
        self.released: list[str] = []
        self._active = 0
        self._delay = delay
        self._lock = threading.Lock()

    def _enter(self) -> None:
        with self._lock:
            if self._active:
                self.overlaps += 1
            self._active += 1
        if self._delay:
            time.sleep(self._delay)

    def _exit(self) -> None:
        with self._lock:
            self._active -= 1

    def emit(self, event: Any) -> None:
        self._enter()
        try:
            self.events.append(event)
        finally:
            self._exit()

    def submit_evaluation_failure(
        self, failure: Any, *, run_id: str, indicator: str, **_: Any
    ) -> None:
        self._enter()
        try:
            self.failures.append((run_id, indicator, failure.exception_type))
        finally:
            self._exit()

    def submit_measurement_health(self, report: Any, *, run_id: str, **_: Any) -> None:
        self.health.append(report)

    def release_run(self, run_id: str) -> None:
        self.released.append(run_id)


class OverlapHandle:
    """Wraps a RunHandle and counts overlapping record calls and calls after close."""

    def __init__(self, inner: Any, delay: float = 0.0) -> None:
        self._inner = inner
        self._delay = delay
        self._lock = threading.Lock()
        self._active = 0
        self.overlaps = 0
        self.calls = 0
        self.closed = False
        self.calls_after_close = 0
        self.holders: set[int] = set()
        self.first_record = threading.Event()

    @property
    def run_id(self) -> str | None:
        rid: str | None = self._inner.run_id
        return rid

    @property
    def measurement_health(self) -> Any:
        return self._inner.measurement_health

    def _guard(self) -> None:
        with self._lock:
            if self._active:
                self.overlaps += 1
            self._active += 1
            self.calls += 1
            self.holders.add(threading.get_ident())
            self.first_record.set()
            if self.closed:
                self.calls_after_close += 1
        if self._delay:
            time.sleep(self._delay)

    def _release(self) -> None:
        with self._lock:
            self._active -= 1
            self.holders.discard(threading.get_ident())

    def record_evaluation(self, *, indicator: str, result: Any) -> None:
        self._guard()
        try:
            self._inner.record_evaluation(indicator=indicator, result=result)
        finally:
            self._release()

    def record_evaluation_failure(
        self, *, failure: Any, indicator: str | None = None
    ) -> None:
        self._guard()
        try:
            self._inner.record_evaluation_failure(failure=failure, indicator=indicator)
        finally:
            self._release()


class LegacyHandle:
    """A handle whose failure recording has no ``indicator`` (SDK 1.2.1 shape)."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.failure_calls: list[Any] = []

    @property
    def run_id(self) -> str | None:
        rid: str | None = self._inner.run_id
        return rid

    def record_evaluation(self, *, indicator: str, result: Any) -> None:
        self._inner.record_evaluation(indicator=indicator, result=result)

    def record_evaluation_failure(self, *, failure: Any) -> None:
        self.failure_calls.append(failure)
        self._inner.record_evaluation_failure(failure=failure)


__all__ = [
    "FIXTURE_DIR",
    "HANG",
    "SECRET",
    "FakeMonotonic",
    "HealthSink",
    "LegacyHandle",
    "OverlapHandle",
    "VirtualClockLoop",
    "correctness_request",
    "good_reply",
    "grounded_request",
    "load_fixture",
    "named_rubrics",
    "request_from_document",
    "run_virtual",
    "steps_from_vector",
]

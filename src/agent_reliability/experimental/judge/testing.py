"""Scripted fake providers for tests and examples (P29 S03 testing helper).

No network, no model. Each script step is consumed once per provider call:

* ``str`` -> a ``ProviderReply`` with that text;
* ``ProviderReply`` -> returned as is;
* ``Exception`` instance -> raised;
* ``HANG`` -> never completes (async only; use with a timeout);
* a callable ``fn(call)`` -> its return value is used as a step (may be a
  coroutine for the async provider); lets a test advance a fake clock.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import threading
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from agent_reliability.experimental.judge.provider import (
    ProviderCall,
    ProviderReply,
)

__all__ = ["HANG", "FakeProvider", "FakeSyncProvider", "judge_reply"]


class _Hang:
    def __repr__(self) -> str:
        return "HANG"


#: Script step that never completes.
HANG = _Hang()


def judge_reply(
    verdict: str = "pass",
    code: str = "consistent_with_reference",
    confidence: str = "high",
    citations: Sequence[int] = (),
    reason: str | None = None,
) -> str:
    """Build a valid ``gentlity.judge-output/1`` document as reply text."""
    doc: dict[str, Any] = {
        "schema": "gentlity.judge-output/1",
        "verdict": verdict,
        "code": code,
        "confidence": confidence,
        "citations": list(citations),
    }
    if reason is not None:
        doc["reason"] = reason
    return json.dumps(doc, separators=(",", ":"))


class _Scripted:
    reports_tokens = False

    def __init__(
        self,
        script: Iterable[Any],
        *,
        provider_label: str = "fake",
        reports_tokens: bool = False,
    ) -> None:
        self._steps = list(script)
        self._lock = threading.Lock()
        self._label = provider_label
        self.reports_tokens = reports_tokens
        self.calls: list[ProviderCall] = []

    @property
    def provider_label(self) -> str:
        return self._label

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def _next(self, call: ProviderCall) -> Any:
        with self._lock:
            self.calls.append(call)
            if not self._steps:
                raise AssertionError("FakeProvider script exhausted")
            return self._steps.pop(0)


def _materialize(step: Any) -> ProviderReply:
    if isinstance(step, BaseException):
        raise step
    if isinstance(step, ProviderReply):
        return step
    if isinstance(step, str):
        return ProviderReply(text=step)
    raise AssertionError("unsupported FakeProvider step")


class FakeProvider(_Scripted):
    """Async scripted provider."""

    async def complete(self, call: ProviderCall) -> ProviderReply:
        step = self._next(call)
        if callable(step) and not isinstance(step, (str, ProviderReply, BaseException)):
            step = step(call)
            if inspect.isawaitable(step):
                step = await step
        if step is HANG:
            await asyncio.Event().wait()
        return _materialize(step)


class FakeSyncProvider(_Scripted):
    """Blocking scripted provider (a callable step may advance a fake clock)."""

    def complete(self, call: ProviderCall) -> ProviderReply:
        step = self._next(call)
        if callable(step) and not isinstance(step, (str, ProviderReply, BaseException)):
            step = step(call)
        if step is HANG:
            raise AssertionError("HANG is not supported by FakeSyncProvider")
        return _materialize(step)


def fixed_nonces(values: Iterable[str]) -> Callable[[], str]:
    """A nonce source returning the given values in order (last one repeats)."""
    items = list(values)

    def source() -> str:
        return items.pop(0) if len(items) > 1 else items[0]

    return source

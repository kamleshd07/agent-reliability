"""Optional executor driver for stuck sync providers (P29 S07).

``ExecutorSyncProvider`` runs a blocking provider call in a daemon helper thread
and gives up after the call deadline: the caller receives ``JudgeTimeoutError``
and the late result is discarded (it can never mutate a terminal state). The
number of helper threads that may exist at once is bounded; beyond the bound the
call fails fast with ``JudgeProviderUnavailableError`` rather than creating
another thread. Daemon threads never keep the process alive. A thread that is
blocked inside the provider cannot be interrupted and lives until the provider
itself returns (modelled on the P28 helper rule in docs/HTTP_EXPORTER.md).
"""

from __future__ import annotations

import threading

from agent_reliability.experimental.judge.errors import (
    JudgeProviderUnavailableError,
    JudgeTimeoutError,
)
from agent_reliability.experimental.judge.provider import (
    ProviderCall,
    ProviderReply,
    SyncJudgeProvider,
)

__all__ = ["ExecutorSyncProvider"]


class _Slot:
    __slots__ = ("abandoned", "done", "error", "reply")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.abandoned = False
        self.reply: ProviderReply | None = None
        self.error: Exception | None = None


class ExecutorSyncProvider:
    def __init__(self, inner: SyncJudgeProvider, *, max_threads: int = 4) -> None:
        if type(max_threads) is not int or not 1 <= max_threads <= 64:
            raise ValueError("max_threads must be an int in 1..64")
        if not callable(getattr(inner, "complete", None)):
            raise TypeError("inner must implement SyncJudgeProvider")
        self._inner = inner
        self._max = max_threads
        self._lock = threading.Lock()
        self._live = 0
        self.reports_tokens = getattr(inner, "reports_tokens", False) is True

    @property
    def provider_label(self) -> str:
        label: str = self._inner.provider_label
        return label

    @property
    def live_threads(self) -> int:
        with self._lock:
            return self._live

    def complete(self, call: ProviderCall) -> ProviderReply:
        with self._lock:
            if self._live >= self._max:
                at_bound = True
            else:
                at_bound = False
                self._live += 1
        if at_bound:
            raise JudgeProviderUnavailableError
        slot = _Slot()

        def work() -> None:
            try:
                slot.reply = self._inner.complete(call)
            except Exception as exc:
                slot.error = exc
            finally:
                with self._lock:
                    self._live -= 1
                slot.done.set()

        thread = threading.Thread(
            target=work, name="judge-provider-helper", daemon=True
        )
        thread.start()
        finished = slot.done.wait(call.deadline_seconds)
        if not finished:
            slot.abandoned = True
            raise JudgeTimeoutError
        if slot.error is not None:
            error = slot.error
            slot.error = None
            raise error
        reply = slot.reply
        assert reply is not None
        return reply

    def __repr__(self) -> str:
        return f"ExecutorSyncProvider(max_threads={self._max})"

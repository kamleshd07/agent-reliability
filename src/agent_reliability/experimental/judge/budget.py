"""Thread- and task-safe sliding-window budget accounting (P29-CON-11).

Counts only provider-reported tokens; there is no estimation by characters.
Per-second buckets bound memory by ``window_seconds`` entries.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from decimal import Decimal

from agent_reliability.experimental.judge.errors import JudgeBudgetExceededError
from agent_reliability.experimental.judge.values import JudgeBudget

__all__ = ["BudgetTracker"]


class BudgetTracker:
    """Shared mutable accounting for one :class:`JudgeBudget`.

    Pass the same tracker to several judges to share one budget window.
    ``check`` is made before every provider call; in-flight calls are not
    interruptible, so the overshoot is bounded by concurrency times the
    per-call caps (documented, not measured).
    """

    def __init__(
        self, budget: JudgeBudget, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        if not isinstance(budget, JudgeBudget):
            raise TypeError("budget must be a JudgeBudget")
        self._budget = budget
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: dict[int, tuple[int, Decimal]] = {}

    @property
    def budget(self) -> JudgeBudget:
        return self._budget

    def _prune(self, now: float) -> None:
        horizon = int(now) - self._budget.window_seconds
        for key in [k for k in self._buckets if k <= horizon]:
            del self._buckets[key]

    def totals(self) -> tuple[int, Decimal]:
        """Return ``(tokens, cost)`` currently inside the window."""
        with self._lock:
            self._prune(self._clock())
            tokens = sum(t for t, _ in self._buckets.values())
            cost = sum((c for _, c in self._buckets.values()), Decimal(0))
            return tokens, cost

    def check(self) -> None:
        """Raise ``JudgeBudgetExceededError`` once a window total reached its limit."""
        tokens, cost = self.totals()
        limit_tokens = self._budget.max_tokens_per_window
        limit_cost = self._budget.max_cost_per_window
        if limit_tokens is not None and tokens >= limit_tokens:
            raise JudgeBudgetExceededError
        if limit_cost is not None and cost >= limit_cost:
            raise JudgeBudgetExceededError

    def record(self, input_tokens: int | None, output_tokens: int | None) -> None:
        """Account provider-reported usage; unreported counts add nothing."""
        tin = input_tokens or 0
        tout = output_tokens or 0
        if tin == 0 and tout == 0:
            return
        cost = Decimal(0)
        price_in = self._budget.input_price_per_1k_tokens
        price_out = self._budget.output_price_per_1k_tokens
        if price_in is not None:
            cost += Decimal(tin) / Decimal(1000) * price_in
        if price_out is not None:
            cost += Decimal(tout) / Decimal(1000) * price_out
        with self._lock:
            now = self._clock()
            self._prune(now)
            key = int(now)
            old_tokens, old_cost = self._buckets.get(key, (0, Decimal(0)))
            self._buckets[key] = (old_tokens + tin + tout, old_cost + cost)

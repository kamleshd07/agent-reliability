from __future__ import annotations

from datetime import UTC, datetime, timedelta


class FakeClock:
    """A deterministic clock: each call to ``now()`` advances by a fixed
    step from a fixed start, so tests never depend on real wall-clock
    timing and never need to sleep."""

    def __init__(
        self, start: datetime | None = None, step: timedelta = timedelta(seconds=1)
    ) -> None:
        self._current = start if start is not None else datetime(2026, 1, 1, tzinfo=UTC)
        self._step = step

    def now(self) -> datetime:
        value = self._current
        self._current = self._current + self._step
        return value


class BrokenClock:
    """A clock that always raises — for failure-isolation tests."""

    def now(self) -> datetime:
        raise RuntimeError("clock is broken")

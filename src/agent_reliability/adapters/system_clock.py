"""The default ``Clock`` implementation."""

from __future__ import annotations

from datetime import UTC, datetime

__all__ = ["SystemClock"]


class SystemClock:
    """Reads the real system clock, normalized to UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)

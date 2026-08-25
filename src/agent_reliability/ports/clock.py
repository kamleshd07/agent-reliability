"""The clock port.

M1 deliberately never reads the wall clock internally (ADR-0002); this
is the layer that does, behind a replaceable interface, so runtime code
never calls ``datetime.now()`` directly and tests never depend on real
wall-clock time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

__all__ = ["Clock"]


@runtime_checkable
class Clock(Protocol):
    """A source of the current time.

    Implementations must return a timezone-aware ``datetime`` — the
    same requirement M1's ``AgentRun`` enforces on its timestamps
    (docs/DOMAIN_MODEL.md).
    """

    def now(self) -> datetime: ...

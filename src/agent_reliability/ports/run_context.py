"""Optional bridge for a context that surrounds one SDK run.

The port is deliberately narrower than a generic hook or plugin API.  Its
paired lifetime lets an adapter make external instrumentation current while
application code executes, then restore the previous context reliably.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_reliability.domain import AgentRun, RunStatus

__all__ = ["RunContextBridge", "RunContextScope"]


@runtime_checkable
class RunContextScope(Protocol):
    """One active external context owned by one SDK run session."""

    def finish(self, *, status: RunStatus, exception_type: str | None) -> None: ...


@runtime_checkable
class RunContextBridge(Protocol):
    """Starts an external context for a fully initialized run."""

    def start(self, run: AgentRun) -> RunContextScope: ...

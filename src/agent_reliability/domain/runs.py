"""Agent run identity and lifecycle.

``AgentRun`` is a pure value object: the domain never generates its own
``run_id`` (no hidden ``uuid.uuid4()``) and never reads the wall clock
(no hidden ``datetime.now()``) during construction. Both are required,
caller-supplied arguments — id/time generation belongs to whichever
future layer actually needs randomness or clock access (the SDK, M2),
injected explicitly, so that an ``AgentRun`` remains reproducible pure
data (see ADR-0002 and docs/ENGINEERING_PRINCIPLES.md #2, #14).

``RunStatus`` is the minimal four-state lifecycle needed for M1's
invariants; a richer failure-cause taxonomy (e.g. distinguishing
timeout from other failure causes) is deferred — see
docs/DOMAIN_MODEL.md and ADR-0002.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import UTC, datetime

from agent_reliability.domain.identity import AgentIdentity

__all__ = ["AgentRun", "RunStatus"]


class RunStatus(enum.Enum):
    """Execution-level lifecycle status — NOT task success.

    A run can be ``COMPLETED`` (executed to completion) and still have
    failed the user's actual task; that is a separate ``EvaluationOutcome``,
    never derived from this status. See docs/DOMAIN_MODEL.md.
    """

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATUSES = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
)


def _require_timezone_aware_utc(value: datetime, field_name: str) -> datetime:
    """Reject naive datetimes; normalize aware ones to UTC.

    Never silently assumes a naive datetime means UTC — see
    docs/ENGINEERING_PRINCIPLES.md #14.
    """
    if value.tzinfo is None:
        raise ValueError(
            f"AgentRun.{field_name} must be timezone-aware; got a naive "
            "datetime. This project never assumes a naive timestamp means "
            "UTC — pass a timezone-aware value (e.g. datetime.now(UTC))."
        )
    return value.astimezone(UTC)


@dataclass(frozen=True)
class AgentRun:
    """One logical execution of an agent.

    Invariants (enforced in ``__post_init__``):

    - ``run_id`` is non-empty and caller-supplied (never generated here).
    - ``started_at`` (and ``ended_at``, if set) must be timezone-aware;
      both are normalized to UTC on construction.
    - ``ended_at``, if set, cannot precede ``started_at``.
    - ``status`` must be ``STARTED`` iff ``ended_at`` is ``None``, and a
      terminal status (``COMPLETED``/``FAILED``/``CANCELLED``) iff
      ``ended_at`` is set — a run cannot be simultaneously "still
      running" and "terminal," or vice versa.
    - ``parent_run_id``, if set, must not equal ``run_id``.
    """

    run_id: str
    agent: AgentIdentity
    started_at: datetime
    status: RunStatus
    ended_at: datetime | None = None
    parent_run_id: str | None = None

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("AgentRun.run_id must not be empty")

        normalized_started_at = _require_timezone_aware_utc(
            self.started_at, "started_at"
        )
        object.__setattr__(self, "started_at", normalized_started_at)

        if self.ended_at is not None:
            normalized_ended_at = _require_timezone_aware_utc(self.ended_at, "ended_at")
            object.__setattr__(self, "ended_at", normalized_ended_at)
            if normalized_ended_at < normalized_started_at:
                raise ValueError("AgentRun.ended_at cannot precede started_at")
            if self.status not in _TERMINAL_STATUSES:
                raise ValueError(
                    "a run with ended_at set must have a terminal status "
                    f"(COMPLETED/FAILED/CANCELLED), got {self.status}"
                )
        elif self.status is not RunStatus.STARTED:
            raise ValueError(
                f"a run without ended_at must have status STARTED, got {self.status}"
            )

        if self.parent_run_id is not None and self.parent_run_id == self.run_id:
            raise ValueError("AgentRun.parent_run_id must not equal its own run_id")

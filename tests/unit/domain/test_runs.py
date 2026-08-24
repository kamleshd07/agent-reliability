from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from agent_reliability.domain import AgentIdentity, AgentRun, RunStatus

AGENT = AgentIdentity(agent_id="a", name="A", version="1")
T0 = datetime(2026, 1, 1, tzinfo=UTC)
T1 = T0 + timedelta(minutes=5)


def test_in_progress_run_requires_started_status_and_no_ended_at() -> None:
    run = AgentRun(run_id="r1", agent=AGENT, started_at=T0, status=RunStatus.STARTED)
    assert run.ended_at is None
    assert run.status is RunStatus.STARTED


def test_terminal_run_requires_ended_at() -> None:
    run = AgentRun(
        run_id="r1", agent=AGENT, started_at=T0, status=RunStatus.COMPLETED, ended_at=T1
    )
    assert run.ended_at == T1


@pytest.mark.parametrize(
    "status", [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED]
)
def test_terminal_status_without_ended_at_is_rejected(status: RunStatus) -> None:
    with pytest.raises(ValueError, match="ended_at"):
        AgentRun(run_id="r1", agent=AGENT, started_at=T0, status=status)


def test_started_status_with_ended_at_is_rejected() -> None:
    with pytest.raises(ValueError, match="terminal status"):
        AgentRun(
            run_id="r1",
            agent=AGENT,
            started_at=T0,
            status=RunStatus.STARTED,
            ended_at=T1,
        )


def test_ended_at_before_started_at_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot precede"):
        AgentRun(
            run_id="r1",
            agent=AGENT,
            started_at=T1,
            status=RunStatus.COMPLETED,
            ended_at=T0,
        )


def test_ended_at_equal_to_started_at_is_allowed() -> None:
    run = AgentRun(
        run_id="r1", agent=AGENT, started_at=T0, status=RunStatus.COMPLETED, ended_at=T0
    )
    assert run.ended_at == run.started_at


def test_naive_started_at_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        AgentRun(
            run_id="r1",
            agent=AGENT,
            started_at=datetime(2026, 1, 1),  # naive
            status=RunStatus.STARTED,
        )


def test_naive_ended_at_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        AgentRun(
            run_id="r1",
            agent=AGENT,
            started_at=T0,
            status=RunStatus.COMPLETED,
            ended_at=datetime(2026, 1, 1, 0, 5),  # naive
        )


def test_non_utc_aware_timestamps_are_normalized_to_utc() -> None:
    plus_five = timezone(timedelta(hours=5))
    started_local = datetime(2026, 1, 1, 5, 0, tzinfo=plus_five)  # == T0 in UTC
    run = AgentRun(
        run_id="r1", agent=AGENT, started_at=started_local, status=RunStatus.STARTED
    )
    assert run.started_at == T0
    assert run.started_at.tzinfo == UTC


def test_empty_run_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="run_id"):
        AgentRun(run_id="", agent=AGENT, started_at=T0, status=RunStatus.STARTED)


def test_parent_run_id_may_differ_from_run_id() -> None:
    run = AgentRun(
        run_id="child",
        agent=AGENT,
        started_at=T0,
        status=RunStatus.STARTED,
        parent_run_id="parent",
    )
    assert run.parent_run_id == "parent"


def test_parent_run_id_equal_to_own_run_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="parent_run_id"):
        AgentRun(
            run_id="r1",
            agent=AGENT,
            started_at=T0,
            status=RunStatus.STARTED,
            parent_run_id="r1",
        )


def test_is_immutable() -> None:
    run = AgentRun(run_id="r1", agent=AGENT, started_at=T0, status=RunStatus.STARTED)
    with pytest.raises(AttributeError):
        run.status = RunStatus.FAILED  # type: ignore[misc]

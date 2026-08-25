from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent_reliability.domain import EvaluationOutcome, RunStatus
from agent_reliability.ports.events import EvaluationRecorded, RunFailed


class TestRunFailedValidation:
    def test_rejects_non_terminal_failure_status(self) -> None:
        with pytest.raises(ValueError, match="FAILED or"):
            RunFailed(
                run_id="r1",
                ended_at=datetime.now(UTC),
                status=RunStatus.STARTED,
                exception_type="ValueError",
            )

    def test_rejects_empty_exception_type(self) -> None:
        with pytest.raises(ValueError, match="exception_type"):
            RunFailed(
                run_id="r1",
                ended_at=datetime.now(UTC),
                status=RunStatus.FAILED,
                exception_type="",
            )

    def test_accepts_failed_and_cancelled(self) -> None:
        now = datetime.now(UTC)
        RunFailed(
            run_id="r1", ended_at=now, status=RunStatus.FAILED, exception_type="X"
        )
        RunFailed(
            run_id="r1", ended_at=now, status=RunStatus.CANCELLED, exception_type="X"
        )


def test_existing_evaluation_event_construction_remains_manual() -> None:
    event = EvaluationRecorded(
        "r1",
        "task_success",
        EvaluationOutcome.PASS,
        datetime.now(UTC),
    )
    assert event.provenance is None
    assert event.reason_code is None


def test_reason_code_without_provenance_is_rejected() -> None:
    with pytest.raises(ValueError, match="provenance"):
        EvaluationRecorded(
            "r1",
            "task_success",
            EvaluationOutcome.PASS,
            datetime.now(UTC),
            reason_code="manual_reason",
        )

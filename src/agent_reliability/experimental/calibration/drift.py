"""Deterministic, offline drift indicators (advisory; no significance claims).

Three indicators only: the fingerprint changed, the calibration expired, the dataset
went stale. Live decision-mix, failure-rate and error-rate shift indicators were
evaluated and deferred: production labels are unknown, so population or label shift
cannot be inferred from judge decisions, and no offline data can validate a threshold.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from agent_reliability.experimental.calibration.assessment import CalibrationAssessment
from agent_reliability.experimental.calibration.fingerprint import JudgeFingerprint
from agent_reliability.experimental.calibration.policy import CalibrationPolicy

__all__ = ["assess_drift"]


def assess_drift(
    assessment: CalibrationAssessment,
    current_fingerprint: JudgeFingerprint,
    policy: CalibrationPolicy,
    now: datetime,
) -> dict[str, Any]:
    """Return each indicator as ``clear`` or ``indicated`` with its evidence."""
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("now must be a timezone-aware datetime")
    now = now.astimezone(UTC)
    diff = assessment.fingerprint.diff(current_fingerprint)
    behavioural = [name for name in diff if name != "implementation_version"]
    age = now - assessment.created_at
    dataset_age = now - assessment.dataset_created_at
    return {
        "fingerprint_changed": {
            "state": "indicated" if behavioural else "clear",
            "differing_components": behavioural,
            "informational": [n for n in diff if n == "implementation_version"],
        },
        "calibration_expired": {
            "state": "indicated"
            if age > timedelta(days=policy.validity_days)
            else "clear",
            "age_days": round(age.total_seconds() / 86400, 3),
            "validity_days": policy.validity_days,
        },
        "dataset_stale": {
            "state": "indicated"
            if dataset_age > timedelta(days=policy.max_dataset_age_days)
            else "clear",
            "age_days": round(dataset_age.total_seconds() / 86400, 3),
            "max_dataset_age_days": policy.max_dataset_age_days,
        },
        "advisory": True,
        "deferred": [
            "decision_mix_shift",
            "failure_rate_shift",
            "error_rate_change",
        ],
    }

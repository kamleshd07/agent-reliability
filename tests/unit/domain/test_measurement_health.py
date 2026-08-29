from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from agent_reliability.measurement import (
    MeasurementHealth,
    MeasurementHealthReason,
    MeasurementHealthReport,
)


def test_healthy_is_the_canonical_empty_report() -> None:
    report = MeasurementHealthReport()
    assert report.health is MeasurementHealth.HEALTHY
    assert report.reasons == frozenset()


@pytest.mark.parametrize(
    ("reason", "health"),
    [
        (MeasurementHealthReason.EVENT_DELIVERY_FAILURE, MeasurementHealth.DEGRADED),
        (MeasurementHealthReason.PARTIAL_EVIDENCE, MeasurementHealth.DEGRADED),
        (
            MeasurementHealthReason.EVALUATOR_EXECUTION_FAILURE,
            MeasurementHealth.UNAVAILABLE,
        ),
        (
            MeasurementHealthReason.RUN_INITIALIZATION_FAILURE,
            MeasurementHealth.UNAVAILABLE,
        ),
    ],
)
def test_reason_has_exact_canonical_severity(
    reason: MeasurementHealthReason, health: MeasurementHealth
) -> None:
    report = MeasurementHealthReport.from_reasons(frozenset({reason}))
    assert report.health is health


def test_report_is_immutable_and_rejects_noncanonical_construction() -> None:
    report = MeasurementHealthReport()
    with pytest.raises(FrozenInstanceError):
        report.health = MeasurementHealth.DEGRADED  # type: ignore[misc]
    with pytest.raises(ValueError, match="match"):
        MeasurementHealthReport(
            MeasurementHealth.HEALTHY,
            frozenset({MeasurementHealthReason.EVENT_DELIVERY_FAILURE}),
        )
    with pytest.raises(TypeError, match="health"):
        MeasurementHealthReport("healthy", frozenset())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="frozenset"):
        MeasurementHealthReport(MeasurementHealth.HEALTHY, set())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="MeasurementHealthReason"):
        MeasurementHealthReport(
            MeasurementHealth.DEGRADED,
            frozenset({"unsafe"}),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="frozenset"):
        MeasurementHealthReport.from_reasons(set())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="MeasurementHealthReason"):
        MeasurementHealthReport.from_reasons(frozenset({"unsafe"}))  # type: ignore[arg-type]


def test_composition_is_monotonic_and_retains_bounded_reasons() -> None:
    degraded = MeasurementHealthReport.from_reasons(
        frozenset({MeasurementHealthReason.EVENT_DELIVERY_FAILURE})
    )
    unavailable = MeasurementHealthReport.from_reasons(
        frozenset({MeasurementHealthReason.PROVENANCE_UNAVAILABLE})
    )
    combined = degraded.combine(unavailable)
    assert combined.health is MeasurementHealth.UNAVAILABLE
    assert combined.reasons == degraded.reasons | unavailable.reasons
    with pytest.raises(TypeError, match="MeasurementHealthReport"):
        degraded.combine(object())  # type: ignore[arg-type]

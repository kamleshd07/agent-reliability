"""Application-owned bounded-degradation capability mapping."""

from __future__ import annotations

import enum

from agent_reliability.measurement import (
    MeasurementHealth,
    MeasurementHealthReason,
    MeasurementHealthReport,
)


class Capability(enum.StrEnum):
    FULL = "full"
    READ_ONLY = "read_only"
    SENSITIVE_DISABLED = "sensitive_disabled"


def decide(measurement_health: MeasurementHealthReport) -> Capability:
    """Map SDK health to this application's generic capability levels."""
    if measurement_health.health is MeasurementHealth.HEALTHY:
        return Capability.FULL
    if measurement_health.health is MeasurementHealth.DEGRADED:
        return Capability.READ_ONLY
    return Capability.SENSITIVE_DISABLED


def main() -> None:
    reports = [
        MeasurementHealthReport(),
        MeasurementHealthReport.from_reasons(
            frozenset({MeasurementHealthReason.PARTIAL_EVIDENCE})
        ),
        MeasurementHealthReport.from_reasons(
            frozenset({MeasurementHealthReason.RUN_INITIALIZATION_FAILURE})
        ),
    ]
    for report in reports:
        print(f"{report.health.value.upper()} -> {decide(report).value.upper()}")
    print("These capability choices belong to the application, not the SDK.")


if __name__ == "__main__":
    main()

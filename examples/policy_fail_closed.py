"""Application-owned fail-closed example for a sensitive capability."""

from __future__ import annotations

import enum

from agent_reliability.measurement import (
    MeasurementHealth,
    MeasurementHealthReason,
    MeasurementHealthReport,
)


class ApplicationDecision(enum.StrEnum):
    AUTHORIZE = "authorize"
    WITHHOLD = "withhold"


def decide(measurement_health: MeasurementHealthReport) -> ApplicationDecision:
    """The application requires healthy evidence for its sensitive action."""
    if measurement_health.health is MeasurementHealth.HEALTHY:
        return ApplicationDecision.AUTHORIZE
    return ApplicationDecision.WITHHOLD


def main() -> None:
    health = MeasurementHealthReport.from_reasons(
        frozenset({MeasurementHealthReason.EVENT_DELIVERY_FAILURE})
    )
    decision = decide(health)
    print(f"Measurement health: {health.health.value.upper()}")
    print(f"Application decision: {decision.value.upper()}")
    print("The application owns authorization; the SDK only reports health.")


if __name__ == "__main__":
    main()

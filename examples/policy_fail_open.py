"""Application-owned fail-open example for a low-criticality capability."""

from __future__ import annotations

import enum

from agent_reliability.measurement import (
    MeasurementHealthReason,
    MeasurementHealthReport,
)


class ApplicationDecision(enum.StrEnum):
    CONTINUE = "continue"


def decide(measurement_health: MeasurementHealthReport) -> ApplicationDecision:
    """The application chooses to continue for every health state."""
    return ApplicationDecision.CONTINUE


def main() -> None:
    health = MeasurementHealthReport.from_reasons(
        frozenset({MeasurementHealthReason.EVENT_DELIVERY_FAILURE})
    )
    decision = decide(health)
    print(f"Measurement health: {health.health.value.upper()}")
    print(f"Application decision: {decision.value.upper()}")
    print("This is application policy, not SDK policy.")


if __name__ == "__main__":
    main()

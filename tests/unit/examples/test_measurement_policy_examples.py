from __future__ import annotations

from examples.policy_bounded_degradation import Capability
from examples.policy_bounded_degradation import decide as bounded_decide
from examples.policy_fail_closed import ApplicationDecision as ClosedDecision
from examples.policy_fail_closed import decide as closed_decide
from examples.policy_fail_open import ApplicationDecision as OpenDecision
from examples.policy_fail_open import decide as open_decide

from agent_reliability.measurement import (
    MeasurementHealthReason,
    MeasurementHealthReport,
)

HEALTHY = MeasurementHealthReport()
DEGRADED = MeasurementHealthReport.from_reasons(
    frozenset({MeasurementHealthReason.PARTIAL_EVIDENCE})
)
UNAVAILABLE = MeasurementHealthReport.from_reasons(
    frozenset({MeasurementHealthReason.RUN_INITIALIZATION_FAILURE})
)


def test_fail_open_is_application_owned_for_every_sdk_health_state() -> None:
    assert [open_decide(report) for report in (HEALTHY, DEGRADED, UNAVAILABLE)] == [
        OpenDecision.CONTINUE,
        OpenDecision.CONTINUE,
        OpenDecision.CONTINUE,
    ]


def test_fail_closed_is_application_owned_for_every_sdk_health_state() -> None:
    assert [closed_decide(report) for report in (HEALTHY, DEGRADED, UNAVAILABLE)] == [
        ClosedDecision.AUTHORIZE,
        ClosedDecision.WITHHOLD,
        ClosedDecision.WITHHOLD,
    ]


def test_bounded_degradation_is_application_owned_for_every_health_state() -> None:
    assert [bounded_decide(report) for report in (HEALTHY, DEGRADED, UNAVAILABLE)] == [
        Capability.FULL,
        Capability.READ_ONLY,
        Capability.SENSITIVE_DISABLED,
    ]

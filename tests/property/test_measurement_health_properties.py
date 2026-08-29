from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from agent_reliability.measurement import (
    MeasurementHealth,
    MeasurementHealthReason,
    MeasurementHealthReport,
)

reports = st.sets(st.sampled_from(list(MeasurementHealthReason))).map(
    lambda reasons: MeasurementHealthReport.from_reasons(frozenset(reasons))
)


@given(reports, reports, reports)
def test_composition_is_associative_commutative_and_idempotent(
    first: MeasurementHealthReport,
    second: MeasurementHealthReport,
    third: MeasurementHealthReport,
) -> None:
    assert first.combine(second) == second.combine(first)
    assert first.combine(first) == first
    assert first.combine(second).combine(third) == first.combine(second.combine(third))


@given(reports, reports)
def test_composition_never_improves_health(
    first: MeasurementHealthReport, second: MeasurementHealthReport
) -> None:
    rank = {
        MeasurementHealth.HEALTHY: 0,
        MeasurementHealth.DEGRADED: 1,
        MeasurementHealth.UNAVAILABLE: 2,
    }
    combined = first.combine(second)
    assert rank[combined.health] >= rank[first.health]
    assert rank[combined.health] >= rank[second.health]

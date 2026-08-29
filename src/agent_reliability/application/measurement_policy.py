"""Application-owned policy extension boundary for measurement health."""

from __future__ import annotations

from typing import Protocol, TypeVar

from agent_reliability.domain.measurement_health import MeasurementHealthReport

__all__ = ["MeasurementPolicy"]

PolicyResultT_co = TypeVar("PolicyResultT_co", covariant=True)


class MeasurementPolicy(Protocol[PolicyResultT_co]):
    """Consumes SDK health and returns an application-owned result.

    The SDK defines neither business criticality nor allow/deny semantics.
    Implementations may return any application-specific type. Exceptions are
    ordinary application-policy failures and are never suppressed by the SDK.
    """

    def evaluate(
        self, *, measurement_health: MeasurementHealthReport
    ) -> PolicyResultT_co: ...

"""The event sink port.

Synchronous and non-generic on purpose: every M2 sink is in-process
(no I/O), so nothing needs to be awaited, and a synchronous protocol is
directly callable from both the SDK's sync and async code paths with no
adapter shim. See docs/SDK_DESIGN.md, "Sink port," for why this does not
foreclose an async, I/O-performing sink in a later milestone.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from agent_reliability.domain.measurement_health import MeasurementHealthReport
from agent_reliability.evaluation import EvaluationExecutionFailure
from agent_reliability.ports.events import InstrumentationEvent

__all__ = ["EventSink", "HealthEvidenceSink"]


@runtime_checkable
class EventSink(Protocol):
    """Receives instrumentation events as they occur.

    ``emit`` is synchronous, is called once for each event the SDK
    attempts to deliver, and preserves per-run lifecycle order. There is
    no total ordering across concurrent runs. The SDK does not serialize
    calls, so a sink shared across OS threads owns any thread-safety it
    requires. Implementations should avoid slow or blocking work.

    An implementation may raise ``Exception`` to report delivery
    failure. The SDK catches that at its failure-isolation boundary and
    routes it to diagnostics; control-flow ``BaseException`` subclasses
    deliberately propagate. The caller owns the sink. The SDK never
    closes, flushes, or otherwise manages its lifecycle.
    """

    def emit(self, event: InstrumentationEvent) -> None: ...


@runtime_checkable
class HealthEvidenceSink(Protocol):
    """Optional evidence capability; existing EventSink implementations stay valid."""

    def submit_evaluation_failure(
        self,
        failure: EvaluationExecutionFailure,
        *,
        run_id: str,
        indicator: str,
        evaluation_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> None: ...

    def submit_measurement_health(
        self,
        report: MeasurementHealthReport,
        *,
        run_id: str,
        measurement_id: str | None = None,
        observed_at: datetime | None = None,
    ) -> None: ...

    def release_run(self, run_id: str) -> None: ...

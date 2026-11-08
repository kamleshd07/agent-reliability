"""Experimental opt-in execution capture; not automatic outcome evaluation.

Framework dependencies are imported only when instrument() is configured.
"""

from .controller import InstrumentationStatus, InstrumentedRunnable, instrument
from .export import TraceExporter, build_requests
from .model import (
    CaptureDiagnostics,
    CaptureLimits,
    ComponentSummary,
    ExecutionEvent,
    ExecutionSummary,
    ExecutionTrace,
    TokenUsage,
)

__all__ = [
    "CaptureDiagnostics",
    "CaptureLimits",
    "ComponentSummary",
    "ExecutionEvent",
    "ExecutionSummary",
    "ExecutionTrace",
    "InstrumentationStatus",
    "InstrumentedRunnable",
    "TokenUsage",
    "TraceExporter",
    "build_requests",
    "instrument",
]

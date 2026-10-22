"""Experimental opt-in execution capture; not automatic outcome evaluation.

Framework dependencies are imported only when instrument() is configured.
"""

from .controller import InstrumentationStatus, InstrumentedRunnable, instrument
from .model import (
    CaptureDiagnostics,
    CaptureLimits,
    ExecutionEvent,
    ExecutionTrace,
    TokenUsage,
)

__all__ = [
    "CaptureDiagnostics",
    "CaptureLimits",
    "ExecutionEvent",
    "ExecutionTrace",
    "InstrumentationStatus",
    "InstrumentedRunnable",
    "TokenUsage",
    "instrument",
]

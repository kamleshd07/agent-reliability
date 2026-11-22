"""Experimental, opt-in emitter of content-free P25 handoff events (schema_version 1).

Not part of the stable API and not re-exported from ``agent_reliability``. Importing
this package starts no thread and opens no connection. See docs/HANDOFF_EMITTER.md.
"""

from ._contract import (
    HANDOFF_EVENTS_PATH,
    SCHEMA_VERSION,
    HandoffEvent,
    HandoffValidationError,
    build_event,
    idempotency_key,
)
from .emitter import (
    HandoffConfigError,
    HandoffEmitter,
    HandoffEmitterConfig,
    HandoffEmitterStats,
    TransportResponse,
)

__all__ = [
    "HANDOFF_EVENTS_PATH",
    "SCHEMA_VERSION",
    "HandoffConfigError",
    "HandoffEmitter",
    "HandoffEmitterConfig",
    "HandoffEmitterStats",
    "HandoffEvent",
    "HandoffValidationError",
    "TransportResponse",
    "build_event",
    "idempotency_key",
]

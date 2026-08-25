"""Diagnostics: how suppressed instrumentation failures stay observable.

Every failure this SDK suppresses to protect application code (see
docs/adr/0004-instrumentation-failure-isolation.md) is delivered here,
synchronously, in-process — never silently discarded, except at the one
documented last resort (a diagnostic handler that itself raises; see
``_report_diagnostic`` in ``client.py``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

__all__ = [
    "DiagnosticComponent",
    "DiagnosticHandler",
    "DiagnosticOperation",
    "LoggingDiagnosticHandler",
    "SdkDiagnostic",
]

DiagnosticComponent = Literal[
    "clock", "evaluator", "run_context_bridge", "run_id_generator", "sink", "sdk"
]
DiagnosticOperation = Literal["now", "evaluate", "generate", "emit", "start", "finish"]

_logger = logging.getLogger("agent_reliability.sdk")


@dataclass(frozen=True)
class SdkDiagnostic:
    """One suppressed instrumentation failure.

    Carries the original exception object deliberately — this channel's
    entire purpose is operator debugging of the SDK's own malfunctions.
    It is delivered synchronously to a caller-supplied handler and never
    serialized, exported, or retained by the SDK itself (see
    docs/SECURITY_MODEL.md).
    """

    component: DiagnosticComponent
    operation: DiagnosticOperation
    run_id: str | None
    exception: Exception = field(repr=False)


@runtime_checkable
class DiagnosticHandler(Protocol):
    """Receives suppressed instrumentation failures.

    If a handler implementation itself raises (an ``Exception`` — see
    ADR-0004 for why ``BaseException`` is never involved here), that
    failure is caught and dropped silently by the SDK — the one
    deliberate, documented last resort. Do not raise from a handler.
    """

    def handle(self, diagnostic: SdkDiagnostic) -> None: ...


class LoggingDiagnosticHandler:
    """The default handler: logs at WARNING via this library's own
    logger, never the application's root logger (a library must never
    configure a consumer's global logging — docs/ENGINEERING_PRINCIPLES.md).

    Retains nothing after logging. Deliberately logs only structured,
    sanitized metadata: never the exception message, representation,
    arguments, traceback, or raw diagnostic object — see
    docs/adr/0005-instrumentation-initialization-degraded-mode.md for why
    the default was changed to strip exception content, and
    docs/SECURITY_MODEL.md. A custom handler still receives the full
    exception object and is a trusted boundary for its own sensitive-data
    handling (ADR-0004, unchanged).
    """

    def handle(self, diagnostic: SdkDiagnostic) -> None:
        _logger.warning(
            "agent_reliability instrumentation failure: component=%s "
            "operation=%s run_id=%s exception_type=%s",
            diagnostic.component,
            diagnostic.operation,
            diagnostic.run_id,
            type(diagnostic.exception).__name__,
        )

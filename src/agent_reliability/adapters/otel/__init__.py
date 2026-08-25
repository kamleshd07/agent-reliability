"""Optional OpenTelemetry interoperability adapter.

Install ``agent-reliability[otel]`` before importing this module. The adapter
uses the OpenTelemetry API but never configures a provider or exporter.
"""

from __future__ import annotations

from agent_reliability.adapters.otel.run_context import (
    OpenTelemetryRunContextBridge,
)

__all__ = ["OpenTelemetryRunContextBridge"]

"""Join an existing OpenTelemetry context without configuring its backend."""

from __future__ import annotations

from opentelemetry import trace

from agent_reliability.adapters.otel import OpenTelemetryRunContextBridge
from agent_reliability.sdk import AgentReliability


def main() -> None:
    # The host application owns this tracer's provider, sampling, processors,
    # exporter, and collector. Agent Reliability configures none of them.
    host_tracer = trace.get_tracer("example-host")
    sdk = AgentReliability(run_context_bridge=OpenTelemetryRunContextBridge())

    with (
        host_tracer.start_as_current_span("incoming-request"),
        sdk.run(agent_id="otel-agent", name="OTel Agent", version="1.0"),
    ):
        print("Agent run is active inside the host-owned OTel context.")


if __name__ == "__main__":
    main()

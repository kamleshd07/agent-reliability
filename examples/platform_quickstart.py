"""Send synthetic, content-free evidence using an explicitly configured deployment.

Requires the optional HTTP exporter (`pip install 'agent-reliability[http]'`); see
docs/PLATFORM_QUICKSTART.md.
"""

from __future__ import annotations

import os
from uuid import UUID

from agent_reliability.adapters.http_event_sink import (
    DeliveryDisposition,
    HTTPEventSink,
)
from agent_reliability.domain import AgentIdentity, EvaluationOutcome
from agent_reliability.domain.measurement_health import MeasurementHealth
from agent_reliability.sdk import AgentReliability


def main() -> int:
    # Machine credentials stay in the environment, never command arguments/output.
    identity = AgentIdentity(
        os.environ["GENTLITY_AGENT_KEY"],
        os.environ["GENTLITY_AGENT_NAME"],
        os.environ["GENTLITY_AGENT_VERSION"],
        os.environ["GENTLITY_ENVIRONMENT_KEY"],
    )
    sink = HTTPEventSink(
        endpoint=os.environ["GENTLITY_EVIDENCE_URL"],
        credential_provider=lambda: os.environ["GENTLITY_MACHINE_TOKEN"],
        deployment_id=UUID(os.environ["GENTLITY_DEPLOYMENT_ID"]),
        expected_agent=identity,
    )
    try:
        with AgentReliability(sink=sink).run(
            agent_id=identity.agent_id,
            name=identity.name,
            version=identity.version,
            environment=identity.environment,
        ) as run:
            run.record(indicator="task-success", outcome=EvaluationOutcome.PASS)
    finally:
        snapshot = sink.close(timeout=15)
    accepted = {DeliveryDisposition.COMMITTED, DeliveryDisposition.DUPLICATE}
    acknowledged = sum(
        snapshot.counts_by_disposition.get(value, 0) for value in accepted
    )
    # This example emits start, evaluation, completion and final health evidence.
    failed = (
        run.run_id is None
        or run.measurement_health.health is not MeasurementHealth.HEALTHY
        or acknowledged != 4
        or snapshot.queue_depth > 0
        or any(
            count
            for disposition, count in snapshot.counts_by_disposition.items()
            if disposition not in accepted
        )
    )
    print(
        "Evidence acknowledged"
        if not failed
        else "Delivery incomplete; inspect redacted status"
    )
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())

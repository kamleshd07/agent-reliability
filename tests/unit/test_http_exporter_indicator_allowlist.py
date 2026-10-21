"""Opt-in ``indicator_allowlist`` pins the only free-text wire field."""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest

from agent_reliability.adapters.http_event_sink import (
    AsyncHTTPEventSink,
    ConfigurationError,
    HTTPEventSink,
)
from agent_reliability.domain import AgentIdentity, EvaluationOutcome
from agent_reliability.sdk import AgentReliability

AGENT = AgentIdentity("agent", "Agent", "1", "test")
SENTINEL = "customer jane@example.com asked about order 4417"


def _options(bodies: list[bytes], **extra: object) -> dict[str, object]:
    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(201, json={"status": "committed"})

    return {
        "endpoint": "http://127.0.0.1:9/api/v1/evidence/runs",
        "credential_provider": lambda: "secret",
        "deployment_id": UUID(int=7),
        "expected_agent": AGENT,
        "_transport": httpx.MockTransport(handler),
        **extra,
    }


def _run(sdk: AgentReliability, *indicators: str) -> None:
    with sdk.run(
        agent_id=AGENT.agent_id,
        name=AGENT.name,
        version=AGENT.version,
        environment=AGENT.environment,
    ) as run:
        for indicator in indicators:
            run.record(indicator=indicator, outcome=EvaluationOutcome.PASS)


def test_default_behaviour_is_unchanged_and_sends_any_valid_indicator() -> None:
    bodies: list[bytes] = []
    sink = HTTPEventSink(**_options(bodies))  # type: ignore[arg-type]
    _run(AgentReliability(sink=sink), SENTINEL)
    sink.close(timeout=10)
    assert any(SENTINEL.encode() in body for body in bodies)


def test_allowlist_blocks_unlisted_indicator_before_anything_is_queued_or_sent() -> (
    None
):
    bodies: list[bytes] = []
    sink = HTTPEventSink(
        **_options(bodies, indicator_allowlist=["task-success"])  # type: ignore[arg-type]
    )
    _run(AgentReliability(sink=sink), "task-success", SENTINEL)
    snapshot = sink.close(timeout=10)
    joined = b"".join(bodies)
    assert b"task-success" in joined
    assert SENTINEL.encode() not in joined
    assert b"jane@example.com" not in joined
    assert snapshot.queue_depth == 0


def test_allowlist_is_a_snapshot_not_a_live_view() -> None:
    bodies: list[bytes] = []
    names = ["task-success"]
    sink = HTTPEventSink(**_options(bodies, indicator_allowlist=names))  # type: ignore[arg-type]
    names.append(SENTINEL)
    _run(AgentReliability(sink=sink), SENTINEL)
    sink.close(timeout=10)
    assert SENTINEL.encode() not in b"".join(bodies)


@pytest.mark.parametrize(
    "bad", [[], "task-success", [1], [""], 5, ["a\nb"], ["x" * 201]]
)
def test_invalid_allowlist_is_a_configuration_error(bad: object) -> None:
    with pytest.raises(ConfigurationError):
        HTTPEventSink(**_options([], indicator_allowlist=bad))  # type: ignore[arg-type]


async def test_async_sink_applies_the_same_allowlist() -> None:
    bodies: list[bytes] = []
    sink = AsyncHTTPEventSink(
        **_options(bodies, indicator_allowlist={"task-success"})  # type: ignore[arg-type]
    )
    _run(AgentReliability(sink=sink), "task-success", SENTINEL)
    await sink.close(timeout=10)
    joined = b"".join(bodies)
    assert b"task-success" in joined
    assert SENTINEL.encode() not in joined

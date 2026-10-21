"""The exporter's "request may have left the process" tracking, on the REAL stack.

The exporter learns that a request was (at least partly) sent from an HTTPX/httpcore
trace event. Every other exporter test replaces the transport, so none would notice if a
future HTTPX/httpcore release renamed or dropped that event: uncertainty tracking would
then silently degrade. These tests use a real loopback socket (no mock transport) and
pin the behaviour for the supported HTTPX range (the ``http`` extra in pyproject.toml).
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from agent_reliability.adapters.http_event_sink import AsyncHTTPEventSink, HTTPEventSink
from agent_reliability.domain import AgentIdentity, EvaluationOutcome
from agent_reliability.sdk import AgentReliability

AGENT = AgentIdentity("agent", "Agent", "1", "test")
DEPLOYMENT = UUID(int=7)


@contextmanager
def read_then_drop_server() -> Iterator[int]:
    """Accept, read the whole request, then close without any response."""

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    listener.settimeout(0.2)
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except (TimeoutError, OSError):
                continue
            with connection:
                connection.settimeout(2)
                buffer = b""
                try:
                    while b"\r\n\r\n" not in buffer:
                        chunk = connection.recv(4096)
                        if not chunk:
                            break
                        buffer += chunk
                    header, _, rest = buffer.partition(b"\r\n\r\n")
                    length = 0
                    for line in header.split(b"\r\n"):
                        if line.lower().startswith(b"content-length:"):
                            length = int(line.split(b":", 1)[1])
                    while len(rest) < length:
                        more = connection.recv(4096)
                        if not more:
                            break
                        rest += more
                except OSError:
                    pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1]
    finally:
        stop.set()
        thread.join(2)
        listener.close()


def closed_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    return port


def _options(port: int) -> dict[str, object]:
    return {
        "endpoint": f"http://127.0.0.1:{port}/api/v1/evidence/runs",
        "credential_provider": lambda: "secret",
        "deployment_id": DEPLOYMENT,
        "expected_agent": AGENT,
        "retry_max_attempts": 1,
        "allow_unrestricted_indicators": True,
    }


def _run(sdk: AgentReliability) -> None:
    with sdk.run(
        agent_id=AGENT.agent_id,
        name=AGENT.name,
        version=AGENT.version,
        environment=AGENT.environment,
    ) as run:
        run.record(indicator="task-success", outcome=EvaluationOutcome.PASS)


def test_sync_sink_flags_records_whose_request_was_sent_but_never_acknowledged() -> (
    None
):
    with read_then_drop_server() as port:
        sink = HTTPEventSink(**_options(port))  # type: ignore[arg-type]
        _run(AgentReliability(sink=sink))
        snapshot = sink.close(timeout=10)
    assert snapshot.exhausted_may_have_committed > 0
    assert any(r.may_have_committed for r in snapshot.recent_records)


def test_sync_sink_does_not_flag_records_when_nothing_was_sent() -> None:
    sink = HTTPEventSink(**_options(closed_port()))  # type: ignore[arg-type]
    _run(AgentReliability(sink=sink))
    snapshot = sink.close(timeout=10)
    assert snapshot.exhausted_may_have_committed == 0
    assert not any(r.may_have_committed for r in snapshot.recent_records)


async def test_async_sink_flags_sent_but_unacknowledged_records() -> None:
    with read_then_drop_server() as port:
        sink = AsyncHTTPEventSink(**_options(port))  # type: ignore[arg-type]
        _run(AgentReliability(sink=sink))
        snapshot = await sink.close(timeout=10)
    assert snapshot.exhausted_may_have_committed > 0
    assert any(r.may_have_committed for r in snapshot.recent_records)


async def test_async_sink_does_not_flag_records_when_nothing_was_sent() -> None:
    sink = AsyncHTTPEventSink(**_options(closed_port()))  # type: ignore[arg-type]
    _run(AgentReliability(sink=sink))
    snapshot = await sink.close(timeout=10)
    assert snapshot.exhausted_may_have_committed == 0
    assert not any(r.may_have_committed for r in snapshot.recent_records)

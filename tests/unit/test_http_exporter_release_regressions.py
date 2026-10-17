"""Release-review regressions for the P28 HTTP exporter (review F-2/F-3/F-5/F-8).

F-2 (explicit proxy CONNECT) lives in ``test_http_exporter_tls_real.py`` beside the TLS
server it needs.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from agent_reliability.adapters import _http_delivery, http_event_sink
from agent_reliability.adapters._http_delivery import Config, Core
from agent_reliability.adapters.http_event_sink import (
    ConfigurationError,
    EventDeliveryRejected,
    HTTPEventSink,
)
from agent_reliability.domain import AgentIdentity
from agent_reliability.ports.events import RunStarted

AGENT = AgentIdentity("agent", "Agent", "1", "test")
BINDING = UUID("00000000-0000-4000-8000-000000000007")
ENDPOINT = "https://platform.example/api/v1/evidence/runs"


def _core() -> Core:
    return Core(Config(ENDPOINT, lambda: "secret", BINDING, AGENT))


# ---------------------------------------------------------------------- F-5
def test_naive_timestamps_are_rejected_before_admission() -> None:
    core = _core()
    with pytest.raises(EventDeliveryRejected, match="timestamp_naive"):
        core.emit(RunStarted("run-1", None, AGENT, datetime(2026, 1, 1)))
    assert core.snapshot().queue_depth == 0


def test_request_body_cap_is_exactly_64_kib(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(size: int) -> SimpleNamespace:
        return SimpleNamespace(dumps=lambda *_a, **_k: "x" * size, loads=json.loads)

    ok = _core()
    monkeypatch.setattr(_http_delivery, "json", fake(65536))
    ok.emit(RunStarted("run-1", None, AGENT, datetime.now(UTC)))
    assert ok.snapshot().queue_depth == 1

    too_big = _core()
    monkeypatch.setattr(_http_delivery, "json", fake(65537))
    with pytest.raises(EventDeliveryRejected, match="request_too_large"):
        too_big.emit(RunStarted("run-1", None, AGENT, datetime.now(UTC)))
    assert too_big.snapshot().queue_depth == 0


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://user@platform.example/api/v1/evidence/runs",
        "https://user:secret@platform.example/api/v1/evidence/runs",
        "http://user@127.0.0.1:8000/api/v1/evidence/runs",
        "https://platform.example@evil.example/api/v1/evidence/runs",
    ],
)
def test_userinfo_endpoints_are_rejected_at_construction(endpoint: str) -> None:
    with pytest.raises(ConfigurationError):
        HTTPEventSink(
            endpoint=endpoint,
            credential_provider=lambda: "secret",
            deployment_id=BINDING,
            expected_agent=AGENT,
        )


# ---------------------------------------------------------------------- F-3
def test_a_response_body_trickled_past_the_budget_is_abandoned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A peer that sends headers and then trickles the body must not pin a worker for
    the whole trickle: the attempt ends after the body budget and the record is retried
    (a trickled body is never an acknowledgement)."""

    monkeypatch.setattr(http_event_sink, "_BODY_SECONDS", 0.5)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    connections: list[int] = []
    stop = threading.Event()

    def trickle(conn: socket.socket) -> None:
        try:
            conn.recv(65536)
            conn.sendall(
                b"HTTP/1.1 201 Created\r\ncontent-type: application/json\r\n"
                b"content-length: 60000\r\nconnection: close\r\n\r\n"
            )
            while not stop.is_set():
                conn.sendall(b"x")
                time.sleep(0.05)
        except OSError:
            pass
        finally:
            conn.close()

    def accept() -> None:
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            connections.append(1)
            threading.Thread(target=trickle, args=(conn,), daemon=True).start()

    threading.Thread(target=accept, daemon=True).start()
    sink = HTTPEventSink(
        endpoint=f"http://127.0.0.1:{listener.getsockname()[1]}/api/v1/evidence/runs",
        credential_provider=lambda: "secret",
        deployment_id=BINDING,
        expected_agent=AGENT,
        retry_max_attempts=5,
    )
    sink._core._backoff = lambda _n: 0
    try:
        sink.emit(RunStarted("run-1", None, AGENT, datetime.now(UTC)))
        deadline = time.monotonic() + 8
        while len(connections) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        # Without the body budget the first attempt would be pinned for as long as the
        # peer keeps trickling (here ~50 minutes), so no second connection would appear.
        assert len(connections) >= 2
        status = sink.status
        assert not any(
            r.disposition.value in {"committed", "duplicate"}
            for r in status.recent_records
        )
    finally:
        stop.set()
        sink.close(1)
        listener.close()


# ---------------------------------------------------------------------- F-8
def test_missing_httpx_gives_an_actionable_message() -> None:
    code = (
        "import sys\n"
        "sys.modules['httpx'] = None\n"  # makes `import httpx` raise ImportError
        "try:\n"
        "    import agent_reliability.adapters.http_event_sink\n"
        "except ImportError as error:\n"
        "    print(error)\n"
        "else:\n"
        "    print('IMPORTED')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert "agent-reliability[http]" in result.stdout
    assert "IMPORTED" not in result.stdout


def test_importing_the_core_package_does_not_import_httpx() -> None:
    code = (
        "import sys\n"
        "import agent_reliability, agent_reliability.sdk, agent_reliability.adapters\n"
        "print('httpx' in sys.modules)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "False"


# ------------------------------------------------------------------ idle cost (F-10)
def test_idle_workers_do_not_build_status_snapshots() -> None:
    """Each idle worker loop used to build a full status snapshot (up to 1,000 history
    rows) every 10 ms just to see whether the sink was closed (~2.7% of a core)."""

    sink = HTTPEventSink(
        endpoint=ENDPOINT,
        credential_provider=lambda: "secret",
        deployment_id=BINDING,
        expected_agent=AGENT,
    )
    calls = 0
    original = sink._core.snapshot

    def counting() -> object:
        nonlocal calls
        calls += 1
        return original()

    sink._core.snapshot = counting  # type: ignore[method-assign]
    try:
        time.sleep(0.5)  # two workers x ~50 loops each if the old behaviour returned
        assert calls <= 5, calls
    finally:
        sink._core.snapshot = original  # type: ignore[method-assign]
        sink.close(1)

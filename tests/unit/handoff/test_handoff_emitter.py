# ruff: noqa: C408
"""Delivery, retry, loss, unsupported-platform and isolation semantics (no real
internet; a fake transport plus one loopback http.server)."""

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest

from agent_reliability.experimental.handoff import (
    HandoffConfigError,
    HandoffEmitter,
    HandoffEmitterConfig,
    TransportResponse,
)

A = "00000000-0000-4000-8000-0000000000a1"
B = "00000000-0000-4000-8000-0000000000b2"
TOKEN = "are_machine_SECRET_TOKEN_value"
OK = json.dumps({"event_id": "e", "duplicate": False}).encode()


def err(code):
    return json.dumps({"error": {"code": code, "message": "m"}}).encode()


class Fake:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, body, headers, timeout):
        self.calls.append((url, body, dict(headers)))
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        status, headers_, body_ = item
        return TransportResponse(status, headers_, body_)


def cfg(**kw):
    base = dict(
        enabled=True,
        base_url="https://gentlity.example",
        credential_provider=lambda: TOKEN,
        backoff_base_seconds=0.001,
        backoff_cap_seconds=0.005,
        retry_after_cap_seconds=0.02,
        max_attempts=4,
    )
    base.update(kw)
    return HandoffEmitterConfig(**base)


def send(emitter, n=1):
    result = None
    for i in range(n):
        result = emitter.requested(
            handoff_id=f"h-{i}",
            originating_agent_id=A,
            originating_producer_run_id="run-1",
            receiving_agent_id=B,
        )
    return result


def send_one(emitter, handoff_id):
    return emitter.requested(
        handoff_id=handoff_id,
        originating_agent_id=A,
        originating_producer_run_id="r",
        receiving_agent_id=B,
    )


def run(transport, config=None, n=1):
    emitter = HandoffEmitter(config or cfg(), _transport=transport)
    send(emitter, n)
    stats = emitter.flush(5)
    emitter.close(1)
    return stats


def test_disabled_by_default_sends_nothing_and_starts_no_thread():
    before = threading.active_count()
    fake = Fake((201, {}, OK))
    emitter = HandoffEmitter(HandoffEmitterConfig(), _transport=fake)
    assert send(emitter, 3) == "disabled"
    assert emitter.acknowledged(
        handoff_id="h", originating_agent_id=A, originating_producer_run_id="r",
        receiving_agent_id=B, acceptance="declined",
    ) == "disabled"  # fmt: skip
    assert emitter.stats.state == "disabled" and emitter.stats.submitted == 0
    emitter.flush(0.1)
    emitter.close(0.1)
    assert fake.calls == [] and threading.active_count() == before


def test_enabled_requires_endpoint_and_credential():
    with pytest.raises(HandoffConfigError):
        HandoffEmitter(HandoffEmitterConfig(enabled=True))
    with pytest.raises(HandoffConfigError):
        HandoffEmitter(cfg(base_url="http://gentlity.example"))  # plaintext, non-loop
    with pytest.raises(HandoffConfigError):
        HandoffEmitter(cfg(base_url="https://gentlity.example/api"))
    with pytest.raises(HandoffConfigError):
        HandoffEmitter(cfg(max_events=0))


@pytest.mark.parametrize(
    ("status", "field"), [(201, "delivered_created"), (200, "delivered_duplicate")]
)
def test_success_is_delivered_once_with_bearer_and_fixed_path(status, field):
    fake = Fake((status, {}, OK))
    stats = run(fake)
    assert getattr(stats, field) == 1 and len(fake.calls) == 1
    url, body, headers = fake.calls[0]
    assert url == "https://gentlity.example/api/v1/handoff-events"
    assert headers["Authorization"] == "Bearer " + TOKEN
    assert json.loads(body)["schema_version"] == 1 and stats.queued_events == 0


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (401, err("authentication_error")),
        (403, err("authorization_error")),
        (409, err("conflict")),
        (413, err("payload_too_large")),
        (422, err("validation_error")),
        (429, err("handoff_limit_exceeded")),
        (400, b""),
    ],
)
def test_non_retryable_statuses_are_rejected_once_and_dropped(status, body):
    fake = Fake((status, {}, body))
    stats = run(fake)
    assert len(fake.calls) == 1
    assert stats.rejected == 1 and stats.retries == 0 and stats.lost_exhausted == 0
    assert stats.last_error == f"http_{status}"


@pytest.mark.parametrize(
    "first",
    [
        (429, {"retry-after": "0"}, err("rate_limited")),
        (503, {}, b""),
        (500, {}, b""),
        (409, {}, err("run_not_yet_known")),
        OSError("boom"),
    ],
)
def test_transient_failures_retry_then_deliver_with_identical_bytes(first):
    fake = Fake(first, (201, {}, OK))
    stats = run(fake)
    assert len(fake.calls) == 2 and fake.calls[0][1] == fake.calls[1][1]
    assert stats.retries == 1 and stats.delivered_created == 1
    assert stats.rejected == 0 and stats.lost_exhausted == 0


def test_retry_after_is_honoured_and_capped():
    fake = Fake((429, {"retry-after": "3600"}, err("rate_limited")), (201, {}, OK))
    start = time.monotonic()
    stats = run(fake)
    assert stats.delivered_created == 1 and time.monotonic() - start < 2


def test_retry_exhaustion_is_counted_as_loss():
    fake = Fake((503, {}, b""))
    stats = run(fake)
    assert len(fake.calls) == 4 and stats.retries == 3
    assert stats.lost_exhausted == 1 and stats.delivered_created == 0
    assert stats.last_error == "http_503"


def test_max_event_age_bounds_retrying():
    fake = Fake((503, {}, b""))
    config = cfg(
        max_attempts=10,
        max_event_age_seconds=0.05,
        backoff_base_seconds=0.03,
        backoff_cap_seconds=0.03,
    )
    stats = run(fake, config)
    assert stats.lost_exhausted == 1 and len(fake.calls) < 10


@pytest.mark.parametrize("status", [404, 405])
def test_unsupported_platform_stops_permanently_without_downgrade(status):
    fake = Fake((status, {}, b""))
    emitter = HandoffEmitter(cfg(), _transport=fake)
    send(emitter, 3)
    emitter.flush(5)
    stats = emitter.stats
    assert stats.state == "unsupported" and stats.unsupported_responses == 1
    calls_after_first = len(fake.calls)
    assert calls_after_first == 1  # queued events were discarded, not retried
    assert send(emitter, 2) == "unsupported"
    emitter.flush(0.2)
    assert len(fake.calls) == calls_after_first
    assert all(c[0].endswith("/api/v1/handoff-events") for c in fake.calls)
    assert emitter.stats.dropped_unsupported >= 5 and emitter.stats.queued_events == 0
    emitter.close(1)


@pytest.mark.parametrize("version", [2, "1", 0, None, True])
def test_different_schema_in_response_is_a_rejection_never_reinterpreted(version):
    body = json.dumps({"event_id": "e", "schema_version": version}).encode()
    fake = Fake((201, {}, body))
    stats = run(fake)
    assert stats.rejected == 1 and stats.delivered_created == 0
    assert stats.last_error == "schema_mismatch" and len(fake.calls) == 1


def test_unparseable_success_is_not_counted_as_delivered():
    stats = run(Fake((200, {}, b"<html>")))
    assert stats.rejected == 1 and stats.delivered_duplicate == 0


class Gate:
    """Blocks the worker so the buffer fills deterministically."""

    def __init__(self):
        self.release = threading.Event()
        self.started = threading.Event()
        self.bodies = []

    def __call__(self, url, body, headers, timeout):
        self.bodies.append(json.loads(body)["handoff_id"])
        self.started.set()
        self.release.wait(5)
        return TransportResponse(201, {}, OK)


def test_drop_newest_bounds_buffer_and_counts_drops():
    gate = Gate()
    emitter = HandoffEmitter(cfg(max_events=3, overflow="drop_newest"), _transport=gate)
    send(emitter, 1)
    assert gate.started.wait(2)  # h-0 in flight, buffer empty
    results = [send_one(emitter, f"n-{i}") for i in range(6)]
    assert results == ["queued"] * 3 + ["dropped"] * 3
    stats = emitter.stats
    assert stats.queued_events == 3 and stats.dropped_buffer_full == 3
    gate.release.set()
    emitter.flush(5)
    assert gate.bodies == ["h-0", "n-0", "n-1", "n-2"]
    emitter.close(1)


def test_drop_oldest_keeps_newest_and_counts_drops():
    gate = Gate()
    emitter = HandoffEmitter(cfg(max_events=2, overflow="drop_oldest"), _transport=gate)
    send(emitter, 1)
    assert gate.started.wait(2)
    for i in range(5):
        send_one(emitter, f"n-{i}")
    assert emitter.stats.queued_events == 2 and emitter.stats.dropped_buffer_full == 3
    gate.release.set()
    emitter.flush(5)
    assert gate.bodies == ["h-0", "n-3", "n-4"]
    emitter.close(1)


def test_byte_bound_is_enforced():
    gate = Gate()
    emitter = HandoffEmitter(
        cfg(max_bytes=1024, overflow="drop_newest"), _transport=gate
    )
    send(emitter, 1)
    assert gate.started.wait(2)
    send(emitter, 20)
    stats = emitter.stats
    assert stats.queued_bytes <= 1024 and stats.dropped_buffer_full > 0
    gate.release.set()
    emitter.close(2)


def test_emit_after_close_is_counted_and_close_abandons_leftovers():
    gate = Gate()
    emitter = HandoffEmitter(cfg(), _transport=gate)
    send(emitter, 3)
    assert gate.started.wait(2)
    stats = emitter.close(0.1)  # worker is blocked: leftovers abandoned
    assert stats.state == "closed" and stats.dropped_closed >= 2
    assert send(emitter) == "closed"
    gate.release.set()


class BadProvider:
    def __call__(self):
        raise RuntimeError(TOKEN)


def test_emit_never_raises_and_never_leaks_the_token():
    boom = Fake(RuntimeError("connect failed with Bearer " + TOKEN))
    emitter = HandoffEmitter(cfg(max_attempts=2), _transport=boom)
    assert send(emitter, 2) == "queued"
    stats = emitter.flush(5)
    emitter.close(1)
    assert stats.lost_exhausted == 2 and stats.last_error == "network"
    blob = repr(stats) + repr(emitter) + repr(cfg()) + str(emitter.stats)
    assert TOKEN not in blob and "SECRET" not in blob

    seen_calls = len(boom.calls)
    emitter = HandoffEmitter(cfg(credential_provider=BadProvider(), max_attempts=1),
                             _transport=boom)  # fmt: skip
    send(emitter)
    stats = emitter.flush(5)
    emitter.close(1)
    assert (
        stats.last_error == "credential_unavailable" and len(boom.calls) == seen_calls
    )
    assert TOKEN not in repr(stats)


def test_invalid_input_never_raises_and_is_counted_not_queued():
    fake = Fake((201, {}, OK))
    emitter = HandoffEmitter(cfg(), _transport=fake)
    assert emitter.terminal(
        handoff_id="bad id", originating_agent_id=A, originating_producer_run_id="r",
        receiving_agent_id=B, terminal_state="completed",
    ) == "invalid"  # fmt: skip
    assert emitter.requested(
        handoff_id="h", originating_agent_id=object(), originating_producer_run_id="r",
        receiving_agent_id=B,
    ) == "invalid"  # fmt: skip
    stats = emitter.stats
    assert stats.rejected_invalid == 2 and stats.submitted == 0
    assert "bad id" not in repr(stats)
    emitter.close(1)
    assert fake.calls == []


def test_emit_returns_quickly_even_if_the_transport_hangs():
    gate = Gate()
    emitter = HandoffEmitter(cfg(), _transport=gate)
    start = time.monotonic()
    send(emitter, 50)
    assert time.monotonic() - start < 1.0
    gate.release.set()
    emitter.close(2)


class _Handler(BaseHTTPRequestHandler):
    seen: ClassVar[list] = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Handler.seen.append(
            (self.path, self.headers["Authorization"], json.loads(body))
        )
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(OK)

    def log_message(self, *_args):
        pass


def test_default_stdlib_transport_against_loopback_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = cfg(base_url=f"http://127.0.0.1:{server.server_port}")
        with HandoffEmitter(config) as emitter:
            send(emitter)
            stats = emitter.flush(5)
        assert stats.delivered_created == 1
        path, auth, body = _Handler.seen[0]
        assert path == "/api/v1/handoff-events" and auth == "Bearer " + TOKEN
        assert body["kind"] == "requested" and "reporter" not in body
    finally:
        server.shutdown()
        server.server_close()


def test_close_accounting_is_idempotent_for_inflight_and_queued():
    gate = Gate()
    emitter = HandoffEmitter(cfg(), _transport=gate)
    send(emitter, 3)  # one in flight (blocked), two queued
    assert gate.started.wait(2)
    first = emitter.close(0.1)
    assert first.dropped_closed == 3
    assert emitter.close(0.1).dropped_closed == 3
    gate.release.set()
    time.sleep(0.2)  # the worker wakes, sees the abandon, must not recount
    assert emitter.stats.dropped_closed == 3


@pytest.mark.skipif(not hasattr(os, "fork"), reason="needs os.fork")
def test_worker_is_restarted_in_a_forked_child_without_duplicating_parent_events():
    import json as _json

    read, write = os.pipe()
    fake = Fake((201, {}, OK))
    emitter = HandoffEmitter(cfg(), _transport=fake)
    send(emitter, 1)
    emitter.flush(5)  # parent worker exists and is idle
    pid = os.fork()
    if pid == 0:  # child
        code = 1
        try:
            send_one(emitter, "child-1")
            stats = emitter.flush(5)
            ids = [_json.loads(c[1])["handoff_id"] for c in fake.calls]
            ok = stats.delivered_created == 2 and ids[-1] == "child-1"
            os.write(write, b"ok" if ok else b"bad")
            code = 0
        finally:
            os._exit(code)
    os.close(write)
    os.waitpid(pid, 0)
    assert os.read(read, 8) == b"ok"
    os.close(read)
    emitter.close(1)

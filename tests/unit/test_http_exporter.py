"""P28 mocked delivery, state-machine, lifecycle and security regressions."""

from __future__ import annotations

import asyncio
import json
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from agent_reliability.adapters._http_delivery import Config, Core
from agent_reliability.adapters.http_event_sink import (
    AsyncHTTPEventSink,
    ConfigurationError,
    ConfigurationFailedError,
    EventDeliveryRejected,
    ExporterClosed,
    HTTPEventSink,
)
from agent_reliability.adapters.http_event_sink import (
    DeliveryDisposition as D,
)
from agent_reliability.domain import AgentIdentity, EvaluationOutcome
from agent_reliability.ports.events import EvaluationRecorded, RunCompleted, RunStarted
from agent_reliability.sdk import AgentReliability

AGENT = AgentIdentity("agent", "Agent", "1.0", "test")
DEPLOYMENT = UUID("00000000-0000-4000-8000-000000000007")
ENDPOINT = "https://platform.example/api/v1/evidence/runs"
NOW = datetime.now(UTC)


def start(run_id="run-1"):
    return RunStarted(run_id, None, AGENT, NOW)


def core(**kwargs):
    result = Core(
        Config(
            ENDPOINT,
            lambda: "secret",
            DEPLOYMENT,
            AGENT,
            **{"allow_unrestricted_indicators": True, **kwargs},
        )
    )
    result.credential = "secret"
    result.generation = 1
    result._backoff = lambda _n: 0
    return result


def send(core):
    attempt = core.take()
    assert attempt is not None
    record, _credential = attempt
    core.mark_sent(record)
    return record


def ack(event_id, status=201):
    return {
        "event_id": event_id,
        "run_id": str(DEPLOYMENT),
        "status": "accepted" if status == 201 else "duplicate",
        "durability": "committed",
    }


def error(code):
    return json.dumps({"error": {"code": code}}).encode()


def sink(handler, **kwargs):
    return HTTPEventSink(
        allow_unrestricted_indicators=True,
        endpoint=ENDPOINT,
        credential_provider=lambda: "secret",
        deployment_id=DEPLOYMENT,
        expected_agent=AGENT,
        _transport=httpx.MockTransport(handler),
        **kwargs,
    )


def wait_state(sink, state):
    deadline = time.monotonic() + 2
    while sink.status.sink_state != state and time.monotonic() < deadline:
        time.sleep(0.005)
    assert sink.status.sink_state == state


@pytest.mark.parametrize("status", [200, 201])
def test_mocked_ingestion_and_duplicate(status):
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert request.headers["authorization"] == "Bearer secret"
        assert "cookie" not in request.headers
        return httpx.Response(status, json=ack(body["event_id"], status))

    exporter = sink(handler)
    try:
        exporter.emit(start())
        result = exporter.flush(2)
        assert result.queue_depth == 0
        assert result.recent_records[-1].disposition == (
            D.COMMITTED if status == 201 else D.DUPLICATE
        )
        assert seen[0]["producer_identity"] == {
            "agent_id": "agent",
            "version": "1.0",
            "environment": "test",
        }
        assert UUID(seen[0]["event_id"][4:]).version == 4
    finally:
        exporter.close(0)


@pytest.mark.parametrize(
    "status,code,state",
    [
        (403, "forbidden", "auth_paused"),
        (404, "not_found", "deployment_unavailable"),
        (302, "", "endpoint_paused"),
    ],
)
def test_pause_response_and_resume(status, code, state):
    c = core()
    c.emit(start())
    r = send(c)
    c.complete(r, status, error(code) if code else b"")
    assert c.snapshot().sink_state == state
    assert c.snapshot().queue_depth == 1
    assert c.take() is None
    if status != 403:
        c.resume(state)
        assert c.take() is not None


def test_identity_mismatch_cancels_other_runs_and_requires_new_sink():
    c = core()
    c.emit(start())
    c.emit(start("run-2"))
    r = send(c)
    c.complete(r, 409, error("deployment_identity_mismatch"))
    result = c.snapshot()
    assert result.sink_state == "configuration_failed"
    assert result.counts_by_disposition[D.PERMANENTLY_FAILED] == 1
    assert result.counts_by_disposition[D.CANCELLED] == 1
    with pytest.raises(ConfigurationFailedError):
        c.emit(start("run-3"))
    with pytest.raises(ConfigurationFailedError):
        c.resume("schema_paused")


def test_conflict_is_event_only_and_404_without_envelope_retries():
    c = core()
    c.emit(start())
    c.emit(start("run-2"))
    c.complete(send(c), 409, error("conflict"))
    assert c.snapshot().sink_state == "open"
    r = send(c)
    c.complete(r, 404, b'{"detail":"Not Found"}')
    assert r.attempts == 1 and r.uncertain


def test_schema_streak_neutral_errors_ack_reset_and_explicit_resume():
    c = core()
    c.emit(start())
    for _ in range(2):
        r = send(c)
        c.complete(r, 422, error("unsupported_schema_version"))
        assert r.attempts == 0
    r = send(c)
    c.complete(r, 500, error("internal_error"))
    r = send(c)
    c.complete(r, 422, error("unsupported_schema_version"))
    assert c.snapshot().sink_state == "schema_paused"
    c.resume("schema_paused")
    r = send(c)
    c.complete(r, 201, json.dumps(ack(r.event_id)).encode())
    assert c.streak == (None, 0)
    assert c.snapshot().counts_by_disposition[D.COMMITTED] == 1


def test_legacy_compatibility_shape_and_content_error():
    c = core()
    c.emit(start())
    r = send(c)
    body = json.dumps(
        {
            "error": {
                "code": "validation_error",
                "details": [
                    {
                        "type": "extra_forbidden",
                        "location": ["body", "producer_identity"],
                    }
                ],
            }
        }
    ).encode()
    c.complete(r, 422, body)
    assert r.attempts == 0 and c.streak[1] == 1
    c.complete(send(c), 422, error("validation_error"))
    assert c.snapshot().unclassified_422_count == 1
    assert c.snapshot().sink_state == "open"


@pytest.mark.parametrize("status", [408, 500, 502, 503, 504, 204])
def test_retry_exhaustion_identical_body_and_sticky_uncertainty(status):
    c = core()
    c.emit(start())
    bodies = []
    for _ in range(3):
        r = send(c)
        bodies.append(r.body)
        c.complete(r, status, error("internal_error"))
    assert bodies[0] == bodies[1] == bodies[2]
    result = c.snapshot()
    assert result.counts_by_disposition[D.RETRY_EXHAUSTED] == 1
    assert result.exhausted_may_have_committed == (0 if status == 408 else 1)


def test_malformed_ack_then_duplicate_clears_sticky_flag():
    c = core()
    c.emit(start())
    r = send(c)
    c.complete(r, 200, b"{}")
    assert r.uncertain
    r = send(c)
    c.complete(r, 200, json.dumps(ack(r.event_id, 200)).encode())
    assert not c.snapshot().recent_records[-1].may_have_committed


def test_rate_gate_separate_attempt_budget_and_ra_b(monkeypatch):
    c = core()
    c.emit(start())
    monkeypatch.setattr(
        "agent_reliability.adapters._http_delivery.random.uniform", lambda a, b: 0
    )
    r = send(c)
    c.complete(r, 429, error("rate_limited"), ("00000000060",))
    assert c.snapshot().sink_state == "rate_gated"
    assert r.throttles == 1 and r.attempts == 0
    assert c.rate_until - time.monotonic() > 59
    c.rate_until = 0
    for _ in range(3):
        c.complete(send(c), 429, error("rate_limited"), ("0",))
    assert c.snapshot().counts_by_disposition[D.RETRY_EXHAUSTED] == 1


def test_tls_gate_threshold_no_unknown_commit_and_overlapping_gates():
    c = core()
    c.emit(start())
    for i in range(3):
        attempt = c.take()
        assert attempt
        r, _ = attempt
        c.complete(r, failure="tls_verification_failed")
        assert r.uncertain is False
        if i < 2:
            assert c.snapshot().sink_state == "open"
    assert c.snapshot().sink_state == "endpoint_paused"
    c.gates.add("schema_paused")
    c.resume("endpoint_paused")
    assert c.snapshot().sink_state == "schema_paused"
    c.resume("schema_paused")
    assert c.take() is not None


def test_tls_classifier_checks_exception_chain():
    from agent_reliability.adapters.http_event_sink import _failure

    c = core()
    c.emit(start())
    r = c.take()[0]
    exc = httpx.ConnectError("secret should never be rendered")
    exc.__cause__ = ssl.SSLCertVerificationError("certificate error")
    assert _failure(exc, r) == "tls_verification_failed"


def test_queue_capacity_reserves_and_release_after_terminal_rejection():
    c = core(max_queue_records=4, closure_reserve_records=2)
    c.emit(start())
    c.emit(EvaluationRecorded("run-1", "indicator", EvaluationOutcome.PASS, NOW))
    with pytest.raises(EventDeliveryRejected, match="queue_full"):
        c.emit(start("run-2"))
    c.emit(RunCompleted("run-1", NOW))
    c.emit(RunCompleted("run-1", NOW))
    with pytest.raises(EventDeliveryRejected, match="closure_reserve_exhausted"):
        c.emit(RunCompleted("run-1", NOW))
    c.release_run("run-1")
    c.release_run("run-1")
    result = c.snapshot()
    assert result.closure_reserve_rejections == 1 and result.active_binding_count == 0
    assert result.terminal_tombstone_count == 1


def test_close_deadline_abandons_request_late_response_is_discarded():
    c = core()
    c.emit(start())
    r = send(c)
    c.begin_close(0)
    closed = c.snapshot()
    assert closed.sink_state == "closed"
    assert closed.recent_records[-1].may_have_committed
    c.complete(r, 201, json.dumps(ack(r.event_id)).encode())
    assert c.snapshot().late_response_discarded == 1
    with pytest.raises(ExporterClosed):
        c.emit(start("run-2"))


def test_provider_hang_single_flight_timeout_and_late_result():
    gate = threading.Event()
    calls = []

    def provider():
        calls.append(1)
        gate.wait(2)
        return "secret"

    c = Core(
        Config(
            ENDPOINT,
            provider,
            DEPLOYMENT,
            AGENT,
            allow_unrestricted_indicators=True,
            provider_timeout=0.02,
        )
    )
    c.emit(start())
    assert c.take() is None
    time.sleep(0.03)
    assert c.snapshot().pause_reason == "credential_invalid_local"
    for _ in range(3):
        assert c.resume_auth_read() is None
    assert calls == [1] and c.snapshot().provider_call_outstanding == 3
    c.begin_close(0)
    gate.set()
    deadline = time.monotonic() + 1
    while c.call and time.monotonic() < deadline:
        time.sleep(0.005)
    assert c.snapshot().late_credential_result_discarded == 1
    assert c.credential is None


def test_401_refresh_then_403_cannot_resume_until_changed_provider():
    value = ["secret-2"]
    c = Core(
        Config(
            ENDPOINT,
            lambda: value[0],
            DEPLOYMENT,
            AGENT,
            allow_unrestricted_indicators=True,
        )
    )
    c.credential = "secret"
    c.generation = 1
    c.emit(start())
    c.complete(send(c), 401, error("unauthorized"))
    deadline = time.monotonic() + 1
    while c.read and time.monotonic() < deadline:
        time.sleep(0.005)
    assert c.snapshot().sink_state == "open" and c.credential == "secret-2"
    c.complete(send(c), 403, error("forbidden"))
    read = c.resume_auth_read()
    read.done.wait(1)
    assert c.snapshot().sink_state == "auth_paused"
    value[0] = "secret-3"
    read = c.resume_auth_read()
    read.done.wait(1)
    assert c.snapshot().sink_state == "open"


def test_concurrent_runs_and_sdk_health_cleanup():
    seen = []
    lock = threading.Lock()

    def handler(request):
        body = json.loads(request.content)
        with lock:
            seen.append(body)
        return httpx.Response(201, json=ack(body["event_id"]))

    exporter = sink(handler)
    try:
        sdk = AgentReliability(sink=exporter)

        def run(_):
            with sdk.run(
                agent_id="agent", name="Agent", version="1.0", environment="test"
            ) as handle:
                handle.record(indicator="task", outcome=EvaluationOutcome.PASS)

        with ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(run, range(10)))
        result = exporter.flush(3)
        assert result.queue_depth == 0 and result.active_binding_count == 0
        assert len(seen) == 40
        for run_id in {body["producer_run_id"] for body in seen}:
            assert [
                body["payload"]["kind"]
                for body in seen
                if body["producer_run_id"] == run_id
            ] == [
                "run_lifecycle",
                "evaluation_outcome",
                "run_lifecycle",
                "measurement_health",
            ]
    finally:
        exporter.close(0)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost",
        "http://example.com",
        "https://user:pass@example.com",
        "https://good.com\\@evil.test",
        "https://example.com/#x",
        "HTTPS://example.com",
        "http://127.0.0.1:080",
    ],
)
def test_rejects_unsafe_urls_without_provider_call(url):
    calls = []
    with pytest.raises(ConfigurationError):
        HTTPEventSink(
            allow_unrestricted_indicators=True,
            endpoint=url,
            credential_provider=lambda: calls.append(1),
            deployment_id=DEPLOYMENT,
            expected_agent=AGENT,
        )
    assert calls == []


def test_diagnostics_redaction_and_invalid_credential():
    exporter = HTTPEventSink(
        allow_unrestricted_indicators=True,
        endpoint=ENDPOINT,
        credential_provider=lambda: "secret\r\nattack",
        deployment_id=DEPLOYMENT,
        expected_agent=AGENT,
    )
    try:
        exporter.emit(start())
        wait_state(exporter, "auth_paused")
        result = exporter.status
        assert result.pause_reason == "credential_invalid_local"
        assert "secret" not in repr(result)
        assert "platform.example" not in repr(exporter._core.config)
    finally:
        exporter.close(0)


@pytest.mark.asyncio
async def test_native_async_delivery_and_cross_thread_rules():
    async def handler(request):
        await asyncio.sleep(0.001)
        return httpx.Response(201, json=ack(json.loads(request.content)["event_id"]))

    exporter = AsyncHTTPEventSink(
        allow_unrestricted_indicators=True,
        endpoint=ENDPOINT,
        credential_provider=lambda: "secret",
        deployment_id=DEPLOYMENT,
        expected_agent=AGENT,
        _transport=httpx.MockTransport(handler),
    )
    exporter.emit(start())
    result = await exporter.flush(2)
    assert result.counts_by_disposition[D.COMMITTED] == 1
    errors = []

    def other():
        try:
            exporter.emit(start("run-2"))
        except EventDeliveryRejected as exc:
            errors.append(str(exc))
        exporter.release_run("run-1")
        assert exporter.status is not None

    thread = threading.Thread(target=other)
    thread.start()
    thread.join()
    await asyncio.sleep(0.02)
    assert errors == ["owner_loop_required"]
    assert exporter.status.active_binding_count == 0
    await exporter.close(0)
    await exporter._cleanup


@pytest.mark.asyncio
async def test_async_close_cancels_hung_http_and_preserves_uncertainty():
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def handler(request):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    exporter = AsyncHTTPEventSink(
        allow_unrestricted_indicators=True,
        endpoint=ENDPOINT,
        credential_provider=lambda: "secret",
        deployment_id=DEPLOYMENT,
        expected_agent=AGENT,
        _transport=httpx.MockTransport(handler),
    )
    exporter.emit(start())
    await asyncio.wait_for(entered.wait(), 1)
    result = await exporter.close(0)
    assert result.sink_state == "closed" and result.exhausted_may_have_committed == 1
    await exporter._cleanup
    assert cancelled.is_set()


def test_redirect_is_never_followed_and_ambient_settings_are_ignored(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://untrusted.invalid:8080")
    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/untrusted-ca.pem")
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://untrusted.invalid"})

    exporter = sink(handler)
    try:
        exporter.emit(start())
        wait_state(exporter, "endpoint_paused")
        assert len(requests) == 1
        assert str(requests[0].url) == ENDPOINT
        assert exporter._client.follow_redirects is False
        assert exporter._client._trust_env is False
    finally:
        exporter.close(0)


def test_mock_read_timeout_retries_same_id_with_uncertainty():
    ids = []

    def handler(request):
        ids.append(json.loads(request.content)["event_id"])
        raise httpx.ReadTimeout("secret response evidence")

    exporter = sink(handler)
    exporter._core._backoff = lambda n: 0
    try:
        exporter.emit(start())
        result = exporter.flush(2)
        assert len(ids) == 3 and len(set(ids)) == 1
        assert result.exhausted_may_have_committed == 1
        assert "secret" not in repr(result)
    finally:
        exporter.close(0)


def test_absolute_and_active_timer_equality_and_pause_stopwatch(monkeypatch):
    c = core(active_delivery_seconds=75, maximum_residence_seconds=900)
    clock = [1000.0]
    monkeypatch.setattr(
        "agent_reliability.adapters._http_delivery.time.monotonic", lambda: clock[0]
    )
    c.emit(start())
    r = send(c)
    clock[0] = 1075
    c.complete(r, 500, error("internal_error"))
    assert c.snapshot().queue_depth == 1
    clock[0] = 1075.001
    assert c.snapshot().recent_records[-1].error_code == "active_time_exceeded"
    c.emit(start("run-2"))
    r = send(c)
    c.complete(r, 404, error("not_found"))
    clock[0] += 900
    assert c.snapshot().queue_depth == 1
    clock[0] += 0.001
    assert c.snapshot().recent_records[-1].error_code == "deployment_unavailable"


def test_ack_wins_at_expired_processing_time_and_tls_reset(monkeypatch):
    c = core()
    c.emit(start())
    r = send(c)
    c.tls_streak = 2
    now = r.accepted + 1000
    monkeypatch.setattr(
        "agent_reliability.adapters._http_delivery.time.monotonic", lambda: now
    )
    c.complete(r, 201, json.dumps(ack(r.event_id)).encode())
    assert c.snapshot().counts_by_disposition[D.COMMITTED] == 1
    assert c.tls_streak == 0


def test_fork_pid_rejected_before_lock_and_release_never_raises(monkeypatch):
    c = core()
    monkeypatch.setattr(
        "agent_reliability.adapters._http_delivery.os.getpid", lambda: c.pid + 1
    )
    with pytest.raises(EventDeliveryRejected, match="fork_unsupported"):
        c.emit(start())
    with pytest.raises(EventDeliveryRejected, match="fork_unsupported"):
        c.begin_close(0)
    c.release_run("run-1")


def test_d13_failure_export_final_health_and_composite_fanout():
    from agent_reliability.adapters.event_sinks import (
        CompositeEventSink,
        InMemoryEventSink,
    )
    from agent_reliability.evaluation import (
        EvaluationExecutionFailure,
        EvaluationFailureStage,
    )

    c = core()
    composite = CompositeEventSink([InMemoryEventSink(), c])
    sdk = AgentReliability(sink=composite)
    with sdk.run(
        agent_id="agent", name="Agent", version="1.0", environment="test"
    ) as handle:
        handle.record_evaluation_failure(
            failure=EvaluationExecutionFailure(
                None, EvaluationFailureStage.EVALUATION, "TimeoutError"
            ),
            indicator="task",
        )
    bodies = [json.loads(r.body) for r in c.records.values()]
    assert [body["payload"]["kind"] for body in bodies] == [
        "run_lifecycle",
        "evaluation_execution_failure",
        "run_lifecycle",
        "measurement_health",
    ]
    assert bodies[-1]["payload"]["health"] == "unavailable"
    assert c.snapshot().active_binding_count == 0


def test_queue_bytes_and_wire_field_rejections():
    c = core(max_queue_bytes=65536 + 1000, closure_reserve_bytes=1000)
    c.emit(start())
    with pytest.raises(EventDeliveryRejected, match="indicator_unsupported"):
        c.emit(EvaluationRecorded("run-1", " task", EvaluationOutcome.PASS, NOW))
    with pytest.raises(EventDeliveryRejected, match="identity_mismatch_local"):
        c.emit(
            RunStarted(
                "run-2", None, AgentIdentity("agent", "Different", "1.0", "test"), NOW
            )
        )
    for _ in range(200):
        try:
            c.emit(EvaluationRecorded("run-1", "task", EvaluationOutcome.PASS, NOW))
        except EventDeliveryRejected as exc:
            assert str(exc) == "queue_full"
            break
    else:
        pytest.fail("byte limit did not reject")
    assert sum(len(r.body) for r in c.records.values()) <= 65536
    c.emit(RunCompleted("run-1", NOW))


def test_tombstones_bounded_and_close_idempotent():
    c = core()
    for index in range(1100):
        c.bindings[str(index)] = (None, time.monotonic())
        c.release_run(str(index))
    assert c.snapshot().terminal_tombstone_count == 1024
    assert c.snapshot().tombstones_evicted == 76
    c.begin_close(0)
    c.begin_close(1)
    assert c.snapshot().terminal_tombstone_count == 0


def test_close_with_current_provider_read_freezes_invalid_label():
    block = threading.Event()
    c = Core(
        Config(
            ENDPOINT,
            lambda: block.wait(1),
            DEPLOYMENT,
            AGENT,
            allow_unrestricted_indicators=True,
        )
    )
    c.emit(start())
    c.take()
    c.begin_close(0)
    assert c.snapshot().pause_reason == "credential_invalid_local"
    block.set()


@pytest.mark.parametrize("join", [False, True])
def test_403_during_refresh_and_resume_join_or_stored_baseline(join):
    block = threading.Event()
    entered = threading.Event()

    def provider():
        entered.set()
        block.wait(1)
        return "changed"

    c = Core(
        Config(
            ENDPOINT, provider, DEPLOYMENT, AGENT, allow_unrestricted_indicators=True
        )
    )
    c.credential = "original"
    c.generation = 1
    c.emit(start())
    c.emit(start("run-2"))
    first = send(c)
    second = send(c)
    c.complete(first, 401, error("authentication_failed"))
    assert entered.wait(1)
    c.complete(second, 403, error("permission_denied"))
    assert c.snapshot().sink_state == "auth_paused"
    read = c.read
    if join:
        assert c.resume_auth_read() is read
    block.set()
    assert read.done.wait(1)
    if join:
        assert c.snapshot().sink_state == "open"
    else:
        assert c.snapshot().sink_state == "auth_paused"
        assert c.credential == "changed" and c.baseline == "original"
        followup = c.resume_auth_read()
        assert followup.done.wait(1)
        assert c.snapshot().sink_state == "open"


def test_legacy_reference_body_and_j2_ignores_library_type():
    from pathlib import Path

    data = json.loads(
        (
            Path(__file__).parents[1] / "fixtures/p28/legacy_platform_responses.json"
        ).read_text()
    )
    response = next(
        row
        for row in data["responses"]
        if row["id"] == "v2-envelope-sent-to-pre-PC2-platform"
    )
    c = core()
    c.emit(start())
    for _ in range(3):
        body = response["body"]
        body["error"]["details"][0].pop("type", None)
        c.complete(send(c), 422, json.dumps(body).encode())
    assert c.snapshot().sink_state == "schema_paused"


@pytest.mark.asyncio
async def test_async_gate_resumes_and_provider_owner_result():
    token = ["secret"]
    statuses = [403, 404, 302, 201]

    async def handler(request):
        status = statuses.pop(0)
        if status == 201:
            return httpx.Response(
                201, json=ack(json.loads(request.content)["event_id"])
            )
        return httpx.Response(
            status,
            json={
                "error": {"code": "not_found" if status == 404 else "permission_denied"}
            },
        )

    exporter = AsyncHTTPEventSink(
        allow_unrestricted_indicators=True,
        endpoint=ENDPOINT,
        credential_provider=lambda: token[0],
        deployment_id=DEPLOYMENT,
        expected_agent=AGENT,
        _transport=httpx.MockTransport(handler),
    )

    async def reach(state):
        async with asyncio.timeout(2):
            while exporter.status.sink_state != state:
                await asyncio.sleep(0.005)

    try:
        exporter.emit(start())
        await reach("auth_paused")
        await exporter.resume_auth()
        assert exporter.status.sink_state == "auth_paused"
        token[0] = "changed"
        await exporter.resume_auth()
        await reach("deployment_unavailable")
        await exporter.resume_deployment()
        await reach("endpoint_paused")
        await exporter.resume_endpoint()
        await exporter.resume_schema()
        assert (await exporter.flush(1)).counts_by_disposition[D.COMMITTED] == 1
    finally:
        await exporter.close(0)
        await exporter._cleanup


@pytest.mark.parametrize(
    "kwargs",
    [
        {"closure_reserve_records": 1000},
        {"closure_reserve_bytes": 4 * 1024 * 1024},
        {"provider_timeout": float("nan")},
        {"retry_max_attempts": True},
        {"active_delivery_seconds": 0},
        {"max_active_run_age": -1},
    ],
)
def test_invalid_config_is_typed_before_workers(kwargs):
    with pytest.raises(ConfigurationError):
        Config(
            ENDPOINT,
            lambda: "secret",
            DEPLOYMENT,
            AGENT,
            **{"allow_unrestricted_indicators": True, **kwargs},
        )


@pytest.mark.parametrize(
    "status,code",
    [
        (400, "domain_error"),
        (409, "conflict"),
        (429, "rate_limited"),
        (422, "validation_error"),
        (500, "internal_error"),
    ],
)
def test_non_ack_deadline_precedes_other_terminal_dispositions(
    monkeypatch, status, code
):
    c = core()
    c.emit(start())
    r = send(c)
    now = r.accepted + 1000
    monkeypatch.setattr(
        "agent_reliability.adapters._http_delivery.time.monotonic", lambda: now
    )
    c.complete(r, status, error(code), ("60",))
    result = c.snapshot()
    assert result.recent_records[-1].disposition == D.RETRY_EXHAUSTED
    assert result.recent_records[-1].error_code == (
        "rate_gated" if status == 429 else "residence_exceeded"
    )

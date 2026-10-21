"""Focused regressions for the independent P28 exporter review findings."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from agent_reliability.adapters.http_event_sink import AsyncHTTPEventSink, HTTPEventSink
from agent_reliability.domain import AgentIdentity
from agent_reliability.ports.events import RunStarted

AGENT = AgentIdentity("agent", "Agent", "1", "test")
BINDING = UUID(int=1)


def event(run_id="run-1"):
    return RunStarted(run_id, None, AGENT, datetime.now(UTC))


def options(handler, **kwargs):
    return dict(
        endpoint="https://example.com/api/v1/evidence/runs",
        credential_provider=lambda: "secret",
        deployment_id=BINDING,
        expected_agent=AGENT,
        _transport=httpx.MockTransport(handler),
        **{"allow_unrestricted_indicators": True, **kwargs},
    )


class BrokenSyncBody(httpx.SyncByteStream):
    def __iter__(self):
        yield b'{"partial":'
        raise httpx.ReadError("sensitive evidence must not appear in diagnostics")


class BrokenAsyncBody(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'{"partial":'
        raise httpx.ReadError("sensitive evidence must not appear in diagnostics")


@pytest.mark.parametrize(
    "status,expected", [(401, "auth_paused"), (403, "auth_paused"), (429, "rate_gated")]
)
def test_known_status_survives_sync_response_read_failure(status, expected):
    exporter = HTTPEventSink(
        **options(
            lambda request: httpx.Response(
                status, headers={"Retry-After": "60"}, stream=BrokenSyncBody()
            ),
            retry_max_attempts=1,
        )
    )
    try:
        exporter.emit(event())
        deadline = time.monotonic() + 1
        while exporter.status.sink_state != expected and time.monotonic() < deadline:
            time.sleep(0.005)
        result = exporter.status
        assert result.sink_state == expected
        assert result.queue_depth == 1
        if status == 429:
            assert (result.resume_not_before - datetime.now(UTC)).total_seconds() > 59
        assert "sensitive evidence" not in repr(result)
    finally:
        exporter.close(0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected", [(401, "auth_paused"), (403, "auth_paused"), (429, "rate_gated")]
)
async def test_known_status_survives_async_response_read_failure(status, expected):
    exporter = AsyncHTTPEventSink(
        **options(
            lambda request: httpx.Response(
                status, headers={"Retry-After": "60"}, stream=BrokenAsyncBody()
            ),
            retry_max_attempts=1,
        )
    )
    try:
        exporter.emit(event())
        async with asyncio.timeout(1):
            while exporter.status.sink_state != expected:
                await asyncio.sleep(0.005)
        result = exporter.status
        assert result.queue_depth == 1
        if status == 429:
            assert (result.resume_not_before - datetime.now(UTC)).total_seconds() > 59
    finally:
        await exporter.close(0)
        await exporter._cleanup


@pytest.mark.asyncio
async def test_async_timers_progress_and_cancel_expired_attempts_without_api_polling():
    entered = []
    cancelled = []

    class HungBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            entered.append(1)
            try:
                await asyncio.Event().wait()
                yield b""
            finally:
                cancelled.append(1)

    exporter = AsyncHTTPEventSink(
        **options(
            lambda request: httpx.Response(201, stream=HungBody()),
            active_delivery_seconds=0.03,
            maximum_residence_seconds=0.2,
        )
    )
    try:
        exporter.emit(event("run-1"))
        exporter.emit(event("run-2"))
        await asyncio.sleep(0.15)
        # The immutable published status must progress without flush/close calls.
        assert len(entered) == 2
        assert exporter.status.queue_depth == 0
        assert len(cancelled) == 2
        assert exporter.status.exhausted_may_have_committed == 2
        assert all(
            row.error_code == "active_time_exceeded"
            for row in exporter.status.recent_records
        )
    finally:
        await exporter.close(0)
        await exporter._cleanup


def test_async_close_awaits_transport_cleanup_before_loop_exit():
    class Transport(httpx.AsyncBaseTransport):
        closed = False

        async def handle_async_request(self, request):
            return httpx.Response(500)

        async def aclose(self):
            await asyncio.sleep(0.01)
            self.closed = True

    transport = Transport()

    async def main():
        config = options(lambda request: httpx.Response(500))
        config["_transport"] = transport
        exporter = AsyncHTTPEventSink(**config)
        await exporter.close(1)

    asyncio.run(main())
    assert transport.closed


def test_native_windows_trust_without_compiled_ca_paths(monkeypatch):
    import ssl

    from agent_reliability.adapters.http_event_sink import _client_options

    cert = ssl.create_default_context().get_ca_certs(binary_form=True)[0]
    defaults = ssl.get_default_verify_paths()._replace(
        openssl_cafile="/absent/p28-ca", openssl_capath="/absent/p28-cas"
    )
    monkeypatch.setattr(ssl, "get_default_verify_paths", lambda: defaults)
    monkeypatch.setattr(
        ssl,
        "enum_certificates",
        lambda store: [(cert, "x509_asn", True)],
        raising=False,
    )
    context = _client_options(None, None)["verify"]
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert len(context.get_ca_certs()) >= 1


@pytest.mark.parametrize("corrected", [False, True])
def test_final_health_is_immutable_after_first_successful_admission(corrected):
    from agent_reliability.adapters._http_delivery import Config, Core
    from agent_reliability.adapters.http_event_sink import EventDeliveryRejected
    from agent_reliability.domain.measurement_health import (
        MeasurementHealthReason,
        MeasurementHealthReport,
    )

    core = Core(
        Config(
            "https://example.com",
            lambda: "secret",
            BINDING,
            AGENT,
            allow_unrestricted_indicators=True,
        )
    )
    core.emit(event())
    core.submit_measurement_health(MeasurementHealthReport(), run_id="run-1")
    report = (
        MeasurementHealthReport.from_reasons(
            frozenset({MeasurementHealthReason.PARTIAL_EVIDENCE})
        )
        if corrected
        else MeasurementHealthReport()
    )
    with pytest.raises(EventDeliveryRejected, match="final_health_already_submitted"):
        core.submit_measurement_health(
            report, run_id="run-1", measurement_id="different-id"
        )
    assert len(core.records) == 2


def test_sync_response_cookies_never_accumulate():
    import json

    def handler(request):
        body = json.loads(request.content)
        assert "cookie" not in request.headers
        return httpx.Response(
            201,
            headers={"Set-Cookie": f"cookie_{body['event_id']}={'x' * 1024}; Path=/"},
            json={
                "event_id": body["event_id"],
                "run_id": str(BINDING),
                "status": "accepted",
                "durability": "committed",
            },
        )

    exporter = HTTPEventSink(**options(handler))
    try:
        for index in range(20):
            exporter.emit(event(f"run-{index}"))
            assert exporter.flush(1).queue_depth == 0
            exporter.release_run(f"run-{index}")
        assert len(exporter._client.cookies) == 0
    finally:
        exporter.close(0)


@pytest.mark.asyncio
async def test_async_response_cookies_never_accumulate():
    import json

    async def handler(request):
        body = json.loads(request.content)
        assert "cookie" not in request.headers
        return httpx.Response(
            201,
            headers={"Set-Cookie": f"cookie_{body['event_id']}={'x' * 1024}; Path=/"},
            json={
                "event_id": body["event_id"],
                "run_id": str(BINDING),
                "status": "accepted",
                "durability": "committed",
            },
        )

    exporter = AsyncHTTPEventSink(**options(handler))
    try:
        for index in range(20):
            exporter.emit(event(f"run-{index}"))
            assert (await exporter.flush(1)).queue_depth == 0
            exporter.release_run(f"run-{index}")
        assert len(exporter._client.cookies) == 0
    finally:
        await exporter.close(1)
        await exporter._cleanup


def test_failed_final_health_admission_can_be_retried_and_marker_is_released():
    import json

    from agent_reliability.adapters._http_delivery import Config, Core
    from agent_reliability.adapters.http_event_sink import EventDeliveryRejected
    from agent_reliability.domain.measurement_health import MeasurementHealthReport
    from agent_reliability.ports.events import RunCompleted

    core = Core(
        Config(
            "https://example.com",
            lambda: "secret",
            BINDING,
            AGENT,
            max_queue_records=2,
            closure_reserve_records=1,
            allow_unrestricted_indicators=True,
        )
    )
    core.credential = "secret"
    core.generation = 1
    core.emit(event())
    core.emit(RunCompleted("run-1", datetime.now(UTC)))
    with pytest.raises(EventDeliveryRejected, match="closure_reserve_exhausted"):
        core.submit_measurement_health(MeasurementHealthReport(), run_id="run-1")
    assert "run-1" not in core.final_health_runs
    record, _credential = core.take()
    core.mark_sent(record)
    core.complete(
        record,
        201,
        json.dumps(
            {
                "event_id": record.event_id,
                "run_id": str(BINDING),
                "status": "accepted",
                "durability": "committed",
            }
        ).encode(),
    )
    core.submit_measurement_health(MeasurementHealthReport(), run_id="run-1")
    assert core.final_health_runs == {"run-1"}
    core.release_run("run-1")
    assert not core.final_health_runs


@pytest.mark.asyncio
async def test_cleanup_timeout_is_bounded_and_a_later_close_can_join():
    class Transport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.release = asyncio.Event()
            self.closed = False

        async def handle_async_request(self, request):
            return httpx.Response(500)

        async def aclose(self):
            await self.release.wait()
            self.closed = True

    transport = Transport()
    config = options(lambda request: httpx.Response(500))
    config["_transport"] = transport
    exporter = AsyncHTTPEventSink(**config)
    before = time.monotonic()
    await exporter.close(0.02)
    assert time.monotonic() - before < 0.15
    assert not transport.closed
    transport.release.set()
    await exporter.close(1)
    assert transport.closed


@pytest.mark.asyncio
async def test_expired_async_requests_release_both_workers_for_later_runs():
    import json

    from agent_reliability.adapters.http_event_sink import DeliveryDisposition

    class HungBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.Event().wait()
            yield b""

    async def handler(request):
        body = json.loads(request.content)
        if body["producer_run_id"] in ("run-1", "run-2"):
            return httpx.Response(201, stream=HungBody())
        return httpx.Response(
            201,
            json={
                "event_id": body["event_id"],
                "run_id": str(BINDING),
                "status": "accepted",
                "durability": "committed",
            },
        )

    exporter = AsyncHTTPEventSink(**options(handler, active_delivery_seconds=0.03))
    try:
        exporter.emit(event("run-1"))
        exporter.emit(event("run-2"))
        exporter.emit(event("run-3"))
        await asyncio.sleep(0.15)
        assert exporter.status.queue_depth == 0
        assert (
            exporter.status.counts_by_disposition[DeliveryDisposition.RETRY_EXHAUSTED]
            == 2
        )
        assert exporter.status.counts_by_disposition[DeliveryDisposition.COMMITTED] == 1
    finally:
        await exporter.close(1)


@pytest.mark.asyncio
async def test_cleanup_exception_is_observed_and_diagnostic_is_redacted(caplog):
    import gc
    import logging

    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return httpx.Response(500)

        async def aclose(self):
            raise RuntimeError("private cleanup detail")

    config = options(lambda request: httpx.Response(500))
    config["_transport"] = Transport()
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()
    unhandled = []
    loop.set_exception_handler(lambda _loop, context: unhandled.append(context))
    try:
        exporter = AsyncHTTPEventSink(**config)
        with caplog.at_level(logging.WARNING):
            result = await exporter.close(1)
        assert result.sink_state == "closed"
        assert exporter._cleanup.done()
        assert not exporter._cleanup._log_traceback
        assert exporter._core.counters["transport_cleanup_failed"] == 1
        assert "transport_cleanup_failed" in caplog.text
        assert "private cleanup detail" not in caplog.text
        del exporter
        gc.collect()
        await asyncio.sleep(0.01)
        assert unhandled == []
    finally:
        loop.set_exception_handler(previous)

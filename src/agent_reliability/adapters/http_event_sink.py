"""Optional HTTPX-backed P28 exporters. Install ``agent-reliability[http]``.

``emit`` admits locally; only a validated acknowledgement means commitment.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import ssl
import threading
import time
from collections.abc import AsyncIterator, Callable, Collection
from http.cookiejar import Cookie, CookieJar, DefaultCookiePolicy
from pathlib import Path
from typing import Any
from uuid import UUID

try:
    import httpx
except ImportError as exc:  # pragma: no cover - exercised by a subprocess test
    raise ImportError(
        "the HTTP evidence exporter needs the optional HTTP transport: "
        "pip install 'agent-reliability[http]'"
    ) from exc

from agent_reliability.adapters._http_delivery import (
    Config,
    ConfigurationError,
    ConfigurationFailedError,
    Core,
    DeliveryDisposition,
    DeliveryRecordStatus,
    DeliveryStatusSnapshot,
    EventDeliveryRejected,
    ExporterClosed,
    Record,
    duration,
    frozen_allowlist,
)
from agent_reliability.adapters._http_protocol import valid_https_endpoint
from agent_reliability.domain import AgentIdentity
from agent_reliability.domain.measurement_health import MeasurementHealthReport
from agent_reliability.evaluation import EvaluationExecutionFailure
from agent_reliability.ports.events import InstrumentationEvent

__all__ = [
    "AsyncHTTPEventSink",
    "ConfigurationError",
    "ConfigurationFailedError",
    "DeliveryDisposition",
    "DeliveryRecordStatus",
    "DeliveryStatusSnapshot",
    "EventDeliveryRejected",
    "ExporterClosed",
    "HTTPEventSink",
]


# Upper bound on reading one response body (the response is capped at 64 KiB, so this
# only bites a peer that trickles bytes). Header trickling is bounded by the transport's
# per-read timeout only; see docs/HTTP_EXPORTER.md.
_BODY_SECONDS = 30.0


class _RejectCookies(DefaultCookiePolicy):
    def set_ok(self, cookie: Cookie, request: Any) -> bool:
        return False

    def return_ok(self, cookie: Cookie, request: Any) -> bool:
        return False


def _load_system_trust(context: ssl.SSLContext) -> None:
    # Native Windows certificate stores do not require compiled OpenSSL paths.
    # Enumerate them directly so SSL_CERT_FILE/DIR cannot alter trust policy.
    enumerate_certificates = getattr(ssl, "enum_certificates", None)
    loaded_native = False
    if enumerate_certificates is not None:
        for store in ("CA", "ROOT"):
            for certificate, encoding, trust in enumerate_certificates(store):
                if encoding == "x509_asn" and (
                    trust is True or ssl.Purpose.SERVER_AUTH.oid in trust
                ):
                    context.load_verify_locations(cadata=certificate)
                    loaded_native = True
    defaults = ssl.get_default_verify_paths()
    cafile: str | None = defaults.openssl_cafile
    capath: str | None = defaults.openssl_capath
    cafile = cafile if cafile and Path(cafile).is_file() else None
    capath = capath if capath and Path(capath).is_dir() else None
    if cafile is not None or capath is not None:
        context.load_verify_locations(cafile=cafile, capath=capath)
    elif not loaded_native:
        raise ConfigurationError("system_trust_unavailable")


def _client_options(proxy: str | None, ca_bundle: Path | None) -> dict[str, Any]:
    if proxy is not None and (
        not isinstance(proxy, str)
        or not (
            valid_https_endpoint(proxy)
            or (
                proxy.startswith("http://")
                and valid_https_endpoint("https://" + proxy[7:])
            )
        )
    ):
        raise ConfigurationError("proxy_invalid")
    try:
        if ca_bundle is not None:
            verify = ssl.create_default_context(cafile=str(ca_bundle))
        else:
            verify = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            _load_system_trust(verify)
    except (OSError, ssl.SSLError, TypeError):
        raise ConfigurationError("ca_bundle_invalid") from None
    return {
        "verify": verify,
        "cookies": CookieJar(policy=_RejectCookies()),
        "proxy": proxy,
        "trust_env": False,
        "follow_redirects": False,
        "timeout": httpx.Timeout(connect=5, read=30, write=10, pool=5),
        "limits": httpx.Limits(max_connections=10, max_keepalive_connections=10),
    }


def _is_proxy_connect(info: dict[str, Any]) -> bool:
    """The tunnel-opening CONNECT to an explicit proxy is not the evidence request.

    Marking it as "sent" would make a TLS failure that occurs afterwards, during the
    handshake with the real endpoint, look like a request that may have committed.
    """

    return bool(getattr(info.get("request"), "method", b"") == b"CONNECT")


def _failure(exc: Exception, record: Record) -> str:
    # httpx/httpcore hide a TLS verification error behind the transport exception:
    # the httpcore error is raised with ``__suppress_context__`` set and no
    # ``__cause__``, so the SSL error is reachable only through ``__context__``.
    # Follow BOTH links with an explicit, bounded, cycle-safe walk and deliberately
    # do NOT honour ``__suppress_context__`` (honouring it would hide exactly this
    # real chain). A verification failure happens during the handshake, before any
    # request byte, so it is only recognised for an attempt that has not sent
    # (``record.sent`` is reset per attempt); a sent attempt keeps the
    # indeterminate/uncertain classification.
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    tls = False
    while pending and len(seen) < 64:
        node = pending.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, ssl.SSLCertVerificationError):
            tls = True
            break
        if node.__cause__ is not None:
            pending.append(node.__cause__)
        if node.__context__ is not None:
            pending.append(node.__context__)
    if tls and not record.sent:
        return "tls_verification_failed"
    return "indeterminate" if record.sent else "network_not_sent"


class HTTPEventSink:
    """Thread-safe enqueue-only sink, two daemon delivery workers.

    Call ``close(timeout)`` explicitly. In-memory records are lost on process
    death. A sink is bound to one exact AgentIdentity and deployment UUID.
    ``endpoint`` is the complete evidence POST URL, not a base URL.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        credential_provider: Callable[[], str],
        deployment_id: UUID,
        expected_agent: AgentIdentity,
        proxy: str | None = None,
        ca_bundle: Path | None = None,
        max_queue_records: int = 1000,
        max_queue_bytes: int = 4 * 1024 * 1024,
        retry_max_attempts: int = 3,
        active_delivery_seconds: float = 75,
        maximum_residence_seconds: float = 900,
        max_throttle_responses: int = 3,
        max_active_run_age: float | None = None,
        closure_reserve_records: int = 50,
        closure_reserve_bytes: int = 3 * 1024 * 1024,
        provider_timeout: float = 60,
        indicator_allowlist: Collection[str] | None = None,
        _transport: httpx.BaseTransport | None = None,
    ) -> None:
        config = Config(
            endpoint,
            credential_provider,
            deployment_id,
            expected_agent,
            max_queue_records,
            max_queue_bytes,
            retry_max_attempts,
            active_delivery_seconds,
            maximum_residence_seconds,
            max_throttle_responses,
            max_active_run_age,
            closure_reserve_records,
            closure_reserve_bytes,
            provider_timeout,
            frozen_allowlist(indicator_allowlist),
        )
        options = _client_options(proxy, ca_bundle)
        self._core = Core(config)
        self._client = httpx.Client(**options, transport=_transport)
        self._wake = threading.Event()
        self._workers = [
            threading.Thread(
                target=self._worker, name=f"gentlity-http-{i}", daemon=True
            )
            for i in range(2)
        ]
        self._workers_left = 2
        for worker in self._workers:
            worker.start()

    def emit(self, event: InstrumentationEvent) -> None:
        self._core.emit(event)
        self._wake.set()

    def submit_evaluation_failure(
        self, failure: EvaluationExecutionFailure, **kwargs: Any
    ) -> None:
        self._core.submit_evaluation_failure(failure, **kwargs)
        self._wake.set()

    def submit_measurement_health(
        self, report: MeasurementHealthReport, **kwargs: Any
    ) -> None:
        self._core.submit_measurement_health(report, **kwargs)
        self._wake.set()

    def release_run(self, run_id: str) -> None:
        self._core.release_run(run_id)

    @property
    def status(self) -> DeliveryStatusSnapshot:
        return self._core.snapshot()

    def flush(self, timeout: float) -> DeliveryStatusSnapshot:
        duration(timeout, "timeout_invalid")
        deadline = time.monotonic() + timeout
        while self.status.queue_depth and time.monotonic() < deadline:
            self._wake.set()
            time.sleep(min(0.01, max(0, deadline - time.monotonic())))
        return self.status

    def close(self, timeout: float) -> DeliveryStatusSnapshot:
        self._core.begin_close(timeout)
        self._wake.set()
        while self.status.sink_state != "closed":
            time.sleep(min(0.01, max(0, self._core.close_deadline - time.monotonic())))
        return self.status

    def resume_auth(self) -> DeliveryStatusSnapshot:
        read = self._core.resume_auth_read()
        if read:
            read.done.wait(
                max(
                    0,
                    self._core.config.provider_timeout
                    - (time.monotonic() - read.started),
                )
            )
        self._wake.set()
        return self.status

    def resume_schema(self) -> DeliveryStatusSnapshot:
        result = self._core.resume("schema_paused")
        self._wake.set()
        return result

    def resume_deployment(self) -> DeliveryStatusSnapshot:
        result = self._core.resume("deployment_unavailable")
        self._wake.set()
        return result

    def resume_endpoint(self) -> DeliveryStatusSnapshot:
        result = self._core.resume("endpoint_paused")
        self._wake.set()
        return result

    def _worker(self) -> None:
        try:
            while True:
                attempt = self._core.take()
                # ``take()`` has just run the timers; reading the lifecycle directly
                # avoids building a full status snapshot (up to 1,000 history rows)
                # every 10 ms.
                if self._core.lifecycle == "closed":
                    return
                if attempt is None:
                    self._wake.wait(0.01)
                    self._wake.clear()
                    continue
                record, credential = attempt
                try:

                    def trace(
                        name: str, info: dict[str, Any], current: Record = record
                    ) -> None:
                        if name.endswith(
                            "send_request_headers.started"
                        ) and not _is_proxy_connect(info):
                            self._core.mark_sent(current)

                    request = self._client.build_request(
                        "POST",
                        self._core.config.endpoint,
                        content=record.body,
                        headers={
                            "Authorization": "Bearer " + credential,
                            "Content-Type": "application/json",
                            "Accept-Encoding": "identity",
                        },
                        extensions={"trace": trace},
                    )
                    request.headers.pop("cookie", None)
                    # Mock transports have no HTTP-core trace; handing the request
                    # to that test boundary is its explicit first-write boundary.
                    if isinstance(self._client._transport, httpx.MockTransport):
                        self._core.mark_sent(record)
                    response = self._client.send(
                        request, stream=True, follow_redirects=False
                    )
                    try:
                        try:
                            data = bytearray()
                            body_deadline = time.monotonic() + _BODY_SECONDS
                            for chunk in (
                                (response.content,)
                                if response.is_stream_consumed
                                # No chunk_size: httpx would buffer a trickling peer's
                                # bytes until 4 KiB arrive and hide the slow read.
                                else response.iter_raw()
                            ):
                                if (
                                    len(data) + len(chunk) > 65536
                                    or time.monotonic() > body_deadline
                                ):
                                    # Oversized, or trickled past the body budget:
                                    # never an acknowledgement.
                                    data = bytearray(b" " * 65537)
                                    break
                                data.extend(chunk)
                        except Exception:
                            data = bytearray()
                        self._core.complete(
                            record,
                            response.status_code,
                            bytes(data),
                            tuple(response.headers.get_list("retry-after")),
                        )
                    finally:
                        with contextlib.suppress(Exception):
                            response.close()
                except Exception as exc:
                    self._core.complete(record, failure=_failure(exc, record))
                finally:
                    credential = ""
        finally:
            with self._core.lock:
                self._workers_left -= 1
                last = self._workers_left == 0
            if last:
                with contextlib.suppress(Exception):
                    self._client.close()

    def __enter__(self) -> HTTPEventSink:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close(5)


class AsyncHTTPEventSink:
    """Native async transport; mutations belong to the creating loop/thread.

    Only ``status`` and ``release_run`` may be called from other threads.
    Credential calls use the dedicated daemon helper, never a loop executor.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        credential_provider: Callable[[], str],
        deployment_id: UUID,
        expected_agent: AgentIdentity,
        proxy: str | None = None,
        ca_bundle: Path | None = None,
        max_queue_records: int = 1000,
        max_queue_bytes: int = 4 * 1024 * 1024,
        retry_max_attempts: int = 3,
        active_delivery_seconds: float = 75,
        maximum_residence_seconds: float = 900,
        max_throttle_responses: int = 3,
        max_active_run_age: float | None = None,
        closure_reserve_records: int = 50,
        closure_reserve_bytes: int = 3 * 1024 * 1024,
        provider_timeout: float = 60,
        indicator_allowlist: Collection[str] | None = None,
        _transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._loop = asyncio.get_running_loop()
        self._thread = threading.get_ident()
        config = Config(
            endpoint,
            credential_provider,
            deployment_id,
            expected_agent,
            max_queue_records,
            max_queue_bytes,
            retry_max_attempts,
            active_delivery_seconds,
            maximum_residence_seconds,
            max_throttle_responses,
            max_active_run_age,
            closure_reserve_records,
            closure_reserve_bytes,
            provider_timeout,
            frozen_allowlist(indicator_allowlist),
        )
        self._core = Core(config)
        self._core.provider_dispatch = self._provider_result
        self._client = httpx.AsyncClient(
            **_client_options(proxy, ca_bundle), transport=_transport
        )
        self._snapshot = self._core.snapshot()
        self._attempts: dict[str, asyncio.Task[None]] = {}
        self._tasks = [self._loop.create_task(self._worker()) for _ in range(2)]
        self._timer = self._loop.create_task(self._maintain())
        self._cleanup: asyncio.Task[None] | None = None

    def _provider_result(self, action: Callable[[], None]) -> None:
        def apply() -> None:
            action()
            self._publish()

        with contextlib.suppress(RuntimeError):
            self._loop.call_soon_threadsafe(apply)

    def _owner(self) -> None:
        if os.getpid() != self._core.pid:
            raise EventDeliveryRejected("fork_unsupported")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise EventDeliveryRejected("owner_loop_required") from None
        if threading.get_ident() != self._thread or loop is not self._loop:
            raise EventDeliveryRejected("owner_loop_required")

    def _publish(self) -> DeliveryStatusSnapshot:
        self._snapshot = self._core.snapshot()
        return self._snapshot

    @property
    def status(self) -> DeliveryStatusSnapshot:
        return self._snapshot

    def emit(self, event: InstrumentationEvent) -> None:
        self._owner()
        self._core.emit(event)
        self._publish()

    def submit_evaluation_failure(
        self, failure: EvaluationExecutionFailure, **kwargs: Any
    ) -> None:
        self._owner()
        self._core.submit_evaluation_failure(failure, **kwargs)
        self._publish()

    def submit_measurement_health(
        self, report: MeasurementHealthReport, **kwargs: Any
    ) -> None:
        self._owner()
        self._core.submit_measurement_health(report, **kwargs)
        self._publish()

    def release_run(self, run_id: str) -> None:
        def release() -> None:
            self._core.release_run(run_id)
            self._publish()

        if self._loop.is_closed():
            return
        try:
            self._loop.call_soon_threadsafe(release)
        except RuntimeError:
            return

    async def flush(self, timeout: float) -> DeliveryStatusSnapshot:
        self._owner()
        duration(timeout, "timeout_invalid")
        deadline = time.monotonic() + timeout
        while self._publish().queue_depth and time.monotonic() < deadline:
            await asyncio.sleep(min(0.01, max(0, deadline - time.monotonic())))
        return self._publish()

    async def close(self, timeout: float) -> DeliveryStatusSnapshot:
        self._owner()
        deadline = time.monotonic() + duration(timeout, "timeout_invalid")
        cancelled = False
        self._core.begin_close(timeout)
        try:
            while self._publish().sink_state != "closed":
                await asyncio.sleep(
                    min(0.01, max(0, self._core.close_deadline - time.monotonic()))
                )
        except asyncio.CancelledError:
            cancelled = True
            with self._core.lock:
                self._core.close_deadline = time.monotonic()
                self._core.tick()
            raise
        finally:
            if self._core.lifecycle == "closed" and self._cleanup is None:
                for task in self._tasks:
                    task.cancel()
                self._cleanup = self._loop.create_task(self._dispose())
            self._publish()
            remaining = max(0.0, deadline - time.monotonic())
            if self._cleanup is not None and not cancelled and remaining:
                # wait() does not cancel shared cleanup on caller cancellation
                # or timeout. Concurrent/idempotent close calls can join it.
                await asyncio.wait((self._cleanup,), timeout=remaining)
        return self._snapshot

    async def _dispose(self) -> None:
        try:
            self._timer.cancel()
            await asyncio.gather(*self._tasks, self._timer, return_exceptions=True)
            await self._client.aclose()
        except Exception:
            # Never retain a raw cleanup exception in an unobserved task or
            # expose its request/credential details through loop diagnostics.
            with self._core.lock:
                self._core.counters["transport_cleanup_failed"] += 1
            with contextlib.suppress(Exception):
                logging.getLogger(__name__).warning("transport_cleanup_failed")

    async def resume_auth(self) -> DeliveryStatusSnapshot:
        self._owner()
        read = self._core.resume_auth_read()
        while read and not read.done.is_set():
            self._publish()
            await asyncio.sleep(0.005)
        return self._publish()

    async def resume_schema(self) -> DeliveryStatusSnapshot:
        self._owner()
        self._core.resume("schema_paused")
        return self._publish()

    async def resume_deployment(self) -> DeliveryStatusSnapshot:
        self._owner()
        self._core.resume("deployment_unavailable")
        return self._publish()

    async def resume_endpoint(self) -> DeliveryStatusSnapshot:
        self._owner()
        self._core.resume("endpoint_paused")
        return self._publish()

    async def _chunks(self, response: httpx.Response) -> AsyncIterator[bytes]:
        if response.is_stream_consumed:
            yield response.content
        else:
            async for chunk in response.aiter_raw(chunk_size=4096):
                yield chunk

    async def _worker(self) -> None:
        while True:
            attempt = self._core.take()
            if self._publish().sink_state == "closed":
                return
            if attempt is None:
                await asyncio.sleep(0.01)
                continue
            record, credential = attempt
            delivery = self._loop.create_task(self._deliver(record, credential))
            self._attempts[record.event_id] = delivery
            try:
                await delivery
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise
                # The maintenance task cancelled an expired delivery. The
                # worker remains available for another run's queued records.
            finally:
                self._attempts.pop(record.event_id, None)

    async def _maintain(self) -> None:
        while True:
            snapshot = self._publish()
            for event_id, task in tuple(self._attempts.items()):
                if event_id not in self._core.records:
                    task.cancel()
            if snapshot.sink_state == "closed":
                return
            await asyncio.sleep(0.005)

    async def _deliver(self, record: Record, credential: str) -> None:
        try:

            async def trace(
                name: str, info: dict[str, Any], current: Record = record
            ) -> None:
                if name.endswith(
                    "send_request_headers.started"
                ) and not _is_proxy_connect(info):
                    self._core.mark_sent(current)

            request = self._client.build_request(
                "POST",
                self._core.config.endpoint,
                content=record.body,
                headers={
                    "Authorization": "Bearer " + credential,
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
                extensions={"trace": trace},
            )
            request.headers.pop("cookie", None)
            if isinstance(self._client._transport, httpx.MockTransport):
                self._core.mark_sent(record)
            response = await self._client.send(
                request, stream=True, follow_redirects=False
            )
            try:
                try:
                    data = bytearray()
                    async for chunk in self._chunks(response):
                        if len(data) + len(chunk) > 65536:
                            data = bytearray(b" " * 65537)
                            break
                        data.extend(chunk)
                except Exception:
                    data = bytearray()
                self._core.complete(
                    record,
                    response.status_code,
                    bytes(data),
                    tuple(response.headers.get_list("retry-after")),
                )
            finally:
                with contextlib.suppress(Exception):
                    await response.aclose()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._core.complete(record, failure=_failure(exc, record))
        finally:
            credential = ""
            self._publish()

    async def __aenter__(self) -> AsyncHTTPEventSink:
        self._owner()
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.close(5)

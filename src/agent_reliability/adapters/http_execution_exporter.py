"""Experimental bounded HTTP exporter for content-free execution facts.

One daemon worker, an in-memory job queue bounded by count and bytes, idempotent
retries of identical bytes with jittered backoff, and fixed-label diagnostics. It never
blocks or raises into application code and never reports a response body, URL or
credential. Delivery is best-effort: queued jobs are lost if the process dies.
"""

from __future__ import annotations

import contextlib
import json
import random
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from agent_reliability.adapters._http_delivery import ConfigurationError
from agent_reliability.adapters._http_protocol import (
    loopback_url,
    retry_after,
    valid_https_endpoint,
)
from agent_reliability.adapters.http_event_sink import _client_options
from agent_reliability.experimental.instrumentation.export import (
    SOURCE,
    ExportRequest,
    build_requests,
)
from agent_reliability.experimental.instrumentation.model import (
    MAX_COUNT,
    ExecutionTrace,
)

_MAX_RESPONSE = 65536
_MAX_RETRY_AFTER = 30.0
_RETRYABLE = frozenset({408, 425, 429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class ExecutionDeliveryStatus:
    """Counters and the last fixed-label error. Never contains evidence or secrets."""

    closed: bool
    queued_jobs: int
    submitted_jobs: int
    delivered_jobs: int
    failed_jobs: int
    dropped_queue_full: int
    dropped_closed: int
    abandoned_jobs: int
    requests_accepted: int
    requests_duplicate: int
    requests_rejected: int
    retries: int
    retry_exhausted: int
    last_error: str | None


class ExecutionHTTPExporter:
    """Submit finished traces to the platform's execution endpoints.

    Needs a machine credential with the ``execution:ingest`` and
    ``execution_resource:ingest`` scopes (the latter only if token usage is reported).
    ``base_url`` is the scheme and authority only; paths are fixed by the contract.
    """

    def __init__(
        self,
        *,
        base_url: str,
        credential_provider: Callable[[], str],
        deployment_id: UUID,
        source: str = SOURCE,
        proxy: str | None = None,
        ca_bundle: Path | None = None,
        max_queue_jobs: int = 64,
        max_queue_bytes: int = 2 * 1024 * 1024,
        retry_max_attempts: int = 3,
        request_deadline_seconds: float = 30.0,
        _transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not isinstance(base_url, str):
            raise ConfigurationError("endpoint_invalid")
        parts = urlsplit(base_url)
        authority_only = (
            not parts.path.strip("/") and not parts.query and not parts.fragment
        )
        probe = base_url.rstrip("/")
        if not authority_only or not (
            valid_https_endpoint(probe)
            or loopback_url(probe, literal_only=True) == "accept"
        ):
            raise ConfigurationError("endpoint_invalid")
        if not callable(credential_provider) or not isinstance(deployment_id, UUID):
            raise ConfigurationError("binding_invalid")
        if (
            not isinstance(source, str)
            or not 1 <= len(source) <= 100
            or any(not "!" <= c <= "~" for c in source)
        ):
            raise ConfigurationError("source_invalid")
        for value, low, high in (
            (max_queue_jobs, 1, 1024),
            (max_queue_bytes, 1024, 64 * 1024 * 1024),
            (retry_max_attempts, 1, 10),
        ):
            if type(value) is not int or not low <= value <= high:
                raise ConfigurationError("capacity_invalid")
        if (
            type(request_deadline_seconds) not in (int, float)
            or not 1 <= request_deadline_seconds <= 120
        ):
            raise ConfigurationError("capacity_invalid")
        self._base = probe
        self._credential = credential_provider
        self._deployment = str(deployment_id)
        self._source = source
        self._max_jobs = max_queue_jobs
        self._max_bytes = max_queue_bytes
        self._attempts = retry_max_attempts
        options = _client_options(proxy, ca_bundle)
        options["timeout"] = httpx.Timeout(
            connect=5,
            read=request_deadline_seconds,
            write=10,
            pool=5,
        )
        self._client = httpx.Client(**options, transport=_transport)
        self._cond = threading.Condition()
        self._jobs: deque[list[ExportRequest]] = deque()
        self._queued_bytes = 0
        self._busy = False
        self._stop = False
        self._abandon = False
        self._status = ExecutionDeliveryStatus(
            False, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, None
        )
        self._random = random.Random()
        self._worker = threading.Thread(
            target=self._run, name="gentlity-execution-export", daemon=True
        )
        self._worker.start()

    # -- public ----------------------------------------------------------------

    @property
    def status(self) -> ExecutionDeliveryStatus:
        with self._cond:
            return replace(self._status, queued_jobs=len(self._jobs))

    def submit(self, trace: ExecutionTrace) -> bool:
        """Admit one trace's requests. Never blocks on I/O; False when not admitted."""
        try:
            requests = build_requests(
                trace, deployment_id=self._deployment, source=self._source
            )
        except Exception:
            self._count("failed_jobs", error="build_failed")
            return False
        if not requests:
            return True
        size = sum(len(r.body) for r in requests)
        with self._cond:
            if self._stop:
                self._bump("dropped_closed")
                return False
            if (
                len(self._jobs) >= self._max_jobs
                or self._queued_bytes + size > self._max_bytes
            ):
                self._bump("dropped_queue_full")
                self._status = replace(self._status, last_error="queue_full")
                return False
            self._jobs.append(requests)
            self._queued_bytes += size
            self._bump("submitted_jobs")
            self._cond.notify_all()
        return True

    def flush(self, timeout: float) -> ExecutionDeliveryStatus:
        """Wait up to ``timeout`` seconds for the queue to drain."""
        deadline = time.monotonic() + max(0.0, timeout)
        with self._cond:
            while self._jobs or self._busy:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
        return self.status

    def close(self, timeout: float) -> ExecutionDeliveryStatus:
        """Flush, then stop; jobs still queued at the deadline are abandoned."""
        self.flush(timeout)
        with self._cond:
            self._stop = True
            self._abandon = True
            self._cond.notify_all()
        self._worker.join(max(0.0, min(timeout, 5.0)) or 0.1)
        with self._cond:
            if self._jobs:
                self._bump("abandoned_jobs", len(self._jobs))
                self._jobs.clear()
                self._queued_bytes = 0
            self._status = replace(self._status, closed=True)
        with contextlib.suppress(Exception):
            self._client.close()
        return self.status

    def __enter__(self) -> ExecutionHTTPExporter:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close(5)

    # -- internals -------------------------------------------------------------

    def _bump(self, field: str, amount: int = 1) -> None:
        # caller holds the condition lock
        self._status = replace(
            self._status,
            **{field: min(MAX_COUNT, getattr(self._status, field) + amount)},
        )

    def _count(self, field: str, *, error: str | None = None) -> None:
        with self._cond:
            self._bump(field)
            if error is not None:
                self._status = replace(self._status, last_error=error)

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._jobs and not self._stop:
                    self._cond.wait(0.5)
                if self._abandon or (self._stop and not self._jobs):
                    return
                job = self._jobs.popleft()
                self._queued_bytes -= sum(len(r.body) for r in job)
                self._busy = True
            try:
                self._deliver(job)
            except Exception:
                self._count("failed_jobs", error="internal")
            finally:
                with self._cond:
                    self._busy = False
                    self._cond.notify_all()

    def _deliver(self, job: list[ExportRequest]) -> None:
        for request in job:
            result = self._send(request)
            if result != "ok":
                self._count("failed_jobs", error=result)
                return
        self._count("delivered_jobs")

    def _send(self, request: ExportRequest) -> str:
        label = "network"
        for attempt in range(self._attempts):
            if self._abandon:
                return "abandoned"
            if attempt:
                self._count("retries")
            delay: float | None = None
            try:
                token = self._credential()
                if not isinstance(token, str) or not token:
                    return "credential_unavailable"
            except Exception:
                return "credential_unavailable"
            try:
                response = self._client.send(
                    self._client.build_request(
                        "POST",
                        self._base + request.path,
                        content=request.body,
                        headers={
                            "Authorization": "Bearer " + token,
                            "Content-Type": "application/json",
                            "Accept-Encoding": "identity",
                        },
                    ),
                    stream=True,
                    follow_redirects=False,
                )
            except Exception:
                label = "network"
            else:
                try:
                    status = response.status_code
                    body = self._read(response)
                    header = tuple(response.headers.get_list("retry-after"))
                finally:
                    with contextlib.suppress(Exception):
                        response.close()
                token = ""
                if status in (200, 201):
                    if self._acknowledged(status, body):
                        self._count(
                            "requests_accepted"
                            if status == 201
                            else "requests_duplicate"
                        )
                        return "ok"
                    self._count("requests_rejected")
                    return "bad_acknowledgement"
                if status in _RETRYABLE:
                    label = f"http_{status}"
                    seconds = retry_after(header, grammar="RA-a")
                    delay = None if seconds is None else min(_MAX_RETRY_AFTER, seconds)
                else:
                    self._count("requests_rejected")
                    return f"http_{status}"
            if attempt + 1 < self._attempts:
                pause = (
                    delay
                    if delay is not None
                    else self._random.uniform(0, min(2.0, 0.1 * (2**attempt)))
                )
                time.sleep(pause)
        self._count("retry_exhausted")
        return label

    @staticmethod
    def _read(response: httpx.Response) -> bytes:
        data = bytearray()
        try:
            for chunk in (
                (response.content,)
                if response.is_stream_consumed
                else response.iter_raw()
            ):
                if len(data) + len(chunk) > _MAX_RESPONSE:
                    return b""
                data.extend(chunk)
        except Exception:
            return b""
        return bytes(data)

    @staticmethod
    def _acknowledged(status: int, body: bytes) -> bool:
        try:
            value = json.loads(body.decode("utf-8", errors="strict"))
        except (ValueError, RecursionError):
            return False
        return isinstance(value, dict) and value.get("status") == (
            "accepted" if status == 201 else "duplicate"
        )

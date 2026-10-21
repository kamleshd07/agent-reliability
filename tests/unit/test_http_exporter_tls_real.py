"""D-1 regression: TLS verification failures produced by REAL handshakes.

The classifier must recognise a certificate-verification failure as raised by real
httpx/httpcore, where the ``ssl.SSLCertVerificationError`` is reachable only through
``__context__`` (the httpcore exception is raised with ``__suppress_context__`` set
and no ``__cause__``). Every failure below comes from an actual handshake against a
local TLS server using certificates generated for the test session (no key is
stored in the repository or shipped); no exception chain is built by hand except
in the explicit chain-walk property tests.
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import shutil
import socket
import ssl
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpcore
import httpx
import pytest

from agent_reliability.adapters.http_event_sink import (
    AsyncHTTPEventSink,
    DeliveryDisposition,
    HTTPEventSink,
    _client_options,
    _failure,
)
from agent_reliability.domain import AgentIdentity
from agent_reliability.ports.events import RunCompleted, RunStarted

AGENT = AgentIdentity("agent", "Agent", "1", "test")
BINDING = UUID("00000000-0000-4000-8000-000000000007")
D = DeliveryDisposition
UNSENT = SimpleNamespace(sent=False)
SENT = SimpleNamespace(sent=True)
TOKEN = "are_machine_test-credential-must-not-leak"

# Disposable certificates are generated for every test session; no private key is stored
# in the repository or shipped in any distribution artifact. ``cryptography`` is a
# development-only dependency (``pip install -e ".[dev]"``).
x509 = pytest.importorskip("cryptography.x509", reason="install the dev extra")
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID  # noqa: E402

_START = datetime(2020, 1, 1, tzinfo=UTC)
_END = datetime(2120, 1, 1, tzinfo=UTC)
_EXPIRED_END = datetime(2021, 1, 1, tzinfo=UTC)


def _name(common: str) -> Any:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common)])


def _key_usage(*, ca: bool) -> Any:
    return x509.KeyUsage(
        digital_signature=not ca,
        key_encipherment=False,
        content_commitment=False,
        data_encipherment=False,
        key_agreement=False,
        key_cert_sign=ca,
        crl_sign=ca,
        encipher_only=False,
        decipher_only=False,
    )


def _generate_tls_material(directory: Path) -> dict[str, tuple[Path, Path]]:
    """Throwaway CA plus leaves: good, wrong hostname, expired, self-signed.

    Certificates carry the extensions Python 3.13's strict verification requires.
    Validity windows are fixed, so there is no time bomb: valid 2020..2120, expired
    ends 2021. The CA private key is never written to disk.
    """

    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(_name("p28-test-ca"))
        .issuer_name(_name("p28-test-ca"))
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_START)
        .not_valid_after(_END)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(_key_usage(ca=True), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_path = directory / "ca.crt"
    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    material: dict[str, tuple[Path, Path]] = {"CA": (ca_path, ca_path)}

    def leaf(stem: str, dns: str, *, signer: Any, end: datetime, issuer: Any) -> None:
        key = ec.generate_private_key(ec.SECP256R1())
        cert = (
            x509.CertificateBuilder()
            .subject_name(_name(dns))
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_START)
            .not_valid_after(end)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(dns)]), False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .add_extension(_key_usage(ca=False), critical=True)
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    (signer or key).public_key()
                ),
                False,
            )
            .sign(signer or key, hashes.SHA256())
        )
        crt, pem = directory / f"{stem}.crt", directory / f"{stem}.key"
        crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        pem.touch(mode=0o600)
        pem.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        material[stem] = (crt, pem)

    leaf("localhost", "localhost", signer=ca_key, end=_END, issuer=ca_cert.subject)
    leaf("other", "other.example", signer=ca_key, end=_END, issuer=ca_cert.subject)
    leaf(
        "expired", "localhost", signer=ca_key, end=_EXPIRED_END, issuer=ca_cert.subject
    )
    leaf("selfsigned", "localhost", signer=None, end=_END, issuer=_name("localhost"))
    return material


_TLS_DIR = Path(tempfile.mkdtemp(prefix="p28-tls-test-"))
atexit.register(shutil.rmtree, _TLS_DIR, True)
_MATERIAL = _generate_tls_material(_TLS_DIR)
CA = _MATERIAL["CA"][0]


def _context(stem: str) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    crt, key = _MATERIAL[stem]
    context.load_cert_chain(crt, key)
    return context


# plan letters -> server certificate
_CERTS = {
    "G": "localhost",  # good: valid for localhost (chains to the test CA)
    "W": "other",  # wrong hostname
    "E": "expired",
    "S": "selfsigned",
    "X": "localhost",  # never used for TLS: the connection is closed immediately
}


class TlsServer:
    """Threaded loopback TLS server; connection N uses plan[N] (last letter repeats).

    A connection whose handshake the client rejects never reaches ``requests``. A
    connection that completes the handshake reads one HTTP request and answers 500.
    """

    def __init__(self, plan: str) -> None:
        self.plan = plan
        self.contexts = {letter: _context(stem) for letter, stem in _CERTS.items()}
        self.connections = 0
        self.requests: list[bytes] = []
        self._lock = threading.Lock()
        self._socket = socket.socket()
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen(16)
        self.port: int = self._socket.getsockname()[1]
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    @property
    def endpoint(self) -> str:
        return f"https://localhost:{self.port}/api/v1/evidence/runs"

    def _serve(self) -> None:
        while not self._stop:
            try:
                conn, _ = self._socket.accept()
            except OSError:
                return
            with self._lock:
                index = self.connections
                self.connections += 1
            letter = self.plan[min(index, len(self.plan) - 1)]
            threading.Thread(
                target=self._handle, args=(conn, letter), daemon=True
            ).start()

    def _handle(self, conn: socket.socket, letter: str) -> None:
        if letter == "X":  # plain TCP close before any TLS: an ordinary network failure
            conn.close()
            return
        try:
            conn.settimeout(5)
            tls = self.contexts[letter].wrap_socket(conn, server_side=True)
        except (ssl.SSLError, OSError):
            conn.close()
            return
        try:
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = tls.recv(65536)
                if not chunk:
                    break
                data += chunk
            with self._lock:
                self.requests.append(data)
            body = b'{"error":{"code":"internal_error","message":"x"}}'
            tls.sendall(
                b"HTTP/1.1 500 Internal Server Error\r\n"
                b"content-type: application/json\r\n"
                b"connection: close\r\ncontent-length: "
                + str(len(body)).encode()
                + b"\r\n\r\n"
                + body
            )
            # Orderly shutdown: let the client finish reading the response before the
            # socket closes; a reset would turn a completed exchange into an
            # "indeterminate" failure, which legitimately does not reset the streak.
            tls.shutdown(socket.SHUT_WR)
            tls.settimeout(2)
            while tls.recv(4096):
                pass
        except (ssl.SSLError, OSError):
            pass
        finally:
            tls.close()

    def close(self) -> None:
        self._stop = True
        self._socket.close()


def _real_error(url: str, ca: Path | None) -> Exception:
    client = httpx.Client(**_client_options(None, ca))
    try:
        client.post(
            url, content=b"{}", headers={"Authorization": "Bearer " + TOKEN}, timeout=5
        )
    except Exception as error:
        return error
    finally:
        client.close()
    raise AssertionError("request unexpectedly succeeded")


def _wait(predicate, timeout: float = 90.0) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return bool(predicate())


def _bounded(call, seconds: float = 10.0):  # type: ignore[no-untyped-def]
    """Run ``call`` with a deadline: a regression fails instead of hanging."""

    outcome: list[object] = []
    worker = threading.Thread(target=lambda: outcome.append(call()), daemon=True)
    worker.start()
    worker.join(seconds)
    assert not worker.is_alive(), "classifier did not terminate (unbounded traversal)"
    return outcome[0]


def _sink(server: TlsServer, **kwargs) -> HTTPEventSink:  # type: ignore[no-untyped-def]
    sink = HTTPEventSink(
        allow_unrestricted_indicators=True,
        endpoint=server.endpoint,
        credential_provider=lambda: TOKEN,
        deployment_id=BINDING,
        expected_agent=AGENT,
        ca_bundle=CA,
        **kwargs,
    )
    # Same test seam the existing exporter tests use: no random retry delay, so these
    # tests do not depend on wall-clock backoff under a loaded machine.
    sink._core._backoff = lambda _n: 0
    return sink


def _emit_run(sink, run_id: str = "run-1", *, complete: bool = True) -> None:  # type: ignore[no-untyped-def]
    sink.emit(RunStarted(run_id, None, AGENT, datetime.now(UTC)))
    if complete:
        sink.emit(RunCompleted(run_id, datetime.now(UTC)))


def _paused(sink) -> bool:  # type: ignore[no-untyped-def]
    return sink.status.counts_by_disposition.get(D.ENDPOINT_PAUSED, 0) > 0


# ------------------------------------------------- classification of real failures
@pytest.mark.parametrize(
    ("plan", "ca"),
    [
        ("G", None),  # untrusted CA: valid certificate, client trusts only system roots
        ("W", CA),  # wrong hostname
        ("E", CA),  # expired
        ("S", CA),  # self-signed leaf, not a trust anchor
    ],
    ids=["untrusted_ca", "wrong_hostname", "expired", "self_signed"],
)
def test_real_verification_failures_are_tls_verification_failed(
    plan: str, ca: Path | None
) -> None:
    server = TlsServer(plan)
    try:
        error = _real_error(server.endpoint, ca)
        assert _failure(error, UNSENT) == "tls_verification_failed"
        # The D-1 premise, on the REAL httpcore exception: it has no __cause__, its
        # context is suppressed, and the SSL error is only on __context__.
        inner = error.__cause__
        assert isinstance(inner, httpcore.ConnectError)
        assert inner.__cause__ is None and inner.__suppress_context__ is True
        assert isinstance(inner.__context__, ssl.SSLCertVerificationError)
        assert (
            server.requests == []
        )  # no HTTP bytes (so no credential) after the failure
    finally:
        server.close()


def test_connection_refused_is_not_tls() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    error = _real_error(f"https://localhost:{port}/x", CA)
    assert _failure(error, UNSENT) == "network_not_sent"


def test_tcp_close_during_handshake_is_not_tls() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)

    def accept() -> None:
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            conn.close()

    threading.Thread(target=accept, daemon=True).start()
    try:
        error = _real_error(f"https://localhost:{listener.getsockname()[1]}/x", CA)
        assert _failure(error, UNSENT) == "network_not_sent"
    finally:
        listener.close()


def test_an_attempt_that_sent_a_request_stays_indeterminate() -> None:
    assert _failure(httpx.ReadTimeout("x"), SENT) == "indeterminate"
    verification = ssl.SSLCertVerificationError(1, "verify failed")
    try:
        try:
            raise verification
        except ssl.SSLCertVerificationError:
            raise httpx.ConnectError("transport") from None
    except httpx.ConnectError as error:
        assert _failure(error, SENT) == "indeterminate"


# -------------------------------------------------------- chain-walk properties
def _hidden_verification_error() -> httpx.ConnectError:
    """Same shape as real httpx/httpcore: SSL error only on ``__context__``, hidden."""

    verification = ssl.SSLCertVerificationError(1, "verify failed")
    try:
        try:
            raise verification
        except ssl.SSLCertVerificationError:
            raise httpx.ConnectError("transport") from None
    except httpx.ConnectError as error:
        return error
    raise AssertionError


def test_context_suppression_does_not_hide_the_verification_error() -> None:
    error = _hidden_verification_error()
    assert error.__cause__ is None and error.__suppress_context__ is True
    assert _failure(error, UNSENT) == "tls_verification_failed"


def test_both_links_are_followed() -> None:
    verification = ssl.SSLCertVerificationError(1, "verify failed")
    outer = httpx.ConnectError("x")
    outer.__cause__ = Exception("dead end")
    outer.__context__ = verification
    assert _failure(outer, UNSENT) == "tls_verification_failed"
    other = httpx.ConnectError("y")
    other.__cause__ = verification
    other.__context__ = Exception("dead end")
    assert _failure(other, UNSENT) == "tls_verification_failed"


def test_traversal_is_cycle_safe_and_bounded() -> None:
    a, b = Exception("a"), Exception("b")
    a.__context__, b.__context__ = b, a
    assert _bounded(lambda: _failure(a, UNSENT)) == "network_not_sent"
    head = node = Exception("0")
    for index in range(10_000):
        nxt = Exception(str(index))
        node.__context__ = nxt
        node = nxt
    node.__context__ = ssl.SSLCertVerificationError(1, "too deep to be found")
    # beyond the 64-node bound
    assert _bounded(lambda: _failure(head, UNSENT)) == "network_not_sent"


# ---------------------------------------- endpoint pause at exactly the third failure
def test_endpoint_pauses_on_exactly_the_third_consecutive_failure() -> None:
    server = TlsServer("WWWG")
    sink = _sink(server)
    try:
        _emit_run(sink)
        assert _wait(lambda: _paused(sink))
        time.sleep(0.3)  # a fourth attempt would show up here
        assert server.connections == 3 and server.requests == []
        assert sink.status.pause_reason is not None
        assert TOKEN not in repr(sink.status)  # diagnostics never carry the credential
        assert sink.status.queue_depth >= 2  # held for explicit recovery, not dropped
        sink.resume_endpoint()
        # After the explicit resume the fourth handshake verifies and the credential is
        # sent for the first time - never over an unverified channel.
        assert _wait(lambda: len(server.requests) >= 1)
        assert b"authorization: bearer " in server.requests[0].lower()
        assert not _paused(sink)
    finally:
        sink.close(1)
        server.close()


def test_two_failures_do_not_pause() -> None:
    server = TlsServer("WWG")
    sink = _sink(server)
    try:
        _emit_run(sink, complete=False)
        assert _wait(lambda: len(server.requests) >= 1)
        assert not _paused(sink)
        assert server.connections >= 3
    finally:
        sink.close(1)
        server.close()


def test_a_completed_exchange_resets_the_failure_streak() -> None:
    # W W (verified exchange) W W (verified exchange): four failures, never three in
    # a row.
    server = TlsServer("WWGWWG")
    sink = _sink(server)
    try:
        _emit_run(sink)  # two records
        assert _wait(lambda: server.connections >= 6 and len(server.requests) >= 2)
        assert not _paused(sink)
        assert sink.status.counts_by_disposition.get(D.RETRY_EXHAUSTED, 0) >= 1
    finally:
        sink.close(1)
        server.close()


def test_sent_flag_is_per_attempt_so_a_later_verification_failure_still_counts() -> (
    None
):
    # Connection 0 completes an exchange (the request is SENT, answered 500). The next
    # three handshakes fail verification. Because ``record.sent`` is reset for every
    # attempt, they are recognised as TLS failures and pause the endpoint on the third
    # (the fourth connection). If ``sent`` leaked from the first attempt they would be
    # labelled "indeterminate", never count, and delivery would never pause.
    server = TlsServer("GWWW")
    sink = _sink(server, retry_max_attempts=10)
    try:
        _emit_run(sink, complete=False)
        assert _wait(lambda: _paused(sink))
        assert server.connections == 4 and len(server.requests) == 1
    finally:
        sink.close(1)
        server.close()


def test_resume_endpoint_resets_the_streak() -> None:
    server = TlsServer("WWWWWWG")
    sink = _sink(
        server, retry_max_attempts=10
    )  # keep the record alive across the pause
    try:
        _emit_run(sink, complete=False)
        assert _wait(lambda: _paused(sink))
        assert server.connections == 3
        sink.resume_endpoint()
        # Another full streak of three is needed before the next pause.
        assert _wait(lambda: server.connections >= 5)
        assert _wait(lambda: _paused(sink))
        assert server.connections == 6
    finally:
        sink.close(1)
        server.close()


# ---------------------------------------------------------------- async exporter
async def test_async_exporter_pauses_on_the_third_failure_and_resumes() -> None:
    server = TlsServer("WWWG")
    sink = AsyncHTTPEventSink(
        allow_unrestricted_indicators=True,
        endpoint=server.endpoint,
        credential_provider=lambda: TOKEN,
        deployment_id=BINDING,
        expected_agent=AGENT,
        ca_bundle=CA,
    )
    try:
        _emit_run(sink)
        for _ in range(600):
            if _paused(sink):
                break
            await asyncio.sleep(0.05)
        assert _paused(sink)
        await asyncio.sleep(0.3)
        assert server.connections == 3 and server.requests == []
        await sink.resume_endpoint()
        for _ in range(600):
            if server.requests:
                break
            await asyncio.sleep(0.05)
        assert server.requests and not _paused(sink)
    finally:
        await sink.close(timeout=1)
        server.close()


def test_interleaved_ordinary_network_failures_neither_count_nor_reset() -> None:
    # W X W W: a plain TCP close sits between verification failures. It must not reset
    # the streak, so the third *verification* failure (the fourth connection) pauses.
    server = TlsServer("WXWWG")
    sink = _sink(server, retry_max_attempts=10)
    try:
        _emit_run(sink, complete=False)
        assert _wait(lambda: _paused(sink))
        time.sleep(0.3)
        assert server.connections == 4 and server.requests == []
    finally:
        sink.close(1)
        server.close()


class ConnectProxy:
    """Minimal HTTP CONNECT proxy that tunnels to a fixed local port."""

    def __init__(self, target_port: int) -> None:
        self.target_port = target_port
        self.connects: list[bytes] = []
        self._socket = socket.socket()
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen(16)
        self.port: int = self._socket.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._socket.accept()
            except OSError:
                return
            threading.Thread(target=self._tunnel, args=(conn,), daemon=True).start()

    def _tunnel(self, client: socket.socket) -> None:
        try:
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = client.recv(4096)
                if not chunk:
                    return
                head += chunk
            self.connects.append(head.split(b"\r\n", 1)[0])
            upstream = socket.create_connection(("127.0.0.1", self.target_port))
            client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")

            def pipe(source: socket.socket, sink: socket.socket) -> None:
                try:
                    while data := source.recv(65536):
                        sink.sendall(data)
                except OSError:
                    pass
                finally:
                    for end in (source, sink):
                        with contextlib.suppress(OSError):
                            end.close()

            threading.Thread(target=pipe, args=(upstream, client), daemon=True).start()
            pipe(client, upstream)
        except OSError:
            client.close()

    def close(self) -> None:
        self._socket.close()


def test_verification_failures_through_an_explicit_proxy_pause_the_endpoint() -> None:
    # The CONNECT request that opens the tunnel is not the evidence request: it must not
    # mark the attempt "sent", otherwise a verification failure during the handshake
    # with the real endpoint would look like a request that may have committed, would
    # not be recognised as TLS, and the endpoint would never pause.
    server = TlsServer("WWWG")
    proxy = ConnectProxy(server.port)
    sink = _sink(server, retry_max_attempts=10, proxy=f"http://127.0.0.1:{proxy.port}")
    try:
        _emit_run(sink, complete=False)
        assert _wait(lambda: _paused(sink))
        time.sleep(0.3)
        assert server.connections == 3 and server.requests == []
        assert len(proxy.connects) == 3 and proxy.connects[0].startswith(b"CONNECT ")
        status = sink.status
        assert status.exhausted_may_have_committed == 0
        assert not any(r.may_have_committed for r in status.recent_records)
    finally:
        sink.close(1)
        proxy.close()
        server.close()


async def test_async_exporter_through_an_explicit_proxy_pauses_the_endpoint() -> None:
    server = TlsServer("WWWG")
    proxy = ConnectProxy(server.port)
    sink = AsyncHTTPEventSink(
        allow_unrestricted_indicators=True,
        endpoint=server.endpoint,
        credential_provider=lambda: TOKEN,
        deployment_id=BINDING,
        expected_agent=AGENT,
        ca_bundle=CA,
        proxy=f"http://127.0.0.1:{proxy.port}",
        retry_max_attempts=10,
    )
    try:
        _emit_run(sink, complete=False)
        for _ in range(600):
            if _paused(sink):
                break
            await asyncio.sleep(0.05)
        assert _paused(sink)
        await asyncio.sleep(0.3)
        assert server.connections == 3 and server.requests == []
        assert sink.status.exhausted_may_have_committed == 0
        assert not any(r.may_have_committed for r in sink.status.recent_records)
    finally:
        await sink.close(timeout=1)
        proxy.close()
        server.close()

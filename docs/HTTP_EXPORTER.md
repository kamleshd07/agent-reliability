# HTTP evidence exporter

Install the optional transport with `pip install 'agent-reliability[http]'`.
Core installation still has no runtime dependencies. HTTPX is constrained to
`>=0.28.1,<1`; importing normal SDK APIs does not import it.

```python
import os
from uuid import UUID

from agent_reliability.adapters.http_event_sink import HTTPEventSink
from agent_reliability.domain import AgentIdentity, EvaluationOutcome
from agent_reliability.sdk import AgentReliability

identity = AgentIdentity("support-agent", "Support Agent", "1.4.0", "production")
exporter = HTTPEventSink(
    endpoint="https://gentlity.example/api/v1/evidence/runs",
    credential_provider=lambda: os.environ["GENTLITY_MACHINE_TOKEN"],
    deployment_id=UUID(os.environ["GENTLITY_DEPLOYMENT_ID"]),
    expected_agent=identity,
)
sdk = AgentReliability(sink=exporter)
try:
    with sdk.run(
        agent_id=identity.agent_id,
        name=identity.name,
        version=identity.version,
        environment=identity.environment,
    ) as run:
        run.record(indicator="task-success", outcome=EvaluationOutcome.PASS)
finally:
    delivery = exporter.close(timeout=5)
```

The endpoint is the **complete POST URL**. Create the sink after process
forking. It is thread-safe across runs for one exact AgentIdentity (including
name) and deployment UUID. The machine credential supplies organization;
there is no caller-supplied organization override or human-session fallback.
Agent id/environment must match the platform's lowercase machine-key grammar;
version is nonempty platform text of at most 120 Unicode scalar values.
Invalid identity/URL/capacity configuration raises `ConfigurationError`
before creating transport workers or reading credentials.

`emit(event) -> None` validates and admits to memory, never performs HTTP on
that caller. Local admission failures raise `EventDeliveryRejected`, including
full queue, unknown/released run, invalid wire field and PID mismatch. SDK
failure isolation records delivery health and preserves application flow.
`ExporterClosed` and `ConfigurationFailedError` are specialized local errors.
Transport failures are observed through immutable `status`, `flush(timeout)`
and `close(timeout)` snapshots. A snapshot has queue/binding counts, high-water
mark, dispositions, bounded recent record ids, redacted error labels, gates
and cumulative uncertainty/late-result counters. It never contains evidence,
URLs, response messages or credentials. A returned `None`, `SENT`, or an HTTP
status alone does not mean commitment. Only a validated 201/200 body yields
`COMMITTED`/`DUPLICATE`. Alerts should include `may_have_committed` and
`exhausted_may_have_committed` when records expire or are cancelled.

Schema version is fixed at 2; there is no silent downgrade. Each accepted
record has an opaque UUID-v4 event id and, where needed, an evaluation or
measurement id. Retries reuse the exact serialized body and identifiers.
The canonical digest preserves v1 bytes and adds exactly the documented v2
identity/version inputs; canonical serialization is distinct from wire JSON.

## Capacity and time configuration

| Constructor setting | Default |
|---|---|
| `max_queue_records`, `max_queue_bytes` | 1,000; 4 MiB |
| `closure_reserve_records`, `closure_reserve_bytes` | 50; 3 MiB |
| `retry_max_attempts` | 3 ordinary-transient outcomes |
| `active_delivery_seconds` | 75 seconds |
| `maximum_residence_seconds` | 900 seconds, including pauses |
| `max_throttle_responses` | 3 per record |
| `provider_timeout` | 60 seconds; configurable |
| `max_active_run_age` | None; no age eviction |

Two workers and ten connections use connect/read/write/pool timeouts of
5/30/10/5 seconds. Bindings cap at 1,000; terminal diagnostic tombstones cap
at 1,024 with 10-minute TTL. Recent record diagnostics cap at 1,000 with
24-hour TTL. Workers never hold the state lock during HTTP or provider waits.

Both queue bounds include in-flight and held records. Ordinary admission
leaves the closure reserve untouched; closure admission can use the full
queue. The 3 MiB reserve cannot guarantee 50 maximum-sized 64 KiB records.
Newest admission is rejected when either bound is exhausted; closure reserve
rejection has a separate counter. Active runs are never age-evicted by default.
Per-run FIFO is preserved across workers; different runs may deliver concurrently.
Direct sink users must call `release_run(run_id)` after their final health
submission, even when start/terminal admission fails. The SDK handles this in
its finish/start-abort cleanup. Each live binding permits one successfully
admitted immutable final-health record; duplicate or corrected submissions
are rejected. A failed admission can be retried. Composite sinks fan out the optional capability
and isolate each child before re-raising the first ordinary exception.

Ordinary transients (including 5xx, timeouts and malformed success bodies)
consume the attempt budget. Retries use independent full jitter from 0 to
250 ms, 500 ms, 1 s and then 2 s. A request that may have left the process
retains sticky uncertainty until an acknowledgement. Connect/DNS/TLS failure
before write has no such uncertainty. Absolute and active deadlines use
monotonic time and strict `>` expiry. Active time starts at first dispatch,
continues through backoff, and stops for queued/held work.

429 increments a separate per-record throttle counter and gates the whole
sink. RA-b accepts exactly one ASCII digit field, numeric value at most
4,294,967,295, including long zero prefixes; dates, comma lists, multiple
fields, signs and decimals are invalid. Clamp to remaining residence, then
add independent 0–2-second jitter, including for zero. Invalid guidance uses
ordinary exponential-backoff guidance plus that jitter. The fourth 429
exhausts that record while still applying the gate.

## Pauses and recovery

- 401 refreshes once per acknowledgement episode, subject to a 60-second
  minimum refresh interval. A second rejection pauses authentication; 403
  pauses immediately. Provider reads are single-flight and run on a dedicated
  daemon helper, initially at first dispatch and then only for refresh/resume.
  `resume_auth()` opens only for a valid token differing from the episode's
  rejected baseline. A platform-side cure using the same token requires a
  different token or a new sink. Invalid/raising/timed-out providers pause
  with `credential_invalid_local`. Late results cannot reopen a gate.
- Envelope `404 not_found` pauses deployment delivery; use
  `resume_deployment()` after fixing configuration. A framework/proxy 404
  without that envelope retries normally.
- Three matching compatibility-422 responses pause schema delivery;
  `resume_schema()` clears that gate and streak. Compatibility responses
  consume no ordinary attempt. J2 recognizes `unsupported_schema_version`,
  or `validation_error` with exactly one detail at
  `location: ["body", "producer_identity"]`, independently of library type or
  message. Only acknowledgement resets the streak; other outcomes are neutral.
- L2 (endpoint pause). The first redirect, or the **third consecutive TLS
  certificate-verification failure**, pauses endpoint delivery; `resume_endpoint()`
  is the explicit recovery. Records are held (up to the maximum residence), not
  dropped. Details (the real-handshake tests in
  `tests/unit/test_http_exporter_tls_real.py` cover classification of the four
  verification failures, the exact third-failure pause, N-1, reset by an exchange
  and by `resume_endpoint()`, interleaved plain-TCP failures, an explicit proxy, and
  the async exporter; other network-failure kinds are covered by classification
  tests only):
  - Scope: the streak belongs to one exporter instance, which is bound to one
    endpoint for its whole life; it is not shared between exporters or endpoints.
  - What counts: only a failed certificate verification (untrusted CA, wrong
    hostname, expired or self-signed certificate) of an attempt that had **not yet
    sent a request**. With an explicit `proxy`, the CONNECT request that opens the
    tunnel does not count as sending. The credential is therefore never sent over an
    unverified channel. Fewer than three such failures never pause delivery; the record is
    retried within its ordinary attempt budget.
  - What does not count and does not reset: other network failures (connection
    refused, closed or reset connections, timeouts, protocol or cipher mismatch)
    keep their ordinary classification and neither advance nor reset the streak; a
    failure of an attempt that had already sent a request stays an uncertain,
    ordinary failure.
  - What resets: any completed HTTP exchange over a verified connection (any status
    code, not only acknowledgements) and `resume_endpoint()`. After a reset three
    further consecutive verification failures are needed to pause again.
  - Other gates remain independently active.
  - These semantics, including the three refinements above (sent-attempt rule, proxy
    CONNECT, per-exporter endpoint scope), were confirmed by the owner on 2026-10-17.
- `409 deployment_identity_mismatch` permanently fails its record, cancels
  others and requires a new sink. `409 conflict` fails only its record.
  Other content 4xx errors permanently fail the affected record.

Held records remain subject to absolute residence. Resume never resets
retry/throttle budgets. No automatic discovery, schema downgrade, endpoint
probe or token fallback exists. Compatibility retries with alternating keys
can amplify requests until active time expires; workload/rate targets remain
pilot hypotheses rather than production SLOs (see the owner decision record).

## Security and lifecycle

TLS certificate and hostname verification are always enabled. HTTPS URLs
follow A-https-1 syntax checks; userinfo, backslashes and fragments are
rejected. Plain HTTP permits literal 127/8 IPv4 and `[::1]` only; `localhost`
is rejected under A2-3. No DNS result authorizes plaintext. Redirects are never
followed. The configured destination and an explicit inspecting proxy/CA
remain trusted operator choices.

`proxy` is an explicit HTTP/HTTPS proxy URL without userinfo; authenticated
proxy credentials are not accepted by this API. `ca_bundle` is an explicit
PEM path. With no bundle, native Windows CA/ROOT stores and available compiled system
CA paths are loaded independently of SSL_CERT_FILE/SSL_CERT_DIR. Ambient proxies, netrc and HTTPX CA environment
settings are disabled. A reject-all cookie policy prevents response cookies from entering either
client jar. Cookie headers are also removed before every request. No credential is sent to
a redirected destination or included in SDK diagnostics. External applications
must likewise avoid logging credentials/evidence or raw HTTP request objects.

Requests and responses cap at 64 KiB. Response bytes are streamed with a cap;
acknowledgements decode strict UTF-8, reject BOM/non-JSON tokens/trailing text,
keep the last duplicate member, and compare exact case-sensitive names after
unescaping. Unknown response members are ignored. Parser limits support the
approved 64 nesting levels and 1,000-character number tokens. Malformed or
oversized bodies never count as acknowledgement. JSON responses are requested
without content compression.

`flush(timeout)` waits up to its bound and leaves unfinished work queued.
`close(timeout)` immediately rejects new admissions, drains until the first
close deadline, cancels remaining work and clears bindings. It is idempotent;
no interpreter-exit flush is promised. Sync I/O cannot forcibly interrupt an
arbitrary blocking transport: at most two daemon workers finish or time out
in the background, and late responses cannot change terminal delivery state.
Likewise a provider that never returns retains at most one daemon helper per
sink; later resumes start no additional calls until that helper returns.
Neither type of helper keeps the host process alive.

Known limit of the synchronous exporter: HTTPX timeouts are per read, not per request.
Reading a response body is additionally bounded to 30 seconds (a trickled body is never
an acknowledgement and the attempt is retried), but a peer that trickles the response
*headers* can hold one of the two workers for as long as it keeps sending a byte inside
the 30-second read timeout, delaying other runs on that exporter. Use `AsyncHTTPEventSink`,
whose maintenance task cancels expired attempts, where an untrusted or unreliable
endpoint is possible. The endpoint is operator-configured and trusted, so this is
documented rather than treated as a defect.

Diagnostics never contain credentials or evidence, but HTTPX's own INFO-level logger
records request URLs: do not put secrets (tokens, keys) in the endpoint URL, including
its query string. Credentials travel only in the `Authorization` header, supplied by the
credential provider.

Installing without the `http` extra fails on import of the exporter modules with
`ImportError: ... pip install 'agent-reliability[http]'`; the core package never imports
HTTPX.

`AsyncHTTPEventSink` takes the same configuration, is created on its running
loop, and implements synchronous put-nowait `emit`/health methods. Await
`flush`, `close`, and all four resume methods. It owns native async HTTP workers and an independent maintenance task, so
deadlines still expire when both workers await responses. Expired attempts
are cancelled and their worker slots become available to other runs. On close
it cancels delivery tasks and waits for transport cleanup within the remaining
caller timeout. With a zero or exhausted timeout cleanup may remain pending;
keep the loop alive and call `await close(timeout=...)` again with a positive
budget to join cleanup. Repeated close does not extend evidence delivery.
Transport cleanup exceptions are observed and produce only the fixed local
log label `transport_cleanup_failed`; raw exception details never go to the
event loop or this diagnostic. Mutations require the creating loop/thread;
`status` is an immutable published snapshot readable from any thread and
`release_run` safely hands cleanup to the owner loop. Use `async with` for a
5-second default close; explicit close supports an application deadline.

## Stability status

**Classification: INTERNAL** under `GA_CONTRACT.md` (owner decision of 2026-10-17; there is
no "Beta" class and none was introduced). INTERNAL means "unsupported implementation detail;
it may change in any release; importability does not create a promise". No compatibility
promise beyond that existing policy is made, and no release version is promised here.

Intended consumer entry points (the names this document describes; use them rather than
anything else in the modules):

* `HTTPEventSink` and `AsyncHTTPEventSink`, their constructor arguments and methods
  (`emit`, `flush`, `close`, `status`, `release_run`, the `resume_*` methods);
* `DeliveryStatusSnapshot`, `DeliveryDisposition`, `DeliveryRecordStatus`;
* the local exceptions `ConfigurationError`, `ConfigurationFailedError`,
  `EventDeliveryRejected`, `ExporterClosed`;
* the optional `HealthEvidenceSink` protocol (`agent_reliability.ports.event_sink`) and the
  `indicator=` argument of `RunHandle.record_evaluation_failure`.

Internal implementation modules (never import from them): `_http_delivery`,
`_http_protocol`, and every underscore-prefixed or undocumented name, including the
test seams `_transport` and `_core`. Pin the SDK version and read the CHANGELOG before
upgrading. The published wire contract (schema version 2 and the acknowledgement) is defined
by the platform's OpenAPI and fixtures, not by this module, and is not affected by this
classification.

## Validation and integration boundary

The vendored platform fixture files are unchanged. Run
`python scripts/verify_p28_fixtures.py --platform-root ../agent-reliability-platform`
for local drift checks. CI verifies hashes; a remote drift job awaits a
published platform manifest/access mechanism. RA-b explicitly differs from
older ra-006's RA-a expectation, and the test records both outcomes without
editing the fixture. Loopback syntax and A2-3 restriction are also tested
separately against the unchanged base vectors.

Mocked delivery is not end-to-end certification. Combined PC-1/PC-2 live tests
must prove machine auth/no fallback, organization isolation, identity binding,
tenant-hidden 404, durable acknowledgement/replay conflict, v1/v2 digests,
rate limits, mixed-fleet schema pause, lost acknowledgements, TLS/proxy
isolation and bounded shutdown against actual persistence. Release still
requires platform-first per-instance build evidence and independent review.


Independent review identified a low-severity observability gap: some local
structural diagnostics (exception-label substitution, unknown release,
no-capable-child composite and unstamped final health) are private or not
counted on the public snapshot. This is explicitly deferred; delivery
commitment, retry/pause states and uncertainty must be monitored through the
existing public fields. No claim of complete diagnostic-reason coverage is made.

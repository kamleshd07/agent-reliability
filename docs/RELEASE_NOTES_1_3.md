# Agent Reliability SDK 1.3 — release notes

**Status: stable release `1.3.0`** (`pip install agent-reliability`; the exporter needs the
`http` extra). The HTTP exporter and the LLM-judge adapter are **Experimental** and may change in a
minor release with release notes. The `1.3.0rc1` pre-release published earlier is superseded by this
release and is not modified. The release date is the upload date shown by the package index.

## What 1.3 adds

1. **An optional HTTP evidence exporter** — `pip install 'agent-reliability[http]'`
   (`httpx>=0.28.1,<0.29`). `HTTPEventSink` and `AsyncHTTPEventSink` send content-free run, evaluation
   and measurement-health evidence from your agent to a Gentlity platform ingestion endpoint using a
   machine credential you supply. See [HTTP exporter](HTTP_EXPORTER.md) and the
   [platform quickstart](PLATFORM_QUICKSTART.md).
2. **An experimental model-backed evaluator adapter** — `agent_reliability.experimental.judge`
   (EXPERIMENTAL: it may change in a minor release; no accuracy claim is made; it sends content only
   to the provider *you* configure, never to the platform).
3. Run-lifecycle integration: when the configured sink supports the optional `HealthEvidenceSink`
   capability, finished runs submit their final measurement-health report; an optional `indicator=`
   argument on `RunHandle.record_evaluation_failure(...)` lets evaluation failures reach exporters.

Everything in the 1.2.x stable API, its reliability/SLO semantics and the `EventSink` contract is
**unchanged**. The core installation still has no runtime dependencies; `httpx` is only installed
with the `http` extra and the core package never imports it.

## What the exporter sends — and never sends

Only typed, bounded, content-free members cross the SDK-to-platform boundary: agent/run/deployment
identity, indicator and evaluator identifiers, outcomes, timestamps, lifecycle state, reason codes,
exception **class names**, evaluator provenance and measurement-health reasons. It never sends
prompts, model responses, tool arguments or results, documents, exception messages, tracebacks,
credentials or arbitrary metadata, and it has no API to attach them. Keep identifiers you choose
(indicator names, evaluator versions and configuration ids, reason codes, exception class names) free of
sensitive text: they are transmitted as-is within their length/grammar limits — the wire contract allows an
indicator of up to 200 printable characters, spaces included — and the SDK cannot detect sensitive content
inside them. The only free-text field, the indicator, is therefore guarded by a **required, fail-closed
policy**: construct the sink with `indicator_allowlist=[...]` (recommended; unlisted indicators are
rejected locally, never queued or sent, and never logged) or with the deliberate
`allow_unrestricted_indicators=True` (you accept that whatever indicator string your code supplies is
sent). A sink given neither raises `ConfigurationError`.

### Migrating the indicator policy

* From **1.2.1**: no change unless you adopt the exporter; new sinks must choose a policy.
* From the **`1.3.0rc1` pre-release**: sinks built without a policy now raise `ConfigurationError` at
  construction. Add `indicator_allowlist=["your-indicator", ...]` (list every indicator you record, exact
  match, case-sensitive) or `allow_unrestricted_indicators=True` to keep the previous behaviour. The wire
  format, platform contract and delivery semantics are unchanged.
* Setting both raises `ConfigurationError`; `allow_unrestricted_indicators` must be exactly `True`.

## Delivery guarantees (exact)

* `emit` only admits an event to a bounded **in-memory** queue; it never performs network I/O on
  your thread. The queue is **not durable**: pending evidence is lost if the process dies.
* Delivery is **best-effort with idempotent acknowledgement**, not exactly-once and not durable. Each record
  gets at most `retry_max_attempts` (default 3) ordinary attempts with jittered backoff — under about 2 s
  in total for a refused connection — so a platform outage longer than that **loses the affected
  evidence** (reported as `retry_exhausted`) unless you raise `retry_max_attempts` (bounded by
  `active_delivery_seconds`, default 75 s). Retries reuse the identical serialized body and event id; the platform answers `201 accepted` or
  `200 duplicate`, and only a validated acknowledgement counts as committed. A request that may have
  left the process stays flagged `may_have_committed` until acknowledged, so a timeout can leave a
  record committed but unacknowledged.
* Retries, queue size, residence time and throttling are bounded; evidence that cannot be delivered
  within those bounds is reported (never silently dropped) in the delivery status snapshots.
* `flush(timeout)`/`close(timeout)` are bounded; unfinished evidence stays queued or is cancelled and
  reported. No flush at interpreter exit is promised.
* Capacity, latency and throughput of a hosted platform are not established by these notes.

## Compatibility

* Python 3.11, 3.12, 3.13 (CI-tested). No change to supported Pythons.
* Platform: the exporter speaks wire **schema version 2** (machine-authenticated, deployment-bound).
  It requires a platform whose evidence-ingestion endpoint accepts schema v2 and machine
  credentials; there is no automatic downgrade or discovery. See the exporter document for the exact
  response/gating behaviour.
* Dependencies: base none; `http` extra `httpx>=0.28.1,<0.29` (the exporter reads one HTTPX/httpcore trace event to know a request may have left the process, so the supported range is pinned and covered by real-socket tests); `otel` extra unchanged.
* **Public API classification:** see [GA_CONTRACT.md](GA_CONTRACT.md) — the exporter entry points
  and the judge adapter are labelled there; internal modules (`_http_*`) carry no promise.

## Migrating from 1.2.1

No code change is required: 1.3 is backward compatible. To start sending evidence to a platform:
install the `http` extra, create an exporter with your endpoint, a credential provider, the
deployment UUID and your exact `AgentIdentity`, pass it as `sink=` to `AgentReliability`, and call
`exporter.close(timeout=...)` on shutdown. Nothing is sent unless you configure an exporter. Existing
sinks keep working; the new health capability is optional.

## Rolling back

Remove the exporter configuration (or pin `agent-reliability==1.2.1`). 1.2.1 contains no exporter and
no stored state; evidence already acknowledged by the platform stays there. In-flight queued evidence
is not recoverable after process exit (see above). There is no data migration on the SDK side.

## Support levels — what is and is not claimed

| Context | Status |
|---|---|
| Local development against a disposable platform | Verified for this release (installed distribution → disposable PostgreSQL-backed platform → reliability and SLO read). |
| A hosted Gentlity service | **Not claimed.** No customer-hosted environment is part of this release; hosted availability, capacity and customer credentials need a separate decision and validation. |
| Production support | **Not claimed.** No service-level commitment accompanies this release. |

## Known limitations

* The in-memory queue loses pending evidence on process death; local admission is not durable delivery.
* The synchronous exporter's HTTP timeouts are per read, so a peer that trickles response headers can
  delay delivery; use `AsyncHTTPEventSink` against untrusted or unreliable endpoints.
* No automatic step/tool/token instrumentation; no notification delivery or scheduler in the SDK.
* Organization, workspace, agent and deployment must be created on the platform by an authorized
  administrator before evidence can be sent (see the quickstart).
* The experimental judge adapter is uncalibrated and unsupported for accuracy claims.

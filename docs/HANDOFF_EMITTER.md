# Handoff event emitter (Experimental)

`agent_reliability.experimental.handoff` is an **optional, Experimental** emitter of
content-free P25 handoff events (platform route `POST /api/v1/handoff-events`,
`schema_version` 1). It is not part of the stable API, is not re-exported from
`agent_reliability`, and may change in a minor release with release notes
([VERSIONING.md](VERSIONING.md)). It adds no runtime dependency (standard library
`http.client`); importing it starts no thread and opens no connection.

## Opt-in

```python
import os
from agent_reliability.experimental.handoff import HandoffEmitter, HandoffEmitterConfig

emitter = HandoffEmitter(
    HandoffEmitterConfig(
        enabled=True,  # default False: nothing is ever sent, no thread, no socket
        base_url="https://gentlity.example",  # scheme and authority only
        credential_provider=lambda: os.environ["GENTLITY_HANDOFF_TOKEN"],
    )
)
emitter.requested(
    handoff_id="h-1",
    originating_agent_id=a,
    originating_producer_run_id="run-1",
    receiving_agent_id=b,
)  # originator
# receiver side: emitter.acknowledged(..., acceptance="accepted")
# receiver side: emitter.terminal(..., terminal_state="completed")
stats = emitter.close(timeout=5)
```

The credential is a machine credential holding only `handoff:ingest`, bound to one
deployment; the platform derives the reporter from `kind` and proves the agent from the
credential. The SDK never sends a reporter. `http://` is accepted only for loopback.

## Content-free by construction

Only the contract members can be passed: ids (UUIDs), closed enums, one timestamp and
bounded machine keys. Unknown or free-text arguments are rejected by the call signature
(`TypeError`). Values are validated with the contract bounds; a bad value returns
`"invalid"` and is counted (`rejected_invalid`), it never raises. Credentials never
appear in stats, `repr` or errors: diagnostics are fixed labels.

## Receiver events

The platform takes the receiving run and the outcome link **only from receiver events**.
The receiver should therefore supply `receiving_producer_run_id` (its own P2 run id) and,
when a P13 verification applies, `outcome_correlation_id` on `acknowledged` and
`terminal`; both helpers accept them. Run ids must be printable ASCII `0x21-0x7E`, 1-200
characters (no space, NUL or control characters). `event_time` is sent as an RFC 3339 UTC
string; `schema_version` is the integer 1.

## Idempotency

`idempotency_key(...)` is `hk1-` plus SHA-256 over the semantic members (source,
handoff id, kind, both agent ids, run ids, correlation id, acceptance or terminal state,
and `event_time` normalised to UTC), mirroring the platform digest. The same logical
event gives the same key across processes if you pass the same `event_time`. Override
with `idempotency_key=`. Keys are unique per (tenant, reporting agent), so two agents may use the same key
without conflict. Replays of identical evidence return 200; a different body
under one key is 409 `conflict` (rejected, not retried).

## Delivery semantics (at-least-once, best-effort, lossy by design)

- Emit never raises (validation and internal errors become counters) and never does I/O:
  it enqueues and returns a disposition string (`queued`, `disabled`, `invalid`,
  `dropped`, `unsupported`, `closed`, `error`).
- One daemon worker sends events in order from a bounded buffer (`max_events`,
  `max_bytes`). Overflow rule (`overflow`): `drop_oldest` (default) evicts the oldest
  buffered event; `drop_newest` refuses the new one. Every drop increments
  `dropped_buffer_full`.
- 201 and 200 are success. Retried with capped exponential backoff and jitter, up to
  `max_attempts` and `max_event_age_seconds`: network errors, 5xx, 429 `rate_limited`
  (honouring an integer `Retry-After`, capped by `retry_after_cap_seconds`), and 409
  `run_not_yet_known`. Not retried, counted `rejected`, dropped: 401, 403, 409
  `conflict`, 413, 422, 429 `handoff_limit_exceeded` and any other status. Exhausted
  attempts or age count `lost_exhausted`.
- 401 and 403 are terminal drops: the event is counted `rejected` and discarded, so
  rotating or revoking a credential while events are queued loses them (nothing is
  retained for a later credential). Fix credentials before emitting.
- After `os.fork()` the child discards its inherited copy of the buffer (the parent
  still delivers it) and starts a fresh worker on its next emit, so forked workers do
  not stall or send duplicates.
- Events still buffered at process exit, or abandoned when `close(timeout)` expires, are
  lost (`dropped_closed`); `flush(timeout)` waits for the buffer to drain.
- Because delivery is at-least-once, a replay is harmless (200); a lost event is visible
  only through `stats`.

## Unsupported platforms, no downgrade

A 404 or 405 from the route moves the emitter to `state == "unsupported"` for the life of
the process: queued events are discarded and counted (`dropped_unsupported`), later
emits return `"unsupported"` without any request, and there is no fallback endpoint and
no schema change. A response that advertises a `schema_version` other than 1 is a
rejection (`schema_mismatch`), never reinterpreted. Single-agent platforms without
handoff evidence are unaffected.

`stats` is a frozen snapshot: `state`, `queued_events`, `queued_bytes`, `submitted`,
`delivered_created`, `delivered_duplicate`, `rejected`, `rejected_invalid`, `retries`,
`dropped_buffer_full`, `lost_exhausted`, `dropped_unsupported`, `dropped_closed`,
`unsupported_responses`, `last_error`.

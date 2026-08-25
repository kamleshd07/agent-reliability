# ADR-0005: Instrumentation initialization failures degrade instead of raising

## Status

Accepted. Supersedes the `__enter__`/`__aenter__` sub-rule of
[ADR-0004](0004-instrumentation-failure-isolation.md) ("The boundary is
timing, not subsystem"); everything else in ADR-0004 (the
`Exception`-vs-`BaseException` boundary, the diagnostic-reporting
principle, all `Alternatives Considered`) remains in force and is not
restated here except where this ADR changes it.

## Context

ADR-0004 drew the failure-isolation boundary at *timing*: a failure
could raise if it occurred before any application code in the current
`with`/`async with` block had started running, on the reasoning that
nothing of the caller's was "at risk" yet. Under that rule, a clock or
run-id-generator failure inside `__enter__`/`__aenter__` was allowed to
raise, on the theory that this behaves like any other function call the
caller is expected to handle.

That reasoning had a hole: Python's context-manager protocol does not
execute a `with`/`async with` block's body unless `__enter__`/`__aenter__`
returns successfully. A raised `__enter__` failure does not "behave
like any other function call the caller is expected to handle" — it
silently prevents the very application code this SDK exists to observe
from running at all. That is a more severe violation of the M2 brief's
"the SDK must be less dangerous than the systems it observes" mandate
than the failure mode ADR-0004 was designed to prevent: a broken
`Clock` or `RunIdGenerator` implementation (a downstream, replaceable
dependency, not a caller mistake) could take down the customer's agent
execution entirely. This was found during M2.1 hardening work and
required a real decision, not a silent code change — hence a new ADR
rather than an edit to ADR-0004 (see [docs/adr/README.md](README.md),
"Process": accepted ADRs are not edited to reflect new decisions).

A related, smaller gap found in the same pass: the default
`LoggingDiagnosticHandler` logged `%r` of the suppressed exception,
which includes its `args`/message — the same message content
`RunFailed.exception_type` was deliberately designed to exclude
(ADR-0004, Security Impact). The default handler was leaking, by
default, exactly the content the rest of the design goes out of its way
to avoid capturing.

## Decision

### `__enter__`/`__aenter__` initialization failures degrade instead of raising

The boundary is redrawn from *timing* to *caller error versus
instrumentation runtime failure*. Direct, immediate validation of
values and object shapes the caller just supplied still raises
normally (this is unchanged from ADR-0004 and is, if anything,
strengthened — `AgentReliability(...)` now also validates that
injected `sink`/`clock`/`run_id_generator`/`diagnostic_handler` objects
structurally satisfy their respective ports, raising `TypeError`
immediately if not). An `Exception` raised by a *validly shaped*
instrumentation runtime component — run id generation, the initial
clock read, or internal run/event/context construction — is now caught,
diagnosed, and answered with a **degraded run** rather than propagated:

```text
AgentReliability.run(...) call     -> may raise  (constructs AgentIdentity;
                                       validates direct caller input)
AgentReliability(...) construction -> may raise  (wrong dependency object
                                       type is invalid SDK usage)
__enter__ / __aenter__             -> clock/id/internal Exception: diagnosed;
                                       returns a degraded handle; body runs;
                                       no event or context is established
                                    -> sink.emit(RunStarted) Exception:
                                       suppressed after a valid run is
                                       established
run.record(...) argument checks    -> may raise  (unchanged from ADR-0004)
run.record(...) clock/sink work    -> suppressed (unchanged from ADR-0004)
__exit__ / __aexit__               -> instrumentation Exception suppressed
                                       (unchanged from ADR-0004)
```

A degraded `RunHandle`:

- has `run_id=None` and `parent_run_id=None` — no identifier is
  fabricated;
- retains the already-validated `agent` identity;
- accepts `record()` calls: malformed arguments still raise
  (`ValueError`/`TypeError`, same validation as a normal run), a call
  after the `with` block exits still raises `RuntimeError`, and a
  well-formed call is a safe no-op;
- is never placed in the `ContextVar` — an existing parent (or `None`)
  remains current for the duration of the degraded run's body and
  afterward, with nothing to restore;
- emits no `RunStarted`, `RunCompleted`, `RunFailed`, or
  `EvaluationRecorded` event.

This makes `RunHandle.run_id`'s type `str | None` (previously always
`str`) — see Compatibility Impact.

### The default diagnostic logger no longer renders exception content

`LoggingDiagnosticHandler` now logs only `component`, `operation`,
`run_id` (if known), and `type(exception).__name__`. It never logs
`str(exception)`, `repr(exception)`, `exception.args`, a traceback, or
the raw `SdkDiagnostic`. A custom `DiagnosticHandler` still receives the
full exception object, unchanged from ADR-0004 — it is an explicit,
documented trusted boundary responsible for its own sensitive-data
handling; only the *default* behavior changes here.

## Alternatives Considered

- **Keep raising at `__enter__`/`__aenter__`, document the limitation
  instead of fixing it.** Rejected: this is not a documentable
  limitation, it is the exact failure mode ADR-0004 exists to prevent,
  just relocated to the one call site ADR-0004 mistakenly exempted.
- **Retry the failing dependency call once before degrading.**
  Rejected: retries hide a systemic problem (a genuinely broken clock
  or id generator will fail again) behind added latency and complexity,
  and a caller who wants retry behavior can implement it in their own
  `Clock`/`RunIdGenerator` implementation, which is exactly what the
  port abstraction is for.
- **Fabricate a placeholder run id (e.g. a fixed sentinel string) so
  `run_id` stays `str`.** Rejected: a fabricated identifier that did not
  come from the configured `RunIdGenerator` is indistinguishable from a
  real one downstream and would misrepresent what actually happened —
  worse than truthfully reporting "no run was established" via `None`.
- **Make the degraded handle a distinct type (e.g. `DegradedRunHandle`)
  rather than widening `RunHandle.run_id`.** Rejected: this would force
  every caller to branch on handle type before calling `record()`,
  defeating the point of degrading gracefully (the brief's own
  requirement: "Callers can keep using `run.record(...)` without
  branching"). A single type with an `Optional` `run_id` keeps the
  call site identical in both cases.
- **Still install the degraded handle in the `ContextVar`.** Rejected:
  a degraded handle has no run id, so any child started underneath it
  would need to either fabricate a parent id or itself go parent-less —
  neither is better than the child correctly inheriting the *true*
  parent (the nearest real run, or none) by simply never installing the
  degraded handle into the context stack at all.
- **Leave the default logger rendering full exception content.**
  Rejected: this directly contradicts the design's own stated rule for
  `RunFailed.exception_type` (ADR-0004, Security Impact) — the default
  path should not be the one place message content leaks by default.

## Consequences

- `RunHandle.run_id: str | None` is now the type every caller (and
  every internal consumer — `_safe_record`, `_emit_terminal_event`) must
  handle; internal consumers narrow it with an explicit `None` check or
  `assert` at the one call site (`_emit_terminal_event`) where it is
  structurally guaranteed non-`None` (a degraded handle never reaches
  `_finish`'s event-emission path, because its `ContextVar` token is
  never set — see `docs/SDK_DESIGN.md`).
- A degraded run produces zero observability by design: no event, no
  diagnostic beyond the one delivered at the moment of degradation. An
  operator who wants to know an agent ran in degraded mode at all must
  watch diagnostics, not events.
- Tests must cover, per failing component (run id generator, clock,
  internal construction, context installation) and per protocol (sync,
  async): that the body still executes, `record()` is a safe no-op,
  programmer errors on the degraded handle still raise, the surrounding
  context is untouched, and the caller's own exception (if any) still
  propagates with identity intact. See M2.1's test suite.
- `LoggingDiagnosticHandler`'s sanitized output must not regress —
  tests assert the exception message, `repr`, and any embedded secret
  are absent from the log line, not merely that *something* was logged.

## Security Impact

Extends ADR-0004's Security Impact: the default diagnostic path now
actively strips exception content rather than merely being described as
"not exported" — closing the gap where the default logger was the one
place message/argument content reached a log sink by default. Degraded
mode itself has no new security surface: it never fabricates identity
and never installs untrusted state into the shared `ContextVar`.

## Performance Impact

Adds a small, fixed number of `try`/`except Exception` blocks to the
`__enter__`/`__aenter__` path (already the case for every other
suppression point per ADR-0004) — no new allocation on the
non-exceptional path beyond what M2 already did. See `benchmarks/`;
M2.1's own benchmark comparison was inconclusive on a noisy shared
Windows host and is called out explicitly as not supporting any
performance claim (see the M2.1 report) — a controlled remeasurement is
carried forward, not treated as resolved by this ADR.

## Compatibility Impact

No public symbol was added or removed. `RunHandle.run_id`'s return
contract widens from `str` to `str | None`; existing code that assumed
`run_id` is always a non-`None` `str` should add a `None` check.
`agent_reliability.sdk` remains pre-alpha with no compatibility
guarantee (see [COMPATIBILITY.md](../COMPATIBILITY.md)) — this is
flagged here anyway because it is exactly the kind of contract
narrowing a stable release could not make silently once this API is
declared stable.

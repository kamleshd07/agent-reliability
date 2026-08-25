# ADR-0004: Instrumentation failure isolation

## Status

Superseded by [ADR-0005](0005-instrumentation-initialization-degraded-mode.md).
The decision recorded below governed M2 as originally shipped; M2.1
kept its `Exception`-vs-`BaseException` boundary and diagnostic-reporting
principle unchanged but replaced the "raise before the body runs"
sub-rule for `__enter__`/`__aenter__` with a degraded-run mode — see
ADR-0005 for what changed, why, and the parts of this ADR that still
hold. This document is left as originally written, not edited, so the
historical record of the M2 decision and its reasoning stays intact
(see [docs/adr/README.md](README.md), "Process").

## Context

The M2 brief states the SDK's central safety requirement plainly: "the
SDK must be less dangerous than the systems it observes." Concretely,
this means a broken sink, a broken custom clock, or a broken custom run
id generator must never (a) replace the application's own exception
with an instrumentation error, or (b) raise a *new* exception into
application code that was not expecting instrumentation to be able to
fail at that point. At the same time, some failures genuinely are the
caller's own mistake (e.g. `sdk.run(agent_id=None, ...)`) and should
raise immediately, exactly like any other misused API. A single
blanket policy — "never raise" or "always raise" — cannot satisfy both
requirements; the boundary between them needed to be decided explicitly
rather than emerging ad hoc across the codebase.

## Decision

### The boundary is timing, not subsystem

A failure is allowed to raise if and only if it occurs **before any
application code belonging to the current `with`/`async with` block has
started running**, as a direct, synchronous consequence of a call the
caller just made. Every other instrumentation-internal failure —
regardless of which component (clock, id generator, sink) caused it —
is caught and routed to diagnostics, never raised.

Concretely:

```text
AgentReliability.run(...) call     -> may raise  (constructs AgentIdentity;
                                       no application code in flight yet;
                                       behaves like any other function call
                                       that can fail)
__enter__ / __aenter__             -> clock/id-generator failure: may raise
                                       (same reasoning: still before the
                                       `with` body runs)
                                    -> sink.emit(RunStarted) failure: suppressed
                                       (the body is about to run; a broken
                                       downstream consumer must not prevent it)
run.record(...) argument checks    -> may raise  (closed run, wrong type,
                                       empty indicator — the caller's own
                                       mistake, checked before any
                                       instrumentation side effect is attempted)
run.record(...) clock/sink work    -> suppressed (application code is
                                       actively running and did not expect
                                       this call to be able to interrupt it)
__exit__ / __aexit__               -> always suppressed, unconditionally
                                       (this runs while the caller's own
                                       exception, if any, is actively
                                       propagating, or while control is
                                       about to return to their code —
                                       replacing or masking that is the one
                                       thing this SDK must never do)
```

The same dependency (e.g. `Clock`) is therefore allowed to raise at
`__enter__` and forbidden to raise at `__exit__` or inside `.record()`.
This is intentional, not an inconsistency: the decision is "is the
caller's own code currently in flight or about to resume," not "which
component failed."

**Superseded by ADR-0005**: this "may raise" treatment of `__enter__`/
`__aenter__` clock/id-generator failures turned out to violate the
underlying safety requirement itself — Python does not execute a
context body unless `__enter__`/`__aenter__` succeeds, so a raised
instrumentation failure here still prevents application code from
running, exactly the outcome this ADR exists to rule out. ADR-0005
replaces this sub-rule with a degraded-run mode. Everything below this
point in this document is otherwise still in force.

### The exception boundary is `Exception`, never `BaseException`

Every suppression point catches `Exception` only. `KeyboardInterrupt`,
`SystemExit`, `GeneratorExit`, and `asyncio.CancelledError` are never
caught by any `_safe_*` wrapper in this SDK, anywhere — including
inside the diagnostic-handler call itself. This is the standard Python
idiom for framework/library code precisely because these are
interpreter- or runtime-level control-flow signals (process
termination, generator teardown, cooperative task cancellation), not
"errors" in the sense this SDK's failure isolation is meant to contain.
A library that swallowed `KeyboardInterrupt` inside `sink.emit()` would
make the host process harder to interrupt at exactly the moment an
operator most needs it to stop — a worse outcome than the instrumentation
failure it would have been "protecting" against.

`asyncio.CancelledError` deserves special mention: it is a
`BaseException` subclass (since Python 3.8) specifically so that
ordinary `except Exception` handlers do not accidentally swallow
cancellation. This SDK's `except Exception` suppression points inherit
that property for free — a cancellation signal arriving while, say,
`sink.emit()` is executing propagates normally, is classified by
`__exit__` as `RunStatus.CANCELLED` (see [SDK_DESIGN.md](../SDK_DESIGN.md)),
and is never suppressed.

### Suppressed failures are reported, never dropped invisibly — except at one, single, documented last resort

Every suppressed failure is delivered synchronously to a
`DiagnosticHandler` as an `SdkDiagnostic` (component, operation, run id
if known, and the original exception object). The default handler logs
via this library's own logger, never the application's root logger. If
the diagnostic handler itself raises (still only `Exception`;
`BaseException` still propagates per the rule above), that failure is
caught and dropped silently — this is the one place in the SDK that
discards a failure with no further reporting, and it is a deliberate,
documented choice: a diagnostic path that can itself crash the
application defeats its entire purpose, and there is no lower-level
mechanism left to report a diagnostic handler's own failure to.

**Refined by ADR-0005**: the default handler's log line originally
included `%r` of the exception (its repr, which includes `args`/message).
ADR-0005 sanitizes the default logger to component/operation/run-id/
exception-class-name only; custom handlers still receive the full
exception object as described here.

## Alternatives Considered

- **Always raise instrumentation failures.** Rejected: directly
  contradicts the M2 brief's central safety requirement and the
  "never swallow user exceptions" instruction taken to its natural
  conclusion — a sink crashing should not be able to crash the agent
  it is merely observing.
- **Never raise, anywhere, including `sdk.run(agent_id=None)`.**
  Rejected: this would mean basic caller-input validation errors (an
  empty required field, wrong type) become invisible or get silently
  defaulted, which is worse for the caller than a normal, expected
  `ValueError` at the point they made the mistake — and the M2 brief
  explicitly endorses this exact case raising.
- **Catch `BaseException` in the suppression wrappers, "to be maximally
  safe."** Rejected: this would silently absorb `KeyboardInterrupt`/
  `SystemExit`/`CancelledError`, which is a worse failure mode than the
  instrumentation error it would be hiding — see the reasoning above.
- **A single global try/except around the entire `with` body.**
  Rejected: this is a different problem (protecting the SDK from the
  *application's* exceptions, which must never be caught at all — see
  "never swallow user exceptions") from the one this ADR solves
  (protecting the application from the *SDK's own* internal failures).
  Conflating the two would risk exactly the anti-pattern the M2 brief
  warns against: an SDK error replacing the user's original exception.

## Consequences

- Every suppression point in the SDK follows one rule, stated once here,
  rather than ad hoc per-call-site judgment calls that could drift.
- Tests must cover, per component (clock, id generator, sink, diagnostic
  handler) and per call site (`__enter__`, `.record()`, `__exit__`),
  that a broken dependency degrades to a diagnostic rather than an
  exception — and, separately, that a caller's own genuine mistake at
  `sdk.run(...)`/`.record()` still raises normally. Both are covered in
  M2's test suite (see the M2 report).
- A future milestone adding a real network exporter sink must not
  quietly relax this boundary "because now there's real I/O to worry
  about" — the same reasoning applies with more force once network
  failures are a realistic, frequent occurrence rather than a
  theoretical misconfiguration.

## Security Impact

Diagnostics carry the original exception object (including its
`args`/message) to the caller-supplied handler, in-process only, never
serialized or exported by M2 itself. This is treated as an accepted,
scoped exception to "avoid retaining exception message content" (see
[SDK_DESIGN.md](../SDK_DESIGN.md)'s event-model discussion of
`RunFailed.exception_type`, which deliberately does *not* carry
`str(exc)`): the diagnostic channel's entire purpose is operator
debugging of the SDK's own malfunctions, it is never automatically
persisted or transmitted by anything in M2, and a caller-supplied
handler that wants to log/store it takes on that responsibility
explicitly. [SECURITY_MODEL.md](../SECURITY_MODEL.md) is updated to
record this distinction.

## Performance Impact

Each suppression wrapper is a single `try`/`except Exception` block —
negligible overhead on the non-exceptional path (the common case), and
irrelevant on the exceptional path (already the slow path in any
Python program). See `benchmarks/`.

## Compatibility Impact

None yet declared stable — `agent_reliability.sdk` remains pre-alpha
(see [COMPATIBILITY.md](../COMPATIBILITY.md)). This ADR fixes the
*policy*, which is expected to remain stable even once the API is
declared stable, since relaxing it later would be a safety regression.

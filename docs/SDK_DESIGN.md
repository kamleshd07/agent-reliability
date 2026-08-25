# SDK Design (M2/M2.1 — Python Instrumentation SDK)

Status: implemented at M2 and runtime-hardened at M2.1. This document
resolves the public API, event model, context model, and failure-isolation semantics *before* the
implementation notes below describe what was actually built — per
[ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md) #1, the design
was settled here first.

## Product question

How can developers safely instrument agent runs and reliability
outcomes from synchronous and asynchronous Python applications — with
zero network, zero database, zero LLM, zero framework dependency, and
essentially zero risk of the SDK itself breaking the host application?

M2 does not answer where telemetry is stored, how it is sent remotely,
how it is visualized, or how it integrates with any agent framework or
LLM provider. See [ROADMAP.md](ROADMAP.md).

## Canonical public API

```python
from agent_reliability.sdk import AgentReliability
from agent_reliability.domain import EvaluationOutcome

sdk = AgentReliability()

with sdk.run(agent_id="refund-agent", name="Refund Agent", version="1.2.0") as run:
    result = execute_agent()
    run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)
```

```python
async with sdk.run(
    agent_id="refund-agent", name="Refund Agent", version="1.2.0"
) as run:
    result = await execute_agent()
    run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)
```

Deviations from the illustrative API in the M2 brief, and why:

- **`run.record()` takes `outcome: EvaluationOutcome`, not a string
  `"pass"`.** M1 exists specifically to make `PASS`/`FAIL`/`UNKNOWN` a
  typed, non-stringly-typed concept (docs/DOMAIN_MODEL.md). Accepting a
  raw string at the SDK boundary would reintroduce exactly the ambiguity
  M1 was built to eliminate (typos, case sensitivity, no exhaustiveness
  checking). The caller imports `EvaluationOutcome` from
  `agent_reliability.domain` once and uses it everywhere.
- **`indicator` stays a plain, validated non-empty `str`, not a value
  object.** A stronger `IndicatorName`/registry with versioning is a
  real future need, but nothing in M1's math consumes the indicator
  name at all (SLI/SLO computation operates on raw outcome counts,
  unaware of which named indicator produced them — that mapping is an
  application-layer concern for a later milestone). Introducing a
  registry now, with no consumer, would be speculative. Deferred,
  documented here rather than silently decided.
- **No `environment` shown in the minimal example**, but it is an
  optional keyword on `sdk.run(...)`, matching `AgentIdentity`.
- **All of `sdk.run()`'s parameters are keyword-only.** Positional
  `agent_id`/`name`/`version`/`environment` strings are easy to
  transpose by accident; keyword-only removes that failure mode for a
  small, permanent readability cost.

## What belongs where

- **Supplied once** (at `AgentReliability(...)` construction):
  `sink`, `clock`, `run_id_generator`, `diagnostic_handler` — the
  operational configuration of the SDK instance itself.
- **Supplied per run** (at `sdk.run(...)`): `agent_id`, `name`,
  `version`, `environment` — these vary per agent/run, not per SDK
  instance. `AgentReliability` does not hold a single fixed
  `AgentIdentity`, because one process instrumenting multiple agents
  (or one agent instrumenting sub-agents — see nested runs below) is a
  real, expected M2 use case.

## M3 external context lifecycle

`EventSink` remains a point-in-time delivery port. It cannot own a context
that must remain current after `emit(RunStarted)` returns. M3 adds the narrower
paired `RunContextBridge.start(run) -> RunContextScope` and
`RunContextScope.finish(...)` contract. The SDK invokes it only after a valid
run and SDK context exist, and finishes it after terminal event delivery.

`AgentReliability(...)` accepts an optional `run_context_bridge`. Bridge
`Exception`s become sanitized diagnostics and do not degrade the valid Agent
Reliability run, suppress its events, or replace application exceptions. A
degraded M2.1 run never invokes the bridge. The OpenTelemetry implementation
is synchronous and API-only: it performs no I/O, flush, provider mutation, or
export. See ADR-0006 and [OTEL_MAPPING.md](OTEL_MAPPING.md).

M3 does not widen the documented thread guarantee. OpenTelemetry Python and
the SDK both rely on context-local state: normal async tasks are isolated, but
new OS threads require explicit context propagation such as the existing
`contextvars.copy_context()` pattern below. Multiprocessing remains unclaimed.

## Why context managers, not decorators

A context manager makes the instrumented region's boundaries visible at
every call site and composes naturally with existing `try`/`except`/
`finally` code the caller already has. A decorator (`@reliable_agent`)
hides the boundary at the function-definition site, which is harder to
reason about for irregularly-shaped control flow (early returns,
partial execution, nested calls at arbitrary points) and — more
importantly — is unnecessary complexity before the context-manager
semantics have proven out. Decorators are explicitly deferred (see
"NO-GO ITEMS" in the M2 brief and [ROADMAP.md](ROADMAP.md)).

## Why one class supports both `with` and `async with`

The object `sdk.run(...)` returns implements `__enter__`/`__exit__` and
`__aenter__`/`__aexit__` on the same class, both calling the same
internal synchronous start/finish logic. This is safe specifically
*because* M2 has no real I/O anywhere in the instrumentation path — the
default sink is in-process, the default clock is a single
`datetime.now(UTC)` call, and the default id generator is
`uuid.uuid4()`. None of that blocks an event loop, so there is nothing
for the async variant to actually await; `async with` exists purely so
the SDK is usable syntactically inside `async def` functions without
forcing awkward `run_in_executor` wrapping. If a future milestone
introduces a sink with real blocking I/O (e.g. a network exporter), the
sync and async code paths may need to diverge for that sink
specifically — this class does not assume that can never happen, but
does not build for it prematurely either.

## Context model

A single `contextvars.ContextVar` holds the current `RunHandle` (or
`None` at the top level). Entering `sdk.run(...)` reads the current
value as this run's parent, then `.set()`s the new handle, saving the
returned `Token`; exiting always `.reset()`s using that token. This is
the standard nested-context-manager pattern and is what gives:

- **Correct nested runs**: a child run's parent is whatever was current
  when it started, regardless of how deep the nesting or how many
  sibling runs preceded it.
- **Correct async task isolation**: `asyncio.Task` creation copies the
  current `contextvars.Context`; two concurrently-running tasks each
  get their own copy, and a `.set()` inside one task's copy is invisible
  to the other task and to the parent context after the copy diverges.
  This is standard library behavior, not something this SDK implements
  itself — M2 relies on it and tests it aggressively (100+ concurrent
  tasks, see Testing below).

No global mutable variable, no thread-local-only storage, no mutable
singleton — all three are explicitly rejected by the M2 brief and would
break under concurrent async execution.

### Threads are not automatically supported

`contextvars` do **not** propagate into a newly started `threading.Thread`
by default — a new thread starts with an empty/default context, so a
run started on the main thread will not automatically appear as the
parent of a run started inside a plain new thread. M2 does not attempt
to work around this. If a caller wants a background thread's run to be
a child of the current run, they must explicitly capture and use the
current context themselves:

```python
import contextvars, threading

ctx = contextvars.copy_context()
thread = threading.Thread(target=lambda: ctx.run(worker_function))
thread.start()
```

This is tested (see Testing below) both to prove the limitation is real
and to prove the documented workaround actually works. `RunHandle` and
`AgentReliability` are not designed for concurrent access to a *single*
`RunHandle` from multiple threads at once (see "Concurrency limits"
below); the `AgentReliability` client itself is safe to call `.run()`
on concurrently, because it holds no mutable per-run state.

## Failure isolation boundary — the one rule that matters most

**Every SDK-internal operation that runs while the caller's code is
executing, or is about to resume, must never raise into that code.
Only immediate validation of arguments the caller just supplied — before
any instrumentation side effect is attempted — is allowed to raise.**

Concretely:

| When | What runs | May raise? |
|---|---|---|
| `AgentReliability(...)` call | Validates injected dependency object shapes | **Yes** — a wrong object type is invalid SDK usage. |
| `AgentReliability.run(...)` call | Constructs `AgentIdentity` (M1 validation) | **Yes** — this is direct, synchronous validation of arguments the caller just passed, exactly like a constructor raising `ValueError`. No user code is "in flight" yet. |
| `__enter__`/`__aenter__` | Reads the clock, generates a run id, establishes context, emits `RunStarted` | **No instrumentation `Exception` raises.** Initialization failure is diagnosed and returns a degraded handle so the body executes. |
| `run.record(...)` | Validates `indicator`/`outcome`; reads the clock; emits `EvaluationRecorded` | Argument validation (empty indicator, wrong-typed outcome, already-closed run): **yes, raise.** Clock/sink failure: **no, suppressed + diagnosed.** |
| `run.record_evaluation(...)` | Validates an already-completed M4 result; reads the clock; emits attributed `EvaluationRecorded` | Same boundary as `record()`: caller argument errors raise; clock/sink failures are suppressed and diagnosed. Evaluator execution does not happen here. |
| `__exit__`/`__aexit__` | Reads the clock, emits `RunCompleted`/`RunFailed` | **Never raises due to instrumentation failure**, full stop — this runs while the caller's own exception (if any) is actively propagating, or while control is about to return to their code; replacing or masking that is the one thing this SDK must never do. Clock/sink failures here are suppressed + diagnosed. |

The boundary is the source of the failure. Direct validation of caller
arguments still raises before any instrumentation side effect. Failures
from validly shaped runtime dependencies (clock, ID generator, sink,
diagnostic handler, or internal event/run construction) are isolated.
In particular, an `__enter__` failure would prevent Python from running
the context body, so M2.1 treats start-up as part of the protected runtime
path. See [ADR-0004](adr/0004-instrumentation-failure-isolation.md) for
the original reasoning, alternatives considered, and the exact
exception-class boundary (`Exception`, never `BaseException` —
`KeyboardInterrupt`, `SystemExit`, `GeneratorExit`, and
`asyncio.CancelledError` are never suppressed) — and
[ADR-0005](adr/0005-instrumentation-initialization-degraded-mode.md) for
why M2.1 replaced ADR-0004's "may raise at `__enter__`" sub-rule with the
degraded-run behavior described next.

### Degraded run behavior

If run-ID generation, the initial clock read, or internal run/event/context
construction raises `Exception`, `__enter__`/`__aenter__` reports one
diagnostic if safely possible and returns a degraded `RunHandle`:

- `run_id` and `parent_run_id` are `None`; no values are invented.
- `agent` remains the already-validated caller identity.
- valid `record()` calls are safe no-ops; malformed arguments and use
  after context exit retain their normal `ValueError`/`TypeError`/
  `RuntimeError` behavior.
- no `RunStarted`, `RunCompleted`, `RunFailed`, or `EvaluationRecorded`
  event is emitted.
- the current `ContextVar` is neither set nor reset. A surrounding parent
  therefore remains current throughout and after the degraded child body.

There is no public `enabled` flag or configurable degraded mode. Callers
can keep using `run.record(...)` without branching. The unavoidable
contract refinement is that the existing `run_id` property is now
`str | None`: `None` means no valid instrumented run was established.

Only one diagnostic is delivered per degraded run — the one at
`__enter__`/`__aenter__` time that explains why it degraded. Subsequent
no-op `record()` calls on the same degraded run do not each re-diagnose
it; the cause was already reported once, and repeating it would be
noise rather than new information for whatever is consuming
diagnostics.

### Suppressed failures are never silently discarded

Every suppressed instrumentation failure is routed to a
`DiagnosticHandler` (a small `Protocol`) as an `SdkDiagnostic` — which
component and operation failed, the run id if known, and the original
exception. The default handler logs at `WARNING` via this library's own
`logging.getLogger("agent_reliability.sdk")` logger and does not
configure the application's root logging in any way
([ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md) — libraries
never configure a consumer's global logging). It logs only component,
operation, run ID (if known), and exception class name. It never renders
the exception message, representation, arguments, traceback, or raw
diagnostic object. A custom handler receives the underlying exception and
is therefore a trusted in-process boundary responsible for its own
sensitive-data handling. If the diagnostic handler
itself raises, that failure is also caught and dropped — silently, as
an explicit, documented last resort — because a diagnostic path that can
itself crash the application would defeat its own purpose. Diagnostics
are not retained by the SDK after delivery; a caller who wants a history
of diagnostics supplies a handler that keeps its own list.

## Run lifecycle → `RunStatus` mapping

`__exit__`/`__aexit__` classifies the caller's exception, if any, to
choose the terminal `RunFailed.status`:

```text
no exception                       -> RunCompleted
asyncio.CancelledError             -> RunFailed(status=RunStatus.CANCELLED)
any other Exception/BaseException  -> RunFailed(status=RunStatus.FAILED)
```

`asyncio.CancelledError` is singled out because it is the canonical,
cooperative "this run was cancelled from outside" signal in asyncio —
distinct from the run's own logic failing, matching M1's
`RunStatus.CANCELLED`. `KeyboardInterrupt` and `SystemExit` are, for
this classification, treated as `FAILED` (the run did not complete its
intended work) — they are always re-raised regardless of classification;
classification only affects which terminal event is recorded, never
whether the exception propagates.

## M4 evaluator execution and run association

M4 keeps evaluation computation outside `RunHandle`. A raw sync or async
evaluator returns an `EvaluationDecision`; the optional `EvaluatorRunner`
attaches identity, configuration identity, determinism, and injected-clock time
to produce `EvaluationResult`. Safe runner failure returns
`EvaluationExecutionFailure`, never an outcome.

`RunHandle.record_evaluation(indicator=..., result=...)` associates only a
completed result. This explicit evaluate-then-record flow avoids hiding
latency, exception behavior, or async work inside instrumentation. It also lets
evaluators run offline or in tests without an active run.

Existing `record(indicator=..., outcome=...)` remains a low-level manual
assertion. Its event has `provenance=None`; the SDK does not manufacture a
`manual` evaluator. See [EVALUATOR_FRAMEWORK.md](EVALUATOR_FRAMEWORK.md) and
ADR-0007.

## Event model

Four typed, immutable, frozen-dataclass events — deliberately not a
richer hierarchy:

```text
RunStarted(run_id, parent_run_id, agent: AgentIdentity, started_at)
RunCompleted(run_id, ended_at)
RunFailed(run_id, ended_at, status: RunStatus, exception_type: str)
EvaluationRecorded(
    run_id,
    indicator: str,
    outcome: EvaluationOutcome,
    recorded_at,
    provenance: EvaluationProvenance | None = None,
    reason_code: str | None = None,
)
```

`recorded_at` is when run association was attempted. For evaluator-produced
events, `provenance.evaluated_at` is when evaluation completed; these times can
differ. Manual recording leaves provenance and reason code absent.

`RunFailed.exception_type` is the exception's **class name only**
(`type(exc).__name__`) — never `str(exc)`, never the exception object or
its traceback. `str(exc)` can contain arbitrary application data (a
`ValueError(f"invalid refund amount for user {email}")` is a realistic
example); retaining it in an event that may later be exported would
silently violate the "no implicit PII capture" principle. The class
name alone (`"ValueError"`) is sufficient for reliability classification
and carries no payload. This is also a memory-safety choice: events
never hold a reference to the exception object or its traceback, so
nothing keeps stack frames alive after the `with` block exits.

## Event vs. domain object

An `AgentRun` (M1) is a domain value — the durable, structured
representation of one run's identity and lifecycle. An event
(`RunStarted`, etc.) represents *something that happened*, emitted once,
consumed by a sink, and not retained by the SDK afterward. M2 never
treats these as interchangeable: `AgentRun` is constructed internally by
the SDK to validate lifecycle invariants (via M1's own `__post_init__`
checks) but is not itself the thing delivered to sinks — sinks receive
events. A future milestone's storage adapter is the layer responsible
for reconstructing/persisting `AgentRun`-shaped history from a stream of
events, if it chooses to; M2 does not do this.

## Sink port

```python
class EventSink(Protocol):
    def emit(self, event: InstrumentationEvent) -> None: ...
```

Synchronous and non-generic on purpose: M2's own sinks are all
in-process (no I/O), so there is nothing to await, and a synchronous
protocol is trivially callable from both the sync and async code paths
without an adapter shim. This does not foreclose an async sink later —
a future exporter-oriented port (M3+) can define its own
`AsyncEventSink` protocol and a small bridging adapter if/when a sink
needs to perform real I/O; nothing here is designed to make that
impossible, but nothing here builds it prematurely either
(YAGNI — see [ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md) #10).
Batching is deliberately out of scope: M2 has no exporter and no
background worker (see Buffering below), so there is no batching
boundary to design yet.

The complete M2.1 contract is:

- **Emission and ordering:** one synchronous `emit(event)` attempt per
  event; lifecycle order is start, zero or more evaluations, terminal for
  each successfully initialized run. Concurrent runs have no total order.
- **Thread safety:** the SDK does not serialize calls from different OS
  threads. A shared custom sink must provide its own thread safety. No new
  thread-support claim is made for run context propagation.
- **Exceptions:** sinks may raise `Exception`; the SDK diagnoses and
  suppresses it. `BaseException` control signals propagate deliberately.
- **Ownership/lifecycle:** the caller owns injected sinks. The SDK never
  closes or flushes them, and the port has no async or lifecycle methods.

### Default sinks

- `NoOpEventSink` — discards everything. This is the actual default
  passed to `AgentReliability()` when no `sink` is given: a library
  should not silently print to the console by default, and an SDK that
  does nothing observable until the caller opts into a sink is the
  least surprising default for production embedding.
- `InMemoryEventSink` — appends events to a list (behind a lock; see
  Concurrency below). Intended for tests and local examples, not
  production use. It retains every event without a capacity limit until
  `clear()` is called; callers retaining it for process lifetime retain
  the full event history. It is deliberately not a production sink.
- `CompositeEventSink` — fans one event out to multiple sinks. Each
  child is attempted exactly once in configured order even if an earlier
  child raises `Exception`. After all attempts, the first such exception
  is raised to the SDK's single failure-isolation boundary. The composite
  does not duplicate diagnostics. A `BaseException` stops fan-out and
  propagates, consistent with the SDK-wide control-signal policy.

## Buffering — deliberately absent

M2 introduces no queue, no background thread, and no batching. Every
`sink.emit()` call happens synchronously, in-line, inside the
already-failure-isolated call site. This is possible only because M2's
sinks are in-process and fast; a real exporter with network I/O would
need bounded buffering and a delivery worker, which is explicitly a
later milestone's concern (M9, per [ROADMAP.md](ROADMAP.md)). Building
that infrastructure now, with nothing to export to, would be
premature — see [ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md)
#13 (backpressure must be explicit, which is trivially true here: there
is no queue, so there is no unbounded-queue risk to design against yet).

## Run ID generation and clock

```python
class RunIdGenerator(Protocol):
    def generate(self) -> str: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
```

Both live in `agent_reliability.ports` (interfaces), with default
implementations (`UuidRunIdGenerator` using `uuid.uuid4()`;
`SystemClock` using `datetime.now(UTC)`) in `agent_reliability.adapters`
— following the M0 architecture boundary exactly (domain code still
imports neither; only `sdk` depends on `ports`, and the default
adapters are wired in by `AgentReliability.__init__`). This is the
layer M1 deliberately deferred id/time generation to (see M1's ADR-0002)
— M2 is that layer.

## Memory safety

- `RunHandle` does not hold a reference to any collection that grows —
  it holds a small, fixed `AgentRun` (or validated identity in degraded
  mode), a `_closed` flag, and a callback to the owning client. Nothing
  about using it causes unbounded growth.
- The `ContextVar` token from `__enter__` is always reset in
  `__exit__`/`__aexit__` (even on exception, since `__exit__` always
  runs once `__enter__` has succeeded), so no completed run's handle is
  kept reachable via the context after its `with` block ends. A degraded
  run (see "Degraded run behavior" above) never sets a token in the
  first place — it is never placed in the `ContextVar` at all, so there
  is nothing for `__exit__`/`__aexit__` to reset for it.
- `InMemoryEventSink` is the one component that intentionally
  accumulates — documented as a test/example-only component, not a
  production default (see Default sinks above).
- Diagnostics are delivered synchronously and not retained by the SDK
  itself.

## Concurrency limits (documented, not solved)

A single `RunHandle` is intended to be used by the task/thread that
entered its `with`/`async with` block. Calling `.record()` on the same
`RunHandle` concurrently from multiple threads or tasks is not
supported or tested at M2 — there is an inherent (and, for this
milestone, accepted) TOCTOU race between checking `_closed` and using
the handle if it is shared across concurrent callers. `AgentReliability`
itself *is* safe to call `.run(...)` on concurrently from multiple
threads/tasks, because it holds no mutable per-run state; each call
produces its own independent `RunHandle`.

## Multiprocessing / forking

Not tested, not claimed. A `contextvars.Context` does not survive a
`fork()`/`multiprocessing` process boundary in any special way beyond
ordinary Python object copying semantics (which, for a `ContextVar`
holding a `RunHandle`, do not reconstruct a meaningful parent
relationship in the child process). If a future milestone needs
cross-process run correlation, it needs its own design — not addressed
here.

## Shutdown

There is no background worker, no queue, and no `atexit` hook. Nothing
in M2 requires an explicit shutdown call — the SDK's resources are
exactly as long-lived as the objects the caller already holds
(`AgentReliability`, any custom sink). If a future milestone introduces
a sink with a real resource to flush (a network connection, a file
handle), that sink's own lifecycle (not a global SDK shutdown call)
should own that responsibility.

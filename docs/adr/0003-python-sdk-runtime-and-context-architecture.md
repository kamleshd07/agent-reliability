# ADR-0003: Python SDK runtime and context architecture

## Status

Accepted

## Context

M2 needs to let application code record agent runs and reliability
outcomes from both synchronous and asynchronous Python, with correct
nested-run and concurrent-task behavior, and without depending on
network, database, OpenTelemetry, or any agent framework
([DOMAIN_MODEL.md](../DOMAIN_MODEL.md), [ROADMAP.md](../ROADMAP.md)).
Three architectural questions had to be settled before writing code:
how "current run" context is tracked and propagated, whether sync and
async usage need separate abstractions, and where the new runtime ports
(clock, run id generation, event sink) live relative to the M0 layering.

## Decision

### 1. A single `contextvars.ContextVar[RunHandle | None]` tracks the current run

Entering a run reads the current value as the new run's parent, sets a
new value, and always resets to the saved `Token` on exit. This is the
standard library's own mechanism for exactly this problem, and — unlike
a global mutable variable, thread-local storage, or a mutable singleton,
all of which the M2 brief explicitly rejects — it is copied per
`asyncio.Task` at task creation, giving correct isolation between
concurrently running tasks without this SDK implementing any of that
copying itself. See [SDK_DESIGN.md](../SDK_DESIGN.md) for the concurrency
and thread-propagation details, including the explicit non-goal of
automatic cross-thread propagation.

### 2. One class implements both the sync and async context manager protocols

`__enter__`/`__exit__` and `__aenter__`/`__aexit__` are both defined on
the object returned by `AgentReliability.run(...)`, both calling the
same synchronous internal start/finish logic. This is safe only because
M2's instrumentation path performs no real I/O anywhere (in-process
sink, a single clock read, `uuid.uuid4()`) — there is nothing for an
async variant to usefully await. Two separate classes (a "sync SDK" and
an "async SDK") were rejected as unnecessary duplication for logic that
is, today, identical; if a future sink introduces real blocking I/O,
that sink (not this class) is the place to draw a sync/async
distinction, since M2's own logic still has nothing to await.

### 3. New runtime ports live in `agent_reliability.ports`; default implementations live in `agent_reliability.adapters`

`Clock`, `RunIdGenerator`, and `EventSink` are `Protocol`s in `ports/`,
matching M0's architecture (`ports` = typed interfaces the application
layer depends on; `adapters` = concrete implementations — see
[ADR-0001](0001-architecture-boundaries.md)). `SystemClock`,
`UuidRunIdGenerator`, `NoOpEventSink`, `InMemoryEventSink`, and
`CompositeEventSink` live in `adapters/`. `agent_reliability.sdk` is the
"User API"/application layer from M0's diagram: it depends on `domain`
and `ports`, and is wired to concrete `adapters` only at
`AgentReliability.__init__` (defaulting to the in-process, no-op-ish
adapters above) — never the reverse. `domain` continues to import
nothing from `ports`, `adapters`, or `sdk`.

### 4. Run id generation and clock reads move to this layer, not the SDK's internals scattered ad hoc

M1's ADR-0002 deliberately left `AgentRun.run_id` and `started_at`/
`ended_at` as required, caller-supplied constructor arguments — no
hidden `uuid.uuid4()` or `datetime.now()` inside the domain. M2 is
exactly the layer ADR-0002 anticipated for this: `AgentReliability`
holds one `RunIdGenerator` and one `Clock` (both replaceable, both
defaulted to standard-library-backed implementations), and every place
that needs an id or a timestamp goes through them — never a scattered
direct `uuid.uuid4()` or `datetime.now()` call inside SDK runtime code.

## Alternatives Considered

- **Global mutable "current run" variable.** Rejected outright — breaks
  under any concurrent execution (two tasks/threads would corrupt each
  other's notion of "current run"), explicitly listed as a rejected
  option in the M2 brief.
- **Thread-local storage instead of `contextvars`.** Rejected: does not
  work correctly for `asyncio` (many concurrent tasks share one OS
  thread), which is a required M2 use case.
- **Separate `AgentReliability`/`AsyncAgentReliability` classes.**
  Rejected as unnecessary duplication given today's identical logic
  (see Decision 2) — revisit only if a future sink genuinely needs
  divergent sync/async behavior.
- **`Clock`/`RunIdGenerator`/`EventSink` defined inside `sdk/` rather
  than `ports/`.** Rejected: these are exactly the shape of thing M0
  defined `ports/` for (typed interfaces the application layer depends
  on, decoupled from any concrete implementation), and putting them in
  `sdk/` would duplicate an abstraction the architecture already has a
  home for.
- **Decorator-based instrumentation (`@reliable_agent`).** Rejected for
  M2 per the brief's explicit no-go list; context managers make
  instrumented boundaries visible at the call site and compose with
  existing control flow without hiding behavior behind a decorator.

## Consequences

- Nested runs, concurrent async tasks, and context restoration on both
  normal exit and exception all fall out of correct `contextvars` usage
  and are covered by dedicated tests (see M2's test report) rather than
  by custom SDK-written propagation logic.
- Cross-thread propagation is a documented non-goal, not a silent gap —
  callers who need it use the standard `contextvars.copy_context()` +
  `Context.run()` pattern themselves, which is tested to confirm it
  works as documented.
- `AgentReliability` is safe to share and call `.run()` on concurrently,
  because it holds no mutable per-run state — all per-run state lives on
  the `RunHandle` and the `ContextVar`.
- If a future milestone's sink needs real async I/O, this ADR does not
  need to be revisited for the context/lifecycle model — only the sink
  port and possibly a bridging adapter.

## Security Impact

None beyond [SECURITY_MODEL.md](../SECURITY_MODEL.md), updated
separately for M2's new capture surface (see ADR-0004 and the M2
security model update).

## Performance Impact

Each `.run()` call does: one `ContextVar.get()`, one id generation call,
one clock read, one `ContextVar.set()`, one event construction + sink
call at start, mirrored at exit. No locking, no serialization, no
reflection, no deep copies. Measured baseline numbers are recorded in
`benchmarks/` as engineering baselines, not marketing claims (see
[ENGINEERING_PRINCIPLES.md](../ENGINEERING_PRINCIPLES.md) #6).

## Compatibility Impact

`agent_reliability.sdk` is a new, pre-alpha, experimental public
namespace (see [COMPATIBILITY.md](../COMPATIBILITY.md)) — not exported
from the package root. Nothing in M1's public surface changes.

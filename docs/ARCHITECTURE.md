# Architecture

## Layering

```text
┌──────────────────────────────────────────────┐
│                 User API                     │
│       SDK / configuration / decorators       │
├──────────────────────────────────────────────┤
│               Application                    │
│ orchestration / lifecycle / reliability use  │
│                  cases                       │
├──────────────────────────────────────────────┤
│                  Domain                      │
│                                              │
│ Run / Evaluation / SLI / SLO / Error Budget │
│ Reliability State / Reliability Event        │
│                                              │
├──────────────────────────────────────────────┤
│                Ports                         │
│ exporters / clocks / evaluators / storage    │
├──────────────────────────────────────────────┤
│               Adapters                       │
│ OTEL / console / framework integrations      │
└──────────────────────────────────────────────┘
```

Dependency rule: an arrow may only point downward in this diagram.
`domain` depends on nothing in this project. `application` depends on
`domain` and `ports` (interfaces only). `adapters` depend on `ports` and
`domain`. Nothing outside `adapters` may import a specific vendor SDK,
transport library, or agent framework. The "User API" layer is the
thin, small, typed surface re-exported from the package root; it wires
application + adapters together for the common case but does not itself
contain business logic.

This mirrors hexagonal / ports-and-adapters architecture. It is chosen
over a simpler flat module layout because the vendor-neutrality and
framework-independence principles ([ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md)
#3, #9) are structural requirements, not style preferences — the layout
should make an OTel or LangChain import inside `domain` a visible
mistake in a diff, not something that requires institutional memory to
catch.

## Current state (M5)

`domain` contains the reliability math kernel from M1 (`AgentIdentity`,
`AgentRun`/`RunStatus`, `EvaluationOutcome`, `UnknownPolicy`/`RatioResult`,
`ObjectiveDirection`/`Slo`/`SloStatus`/`SloEvaluation`,
`BudgetStatus`/`ErrorBudget`/`BurnRate`) — pure, typed, deterministic,
zero I/O, unchanged since M1 (see [DOMAIN_MODEL.md](DOMAIN_MODEL.md),
[SLO_SEMANTICS.md](SLO_SEMANTICS.md), and
[ADR-0002](adr/0002-reliability-mathematics-and-undefined-data-semantics.md)).

M2 added the Python instrumentation SDK; M2.1 hardens its runtime failure
boundaries without adding a layer, dependency, exporter, or worker. The
same dependency direction fixed at M0 remains in force
(`sdk` → `domain` + `ports`; `adapters` → `ports`
+ `domain`; nothing flows back into `domain`):

- `ports`: `Clock`, `RunIdGenerator`, `EventSink` (with the
  `InstrumentationEvent` types the sink port speaks in) — typed
  interfaces, no concrete implementation.
- `adapters`: `SystemClock`, `UuidRunIdGenerator`, `NoOpEventSink`,
  `InMemoryEventSink`, `CompositeEventSink` — the default, in-process
  implementations `AgentReliability` wires in unless overridden.
- `sdk`: `AgentReliability` (the entry point), `RunHandle`, `current_run()`,
  `DiagnosticHandler`/`LoggingDiagnosticHandler`/`SdkDiagnostic` — the
  "User API" layer from the diagram above. Run initialization failure
  produces a context-neutral, no-telemetry degraded handle.

See [SDK_DESIGN.md](SDK_DESIGN.md) for the full design and
[ADR-0003](adr/0003-python-sdk-runtime-and-context-architecture.md)/
[ADR-0004](adr/0004-instrumentation-failure-isolation.md)/
[ADR-0005](adr/0005-instrumentation-initialization-degraded-mode.md) for
the context-propagation and failure-isolation architecture — ADR-0005
supersedes ADR-0004's `__enter__`/`__aenter__` sub-rule with the
degraded-run behavior. `application` and `experimental` remain empty,
documented placeholders.

M4 adds `agent_reliability.evaluation` between the pure domain outcome and SDK
orchestration. It contains immutable identity/decision/provenance/result
values, separate structural sync/async protocols, and two local built-ins. It
depends only on `domain` and the standard library. The SDK-layer
`EvaluatorRunner` adds the existing `Clock` and diagnostic ports, while
`RunHandle` only associates an already completed result with a run. No domain
dependency points upward and no evaluator requires SDK context.

`ports.events` depends on `evaluation` too — `EvaluationRecorded` carries an
optional `EvaluationProvenance` so a recorded evaluation's attribution is
typed, not four duplicated string fields. This refines ADR-0001's original
"ports are expressed only in domain types" statement (that ADR's text is left
as originally written, not edited — see
[ADR-0007](adr/0007-evaluator-architecture-and-provenance-semantics.md) §11
for the full reasoning and the boundary that still holds: ports may reference
these immutable, vendor-neutral evaluation *values*, but still may not depend
on evaluator execution, SDK runtime, or concrete adapters).

Everything above is exported from its own subpackage
(`agent_reliability.domain`, `.evaluation`, `.ports`, `.adapters`, `.sdk`),
never from
the package root (`agent_reliability.__version__` is still the only
root-level export) — see the M1/M2 entries in
[CHANGELOG.md](../CHANGELOG.md) for the full symbol lists, all
classified by the normative [GA contract](GA_CONTRACT.md).

M5 adds `agent_reliability.reliability` as the pure application-level
measurement-integrity boundary between M4 observations and M1 mathematics. It
streams one full-window iterable and an optional explicit lookback, validates
one exact indicator/methodology cohort, then calls the existing M1 functions.
It returns either a complete immutable report composed from M1 values or a
typed conflict containing no reliability number. Neither `domain`,
`evaluation`, runtime `sdk`, event `ports`, nor the OTel adapter depends on
this package. See [ADR-0008](adr/0008-reliability-aggregation-and-provenance-compatibility.md)
and [LOCAL_RELIABILITY_ENGINE.md](LOCAL_RELIABILITY_ENGINE.md).

## Why `experimental` is a package, not a decorator

A separate `experimental` namespace makes instability visible at the
import site (`from agent_reliability.experimental import X`), rather
than requiring a reader to notice a `@experimental` decorator or a
docstring warning. It also lets tooling (future: a lint rule, a CI
check) enforce that `experimental` symbols never leak into a stable
module's public re-exports.

## Deviations from the initially proposed repository layout

The task brief proposed a repository tree as a starting point and asked
for it to be critiqued, not copied blindly. Deviations made at M0:

- **No `.github/workflows/security.yml` yet.** There is no dependency
  surface or attack surface yet to scan meaningfully (zero runtime
  dependencies, no network code, no deserialization). Adding a security
  workflow now would be a placebo. It belongs at the milestone that
  first adds runtime dependencies or handles untrusted input (see
  [SECURITY_MODEL.md](SECURITY_MODEL.md) and [ROADMAP.md](ROADMAP.md)).
- **No `.github/ISSUE_TEMPLATE/` yet.** Low value before there are
  external contributors or a public repository to receive issues
  against; trivial to add later without any structural cost.
- **`benchmarks/` deferred**, not created at M0. There is no
  instrumentation code yet to benchmark. Creating an empty benchmarks
  harness now would be scaffolding without a target; it is scoped into
  the milestone that introduces the SDK's runtime instrumentation path
  (M2), per [ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md) #6.
- **`CODE_OF_CONDUCT.md` included as proposed** — cheap, standard, and
  expected of a public OSS repository from day one.
- **Test category directories (`tests/integration`, `tests/contract`,
  `tests/property`) created empty with `.gitkeep`**, holding only a
  single real unit test (package import/version/public-API-surface).
  There is no integration boundary, evaluator, or exporter yet to write
  contract or integration tests against; see
  [TESTING_STRATEGY.md](TESTING_STRATEGY.md).
- **`hatchling` chosen as the build backend** (not specified in the
  brief) for its widely-adopted `src/` layout support and low
  configuration surface, over `setuptools` or `poetry-core`. This is a
  reversible, low-stakes choice and does not warrant an ADR.

## M3 OpenTelemetry adapter

M3 adds `RunContextBridge`/`RunContextScope` in `ports` and the optional
`adapters.otel` implementation. The SDK owns the paired start/finish call;
the adapter owns OpenTelemetry span activation and restoration. Point-in-time
event delivery therefore remains separate from execution-scope lifetime.

Only the optional adapter imports `opentelemetry-api`; the base dependency set
remains empty. No provider, exporter, worker, propagation protocol, or OTel
identifier enters the core or domain. See
[ADR-0006](adr/0006-opentelemetry-interoperability-and-context-ownership.md)
and [OTEL_MAPPING.md](OTEL_MAPPING.md).

## M8 measurement health

M8 adds the orthogonal `agent_reliability.measurement` namespace and run-local
health tracking. Evaluator outcomes, reliability math, event schemas, and
optional OTel ownership remain unchanged. See ADR-0009 and
[MEASUREMENT_HEALTH.md](MEASUREMENT_HEALTH.md).

## Deferred architectural decisions (require an ADR before implementation)

- Agent identity semantics (what makes two runs "the same agent" across
  versions; how `environment` participates in SLO scoping)
- Richer run failure-cause taxonomy (e.g. distinguishing timeout from
  other failure causes) — the minimal four-state run lifecycle
  (`STARTED`/`COMPLETED`/`FAILED`/`CANCELLED`) needed for M1's
  invariants was resolved by
  [ADR-0002](adr/0002-reliability-mathematics-and-undefined-data-semantics.md)
- SLO calculation model specifics (rolling vs. calendar windows,
  multi-window burn-rate alerting)
- Error-budget mathematics for non-ratio SLIs
- Exporter architecture (batching, retry, backpressure policy)
- Persistence architecture (if/when a reference storage adapter is
  built)

ADR-0001 ([docs/adr/0001-architecture-boundaries.md](adr/0001-architecture-boundaries.md))
records only the layering and dependency-direction decision made at M0.
The items above are explicitly not decided yet.

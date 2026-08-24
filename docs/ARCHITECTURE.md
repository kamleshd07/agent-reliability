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

## Current state (M1)

`domain` now contains the reliability math kernel: `AgentIdentity`,
`AgentRun`/`RunStatus`, `EvaluationOutcome`, `UnknownPolicy`/`RatioResult`,
`ObjectiveDirection`/`Slo`/`SloStatus`/`SloEvaluation`, and
`BudgetStatus`/`ErrorBudget`/`BurnRate` — pure, typed, deterministic,
zero I/O (see [DOMAIN_MODEL.md](DOMAIN_MODEL.md),
[SLO_SEMANTICS.md](SLO_SEMANTICS.md), and
[ADR-0002](adr/0002-reliability-mathematics-and-undefined-data-semantics.md)
for the full specification these implement). `application`, `ports`,
`adapters`, and `experimental` remain empty, documented placeholders.
These domain types are exported from `agent_reliability.domain`, not
from the package root (`agent_reliability.__version__` is still the
only root-level export) — see the M1 entry in
[CHANGELOG.md](../CHANGELOG.md) for the full symbol list, all
pre-alpha/unstable per [COMPATIBILITY.md](COMPATIBILITY.md).

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

## Deferred architectural decisions (require an ADR before implementation)

- OpenTelemetry integration strategy (SDK bridge vs. optional exporter
  vs. required dependency)
- Telemetry schema/semantic-convention versioning mechanism
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
- Evaluation plugin model (exact `Evaluator` protocol)
- Persistence architecture (if/when a reference storage adapter is
  built)

ADR-0001 ([docs/adr/0001-architecture-boundaries.md](adr/0001-architecture-boundaries.md))
records only the layering and dependency-direction decision made at M0.
The items above are explicitly not decided yet.

# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/); versioning
follows [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).

## [Unreleased]

## [1.0.0]

First General Availability release. The public contract frozen for `1.0.0rc1`
is unchanged; this release differs from `1.0.0rc1` only in version, release
metadata, and documentation status — no production code, public API, or
documented semantic changed. See [GA_CONTRACT.md](docs/GA_CONTRACT.md) for
the full normative 1.0 contract and [VERSIONING.md](docs/VERSIONING.md) for
the compatibility and deprecation policy this version now follows.

Stable, user-facing capabilities as of `1.0.0`:

- Safe synchronous and asynchronous agent instrumentation: instrumentation
  dependency failures are isolated from application code, and initialization
  failure degrades to a no-telemetry handle instead of raising.
- Optional OpenTelemetry trace interoperability, with the host owning the
  provider, sampling, propagation, processing, and export.
- Explicit `PASS`/`FAIL`/`UNKNOWN` evaluation outcomes, with evaluator
  execution failure kept categorically distinct from all three.
- A deterministic evaluator framework (`agent_reliability.evaluation`) with
  immutable evaluator identity, decisions, results, and provenance.
- Exact `fractions.Fraction` SLO, error-budget, and burn-rate mathematics,
  including explicit `UnknownPolicy` handling and defined no-data/
  zero-tolerance states.
- Provenance-safe local reliability aggregation
  (`agent_reliability.reliability`): incompatible measurement methodologies
  return a typed conflict rather than a misleading combined number.
- A typed public API (`py.typed` shipped, strict-mypy verified against the
  installed package) with zero base runtime dependencies and fully offline,
  local operation — no network service, database, or hosted platform is
  required.
- Privacy-first defaults throughout: no automatic capture of prompts,
  responses, tool arguments/results, exception messages, tracebacks, or
  arbitrary payloads.

This is an open-source SDK release. It does not include any hosted,
multi-tenant, or commercial control-plane functionality.

## [1.0.0rc1]

This first public release candidate establishes the frozen 1.0 contracts for
privacy-first agent instrumentation, synchronous and asynchronous run
lifecycles, instrumentation failure isolation, optional OpenTelemetry
interoperability, deterministic evaluation with provenance, exact SLO/error
budget/burn-rate mathematics, provenance-safe local reliability aggregation,
and a typed zero-base-dependency API.

### Changed

- M7 freezes the 1.0 public and semantic contracts, defines SemVer and
  deprecation policy, makes runtime `__version__` the package-metadata source,
  and excludes retained exceptions from `SdkDiagnostic` representations.

- M6 reframes the developer path around an executable quickstart, core
  concepts, framework-neutral integration guidance, and a product-first
  README. Public API review found no rename or semantic change necessary.

- M5 makes evaluator provenance operational: local aggregation fails closed
  with a typed, number-free conflict when indicator or methodology cohorts do
  not match. M1 remains the sole source of reliability mathematics.

- M4 extends `EvaluationRecorded` additively with optional immutable evaluator
  provenance and a bounded reason code. Existing `RunHandle.record(...)`
  remains a manual assertion and emits `provenance=None`.
- Evaluator execution failure is now explicitly distinct from
  `EvaluationOutcome.UNKNOWN`; safe execution never converts evaluator failure
  into agent `FAIL` or `UNKNOWN`.

- M3 OpenTelemetry interoperability adds an optional API-only trace-context
  bridge while preserving the M2.1 default path and failure isolation. The
  host owns provider, sampling, propagation, processing, and export.
- Agent run spans use a privacy allowlist, the constant `invoke_agent` name,
  and versioned Experimental `agent_reliability.*` attributes. Evaluations
  remain vendor-neutral events while OTel's log-based Events APIs mature.

- M2.1 runtime hardening: clock, run-ID, and internal run-start failures
  now enter a no-telemetry degraded mode so sync/async application bodies
  still execute. Degraded handles expose no fabricated IDs, valid
  `record()` calls are no-ops, and no lifecycle/evaluation events are emitted.
  This supersedes ADR-0004's original "clock/id-generator failure at
  `__enter__`/`__aenter__` may raise" sub-rule (that behavior turned out
  to prevent the application body from running at all, contradicting the
  ADR's own safety requirement) — see the new ADR-0005, which is now the
  authority on this boundary; ADR-0004's Status was changed to
  "Superseded by ADR-0005" and its original text left otherwise unedited,
  per the project's own ADR process.
- The default diagnostic logger now emits only sanitized structural
  metadata and the exception class name; it never renders exception
  messages, arguments, representations, or tracebacks (also ADR-0005).
- `AgentReliability(...)` now validates at construction that any
  supplied `sink`/`clock`/`run_id_generator`/`diagnostic_handler`
  structurally implements its port, raising `TypeError` immediately for
  a wrong object type, rather than failing later and less clearly.
- Clarified `EventSink` ordering, concurrency, exception, and lifecycle
  contracts; confirmed `CompositeEventSink` attempts all children and
  raises the first child `Exception` after fan-out.
- Explicitly classified `InMemoryEventSink` as an unbounded-retention
  test/local-inspection utility unsuitable for production.

### Added

- M7 adds public API/enum/signature compatibility tests, GA semantic and
  privacy golden tests, wheel-and-sdist release verification, supported-Python
  CI gates, and maintainer release/readiness documentation.

- M6 adds four contract-tested examples, clean installed-wheel/base/OTel-extra
  verification in CI, lightweight public issue templates, and the PEP 561
  `py.typed` marker. Base runtime dependencies remain empty.

- M5 local reliability engine:
  - immutable observation, cohort, conflict, and report values in
    `agent_reliability.reliability`;
  - pure `evaluate_reliability(...)` with explicit UNKNOWN policy and optional
    explicit burn-rate lookback;
  - exact M1-composed ratio, SLO, error-budget, and burn-rate results;
  - ADR-0008, `docs/LOCAL_RELIABILITY_ENGINE.md`, property/contract tests, and
    aggregation benchmarks;
  - no runtime dependency, I/O, persistence, logging, clock, registry,
    framework coupling, or commercial-platform coupling.

- M4 evaluator framework:
  - public `agent_reliability.evaluation` identity, decision, provenance,
    result, execution-failure, sync/async protocol, equality, and predicate
    types;
  - SDK `EvaluatorRunner` with explicit sync/async methods, injected clock, and
    existing sanitized diagnostics;
  - `RunHandle.record_evaluation(...)` for associating completed attributable
    results with a run;
  - `docs/EVALUATOR_FRAMEWORK.md`, `docs/EVALUATION_PROVENANCE.md`, and
    ADR-0007;
  - no new runtime dependency, provider/framework coupling, input capture,
    registry, timeout system, or OTel evaluation mapping.

- M3 `RunContextBridge`/`RunContextScope`, optional
  `OpenTelemetryRunContextBridge`, ADR-0006, `docs/OTEL_MAPPING.md`, real OTel
  context/parentage/failure tests, and comparison benchmarks.

- Milestone M2: the Python instrumentation SDK, under
  `agent_reliability.sdk` (not the package root), plus new
  `agent_reliability.ports`/`agent_reliability.adapters` runtime types:
  - `sdk`: `AgentReliability`, `RunHandle`, `current_run()`,
    `DiagnosticHandler`/`LoggingDiagnosticHandler`/`SdkDiagnostic`
  - `ports`: `Clock`, `RunIdGenerator`, `EventSink`,
    `RunStarted`/`RunCompleted`/`RunFailed`/`EvaluationRecorded`/`InstrumentationEvent`
  - `adapters`: `SystemClock`, `UuidRunIdGenerator`, `NoOpEventSink`,
    `InMemoryEventSink`, `CompositeEventSink`
  - ADR-0003 (SDK runtime/context architecture) and ADR-0004
    (instrumentation failure isolation) — the latter defines the exact
    rule for what raises and what is suppressed, applied consistently
    across the SDK.
  - `benchmarks/bench_sdk.py`: the first milestone with a real runtime
    path to measure (engineering baselines only, not marketing claims).
  - No M1 (`agent_reliability.domain`) code was modified. No new
    runtime dependencies (standard library only).

- Milestone M1: the reliability domain kernel, under
  `agent_reliability.domain` (not the package root). Pure, typed,
  deterministic, zero I/O:
  - `EvaluationOutcome` (`PASS`/`FAIL`/`UNKNOWN`)
  - `AgentIdentity`
  - `AgentRun`, `RunStatus` (minimal four-state lifecycle)
  - `UnknownPolicy`, `ObservationCounts`, `RatioResult`, `compute_ratio`
  - `ObjectiveDirection`, `Slo`, `SloStatus`, `SloEvaluation`, `evaluate_slo`
  - `BudgetStatus`, `ErrorBudget`, `BurnRate`, `compute_error_budget`,
    `compute_burn_rate`
  - ADR-0002 resolves the ratio-math and undefined-data semantics this
    kernel implements, correcting an ambiguity found in the M0
    `SLO_SEMANTICS.md` draft. All public symbols remain pre-alpha with
    no compatibility guarantee (see `docs/COMPATIBILITY.md`).

- Repository foundation (milestone M0): engineering principles,
  architecture and domain-model specifications, telemetry contract
  approach, SLO/error-budget/burn-rate mathematics specification,
  security threat model, testing strategy, ADR process
  (ADR-0001: architecture and dependency boundaries), and CI.
- `agent_reliability` package skeleton: layered `domain` / `application`
  / `ports` / `adapters` / `experimental` structure, all currently
  empty placeholders. Public API is limited to `__version__`.

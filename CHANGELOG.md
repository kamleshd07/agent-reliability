# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/); versioning
follows [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md).

## [1.2.0] - 2026-09-08

Developer-adoption additive release ("DX-1 — Developer Adoption").
Existing public APIs, reliability/SLO semantics, `UnknownPolicy` behavior,
the evaluator protocol, degraded-mode behavior, OTel behavior, and
provenance semantics are unchanged. Base runtime dependency count remains
zero.

**Naming note:** this milestone is referred to as **"DX-1 — Developer
Adoption"**, not "M8", in this and future release-facing documentation.
`docs/ROADMAP.md` already has an unrelated, older, still-planned milestone
named "M8 — Framework integrations" (separate adapter packages such as
`agent-reliability-langchain`); this developer-adoption work is not that
effort and does not renumber or otherwise change that roadmap entry. (Some
in-repo test/module names and prior commit messages still say "m8"/"M8" for
this milestone; those are not rewritten here — see the individual files'
docstrings for a pointer back to this note.)

### Added

- `agent_reliability.evaluation.EvaluationOutcome` as an additive re-export
  of `agent_reliability.domain.EvaluationOutcome` (same object; fixes an
  ImportError-on-first-try friction point — every sibling evaluation type
  already lived in `agent_reliability.evaluation`).
- `agent_reliability.reliability.evaluate_reliability_or_raise(...)` and
  `AggregationConflictError`: a convenience wrapper around
  `evaluate_reliability(...)` that raises instead of returning
  `AggregationConflict`, for call sites with no recovery path other than
  failing loudly. The explicit, non-raising API is unchanged.
- Built-in evaluators in `agent_reliability.evaluation`: `ContainsEvaluator`,
  `RegexMatchEvaluator` (stdlib `re` only, fails fast on a malformed pattern
  at construction time), `LatencyThresholdEvaluator` (explicit
  developer-supplied duration; a missing measurement is `UNKNOWN`, never
  `FAIL`), and `ToolCalledEvaluator`/`ToolNotCalledEvaluator` (operate only
  on a bounded `frozenset[str]` of tool names, never arguments or results).
- New `agent_reliability.reporting` namespace: `format_report(...)` (human-
  readable text) and `report_to_dict(...)` (JSON-compatible primitive
  structures) render an existing `ReliabilityReport` without recomputing any
  of its values.
- New `agent_reliability.testing` namespace: `assert_slo_met(...)`, a
  framework-neutral assertion helper (zero runtime dependency, no pytest
  plugin) usable from `pytest`, `unittest`, or plain scripts.
- Three new runnable, contract-tested examples:
  `examples/builtin_evaluators_quickstart.py`, `examples/slo_assertion.py`,
  and `examples/tool_call_evaluators.py`.
- New task-first docs: `docs/EVALUATE.md`,
  `docs/MEASURE_RELIABILITY_LOCALLY.md`, `docs/TEST_RELIABILITY.md`, linked
  from `docs/README.md` and `docs/QUICKSTART.md`.
- `jsonschema`-backed `JsonSchemaEvaluator` was deliberately **not** added:
  it would either require a new mandatory/optional dependency or a
  hand-rolled, non-compliant partial validator. Deferred pending a real
  design for that tradeoff.

### Fixed

Pre-merge remediation following independent review, before this branch
merges. No public symbol was added or removed; no reliability/SLO/OTel/
`UnknownPolicy`/`EvaluatorIdentity` semantic was changed.

- `ContainsEvaluator(substring="")` is now rejected with `ValueError` at
  construction time. It previously accepted an empty substring, which made
  the evaluator PASS on every input (Python's own `"" in value` is always
  `True`) — a silent, always-100%-reliability misconfiguration. A
  whitespace-only substring (e.g. `" "`) is still accepted; only the truly
  empty string is rejected.
- `report_to_dict(...)` no longer emits rounded `*_float` convenience
  fields (`pass_ratio_float`, `fail_ratio_float`, `target_float`,
  `remaining_fraction_float`, `value_float`) alongside the exact
  numerator/denominator representation. Only the exact representation
  remains; `format_report`'s human-readable text output is unaffected.
- `tests/compat/test_public_api_1_0.py` had been loosened from exact export
  equality to a subset check applied globally, which silently removed
  exact-lock protection from the five 1.0 namespaces this milestone did not
  touch (`domain`, `sdk`, `ports`, `adapters`, `adapters.otel`). Those five
  are exact-locked (`==`) again; only `evaluation` and `reliability` (the
  two namespaces this milestone legitimately grew) keep a baseline-subset
  (`<=`) check, with their full current export set separately exact-locked
  in `tests/unit/test_package.py`.
- `ToolCalledEvaluator`/`ToolNotCalledEvaluator` now also reject a
  blank-after-strip `tool_name` (e.g. `"   "`) at construction, not just an
  empty one; a non-blank name is still matched exactly, with no stripping.
- Added an explicit, non-vague docstring warning to each of the five new
  evaluators (`ContainsEvaluator`, `RegexMatchEvaluator`,
  `LatencyThresholdEvaluator`, `ToolCalledEvaluator`,
  `ToolNotCalledEvaluator`) stating that a configuration change which can
  change judgments must be paired with a manual `EvaluatorIdentity.version`
  or `configuration_id` bump — this pre-existing cohort-aggregation
  behavior is unchanged, only documented and now covered by a regression
  test.

## [1.1.1] - 2026-08-29

Measurement Health hardening release. Public APIs, reliability and SLO
semantics, runtime behavior, supported Python versions, and dependency
metadata are unchanged from `1.1.0`.

### Hardened

- Added a frozen 1.1 measurement-health API snapshot plus deterministic
  combined-failure, ordering, nested-run, async-concurrency, multiple-evaluator,
  privacy, retention, OTel, and reliability/SLO regression coverage.
- Added offline, contract-tested fail-open, fail-closed, and
  bounded-degradation application examples without introducing SDK
  authorization semantics or new public symbols.

## [1.1.0] - 2026-08-29

### Added

- First-class, vendor-neutral measurement health through the new
  `agent_reliability.measurement` namespace, with immutable `HEALTHY`,
  `DEGRADED`, and `UNAVAILABLE` states and bounded privacy-safe reason codes.
- Run-local health tracking for initialization, evaluator, timestamp, and
  event-delivery failures while preserving non-blocking instrumentation.
- `RunHandle.record_evaluation_failure(...)`, keeping execution failure
  distinct from `EvaluationOutcome.UNKNOWN`.
- Generic `MeasurementPolicy[T]` with application-owned results; the SDK
  defines no action criticality or authorization decisions.
- Independent health visibility on reliability reports and provenance
  conflicts without changing reliability mathematics.
- ADR-0009, focused documentation, deterministic failure injection, property,
  async/nesting, compatibility, and planted-secret tests.

### Compatibility and security

- Frozen 1.0 exports, callable signatures, event meanings, UNKNOWN semantics,
  SLO mathematics, and degraded-mode execution behavior remain unchanged.
- Health retains bounded structural enums, uses O(1) state per active run, and
  adds no base runtime dependency or payload/exception leakage channel.

## [1.0.1] - 2026-08-26

Documentation-only patch release. Public APIs, reliability semantics, runtime
behavior, supported Python versions, dependency metadata, and the stable 1.0
contract are unchanged.

### Fixed

- Replaced repository-relative links in the package README with canonical
  GitHub URLs so documentation and example links resolve correctly on PyPI
  and other package indexes as well as GitHub.
- Added a focused contract test that rejects package-index-unsafe relative
  links while allowing absolute URLs and same-document anchors.

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

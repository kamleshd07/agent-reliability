# Roadmap

No dates are attached to any milestone below, intentionally. Milestones
are ordered by dependency, not by calendar.

## M0 — Repository & specification foundation

Repository structure, engineering principles, domain model
specification, telemetry contract approach, SLO mathematics
specification, security threat model, testing strategy, ADR process,
and minimal CI. Zero business logic.

## M1 — Reliability domain kernel

`AgentIdentity`, `AgentRun` identity/lifecycle primitives,
`EvaluationOutcome`, `ReliabilityIndicator` primitives, SLO definition
and evaluation, error-budget calculation, burn-rate calculation. Pure
domain logic: zero database, network, or LLM dependencies. High test
rigor including property-based tests. Fully typed. Deterministic. See
[DOMAIN_MODEL.md](DOMAIN_MODEL.md) and [SLO_SEMANTICS.md](SLO_SEMANTICS.md)
for the specifications this milestone implements.

## M2 — Python instrumentation SDK

The user-facing API surface for recording runs and evaluations from
application code (sync, async, threaded, web, background-worker
contexts). Context propagation via `contextvars`. Failure isolation and
bounded overhead become concretely testable here — this is also where
`benchmarks/` is introduced (see [ARCHITECTURE.md](ARCHITECTURE.md)).

### M2.1 — Instrumentation runtime hardening

A follow-up hardening pass on M2, not a new top-level milestone: found
that a clock or run-id-generator failure inside `__enter__`/`__aenter__`
was allowed to raise under M2's original failure-isolation rule
(ADR-0004), which — because Python never runs a context manager's body
unless entry succeeds — meant a broken instrumentation dependency could
still prevent the application code being instrumented from running at
all, contradicting the SDK's own core safety requirement. M2.1
introduces a degraded-run mode for exactly that case (see
[ADR-0005](adr/0005-instrumentation-initialization-degraded-mode.md),
which supersedes ADR-0004's `__enter__`/`__aenter__` sub-rule), sanitizes
the default diagnostic logger to stop rendering exception message
content, and adds constructor-time validation that injected SDK
dependencies structurally implement their ports. No public symbol was
added; `RunHandle.run_id` widens from `str` to `str | None`.

## M3 — OpenTelemetry bridge

Concrete telemetry emission aligned with OTel GenAI semantic
conventions, per [TELEMETRY_SPEC.md](TELEMETRY_SPEC.md). This is where
the OTel integration strategy, schema versioning mechanism, and
project-specific namespace get decided via ADR and actually implemented.
M3 is now implemented via the optional API-only run-context bridge, ADR-0006,
and [OTEL_MAPPING.md](OTEL_MAPPING.md). It adds no provider, exporter, custom
propagation, metrics, or evaluation-event mapping.

## M4 — Evaluator framework

Implemented: separate typed sync/async evaluator protocols, immutable
behavior/configuration identity and provenance, explicit evaluation decisions
and results, safe execution failures, equality/predicate evaluators, and
run-event association. The framework retains no evaluation input and has no
provider, agent-framework, hosted-platform, or runtime dependency. LLM-as-judge
remains deliberately deferred until a later adapter milestone can define its
privacy, nondeterminism, remote-failure, and provenance semantics explicitly.

## M5 — Local reliability engine

Implemented: a local, offline, immutable report computed from explicit
`ReliabilityObservation` values. The engine validates exact indicator and M4
methodology cohorts, preserves manual/evaluated separation, rejects
incompatible full/lookback collections without a partial number, and composes
M1 ratio, SLO, error-budget, and burn-rate values. It does not depend directly
on telemetry transport events and never counts `EvaluationExecutionFailure`.
No backend, I/O, window selection, or new runtime dependency is required.

## M6 — Developer experience

Implemented: an executable quickstart, product-first README, concepts and
integration guidance, four contract-tested examples, PEP 561 packaging, and
clean-wheel/base/OTel-extra verification. No core semantic or runtime-
dependency change was required.

## M7 — GA hardening

Implemented in the pre-release tree: normative GA/compatibility/deprecation
contracts, public API and semantic regression locks, security/privacy review,
single-source versioning, supported-Python CI, and wheel/sdist release gates.
Operational release prerequisites and the final verdict are tracked in
[GA_READINESS.md](GA_READINESS.md).

## M8 — Framework integrations

Separate adapter packages (e.g. `agent-reliability-langchain`,
`agent-reliability-crewai`) built on the M2 SDK and M4 evaluator
framework, kept out of core dependencies per
[ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md) #3 and #9.

## M9 — Remote ingestion / backend

An optional ingestion backend for organizations that want centralized,
multi-agent, multi-environment reliability data, built as a consumer of
the contracts established in M0–M3 — not a redesign of them.

## M10 — Enterprise reliability control

The longer-term "AI Reliability Control Plane" direction referenced in
[VISION.md](VISION.md): diagnosis and recommendation, and eventually
guarded control actions. Explicitly not scoped or designed in detail
until the milestones above exist and are in real use.

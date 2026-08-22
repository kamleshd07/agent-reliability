# Roadmap

No dates are attached to any milestone below, intentionally. Milestones
are ordered by dependency, not by calendar.

## M0 — Repository & specification foundation *(this milestone)*

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

## M3 — OpenTelemetry bridge

Concrete telemetry emission aligned with OTel GenAI semantic
conventions, per [TELEMETRY_SPEC.md](TELEMETRY_SPEC.md). This is where
the OTel integration strategy, schema versioning mechanism, and
project-specific namespace get decided via ADR and actually implemented.

## M4 — Evaluator framework

The `Evaluator` protocol, provenance tracking, and initial deterministic/
rule-based evaluator implementations. LLM-as-judge evaluators arrive
here as one implementation among several, never as a requirement for the
core.

## M5 — Local reliability report

A local, offline report (the `Task Success / Correctness / Policy
Compliance / Tool Reliability / SLO / Error Budget / Burn Rate / Status`
view described in the project's product thesis) computed entirely from
locally recorded runs and evaluations — no backend required, honoring
the vision that the OSS SDK stands on its own.

## M6 — Agent SLO monitoring

Continuous (not just batch-report) SLO evaluation and reliability-state
tracking over live traffic.

## M7 — Reliability regression detection

Comparing reliability indicators across `AgentIdentity` versions to
surface regressions automatically.

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

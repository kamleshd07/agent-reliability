# Telemetry Contract

Status: the M2 vendor-neutral event contract, M3 OpenTelemetry run-span
mapping, and M4 evaluation provenance extension are implemented. M5 adds
pure local analysis and does not change or emit telemetry.
Evaluation-to-OpenTelemetry mapping remains deferred.

## Principle

This project does not invent its own trace/span infrastructure. Domain
`AgentRun` values deliberately carry no OpenTelemetry types or identifiers.
The optional runtime adapter participates in the host's current OTel context
without changing the domain. Our additional semantics concern
*agent reliability* — they extend telemetry, they do not replace
distributed tracing, metrics, or logging as already defined by OTel.

## M4 evaluation event extension

`EvaluationRecorded` preserves its existing run ID, indicator, outcome, and
recording timestamp. It additively carries optional immutable evaluator
provenance and a bounded reason code. `provenance=None` identifies the existing
manual assertion path; evaluator-produced records contain evaluator name,
opaque version, optional configuration identity, evaluation completion time,
and determinism declaration. No evaluation input, output, evidence payload,
score, exception, or arbitrary metadata is emitted.

This remains a vendor-neutral `EventSink` event. M4 does not add an OTel event,
span attribute, metric, log mapping, or semantic-convention claim.

## M3 resolution and continuing review rule

Before this project adopts or changes a span name or attribute key, it must:

1. Inspect the current OpenTelemetry **GenAI semantic conventions**
   (`gen_ai.*`) as published at implementation time — they are still
   evolving upstream and must be re-checked, not assumed from memory.
2. Identify which existing standard attributes already cover a given
   concept (e.g. model name, token counts, operation name) and reuse
   them verbatim rather than re-inventing parallel keys.
3. Namespace anything genuinely new to agent-reliability concerns (see
   below) and mark it experimental.
4. Document the stability level of every convention adopted or
   introduced.

M3's normative mapping, reviewed upstream versions, stability, privacy, and
compatibility rules are in [OTEL_MAPPING.md](OTEL_MAPPING.md).

## Namespacing

- Attributes and events defined by this project, not by OpenTelemetry
  upstream, live under a distinct namespace prefix reserved for this
  project. M3 selected `agent_reliability.*`; every such attribute is
  Project Experimental and is not presented as an upstream convention.
- Nothing under that namespace is considered stable until explicitly
  promoted; see versioning below.

## Illustrative conceptual events (names not final)

```text
agent.run.started
agent.run.completed
agent.evaluation.completed
agent.reliability.changed
agent.slo.breached
```

These are placeholders to communicate intent (a run lifecycle, an
evaluation being recorded, a reliability-state transition, an SLO
breach) — not a committed schema. The M3 ADR ("OpenTelemetry integration
strategy") replaces this list with real, versioned definitions, informed
by step 1–4 above.

## Schema/convention versioning mechanism

Every project-specific semantic convention (attribute key, event
schema, or event name) must carry an explicit stability marker:

```text
experimental   — may change or be removed in any release
stable         — follows semantic versioning; breaking changes require
                 a major version bump and a deprecation window
```

M3 identifies its mapping with `agent_reliability.schema.version=1`. It does
not claim an OpenTelemetry schema URL because the project has not published a
schema file or transformation.
What is decided now is that **no experimental convention may be
described as part of a "stable" telemetry contract**; the two must
never be presented to users as equally reliable.

## Relationship to the domain model

Telemetry is the "what occurred" layer (see the layering table in
[DOMAIN_MODEL.md](DOMAIN_MODEL.md)). It is a *source of facts* that the
application layer may use to construct `AgentRun`s; it is never itself
an `Evaluation`, `SLI`, or `ReliabilityState`. Nothing in this document
authorizes deriving task success from a span's status code — see the
explicit rule against conflating HTTP/transport success with task
success in [DOMAIN_MODEL.md](DOMAIN_MODEL.md).

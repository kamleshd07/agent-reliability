# Telemetry Contract

Status: **specification only**, and even at the specification level,
partially deferred. No telemetry emission exists yet in this repository
(that begins at M2/M3). This document exists so that when it is built,
it is built on OpenTelemetry rather than around it.

## Principle

This project does not invent its own trace/span infrastructure. Every
`AgentRun` carries the OpenTelemetry `trace_context` it belongs to (see
[DOMAIN_MODEL.md](DOMAIN_MODEL.md)). Our additional semantics concern
*agent reliability* — they extend telemetry, they do not replace
distributed tracing, metrics, or logging as already defined by OTel.

## Before defining any attribute or event name

Before this project adopts a single span name or attribute key, the
implementing milestone (M3, "OpenTelemetry Bridge") must:

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

This document intentionally does **not** freeze `gen_ai.*` attribute
names today, because doing so risks contradicting the upstream
convention by the time it's implemented. What it does freeze is the
*namespacing and versioning discipline* below.

## Namespacing

- Attributes and events defined by this project, not by OpenTelemetry
  upstream, live under a distinct namespace prefix reserved for this
  project (exact prefix decided at M3, alongside the OTel-integration
  ADR — candidates include `agent_reliability.*` or a shorter
  project-specific prefix once the project's final name is set; see
  the working-name note in the repository root).
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

The mechanism for attaching that marker (a schema version attribute
alongside each event, a documented convention registry file, or
something else) is an open decision for the M3 ADR — not decided here.
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

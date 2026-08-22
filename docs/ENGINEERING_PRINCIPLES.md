# Engineering Principles

These principles are non-negotiable for this project. They exist because
this SDK is meant to be embedded in other people's production systems,
and its telemetry and reliability contracts may eventually be depended
upon at scale. When a principle and a convenient shortcut conflict, the
principle wins; if it shouldn't, that's an ADR, not a silent exception.

## 1. Correctness before convenience

Reliability calculations must have mathematically documented behavior.
Ambiguous semantics (what counts as a "good" event, how an UNKNOWN
evaluation affects a ratio, how a burn rate is defined) must never be
inferred silently by an implementation detail. If the math isn't
written down in [SLO_SEMANTICS.md](SLO_SEMANTICS.md) or
[DOMAIN_MODEL.md](DOMAIN_MODEL.md) first, it doesn't get implemented.

## 2. Deterministic core

The reliability engine (SLI/SLO/error-budget/burn-rate computation) must
be deterministic given identical inputs. LLMs may eventually be used as
*evaluators* that produce inputs to the engine, but the engine itself
must never require an LLM call to produce a result, and must never
produce different output for the same input.

## 3. Vendor neutrality

The core cannot depend, even conceptually, on OpenAI, Anthropic, Google,
AWS Bedrock, LangChain, LlamaIndex, CrewAI, AutoGen, any single model, or
any single agent framework. All such integrations live behind adapters
(`agent_reliability.adapters`) or in separate packages — never in
`domain`, `application`, or `ports`.

## 4. OpenTelemetry alignment

Prefer interoperability with OpenTelemetry over inventing a proprietary
tracing system. Reuse OTel GenAI semantic conventions where they exist.
Project-specific agent-reliability semantics extend telemetry — they do
not replace it. Experimental conventions are isolated and versioned; see
[TELEMETRY_SPEC.md](TELEMETRY_SPEC.md).

## 5. Failure isolation

Instrumentation must never cause the instrumented application to fail.
A telemetry backend outage, a slow exporter, a full queue, a
serialization error, an evaluator that throws, or a timeout must all
degrade gracefully (drop-with-counter, not propagate-exception).

## 6. Bounded overhead

The SDK will have explicit performance budgets once there is code to
measure (see `benchmarks/`, established at the milestone that first adds
runtime instrumentation). Expensive evaluation never runs synchronously
in the application's critical path unless explicitly requested by the
caller.

## 7. Privacy by design

Agent telemetry may contain prompts, responses, PII, financial data,
health data, secrets, tool parameters, or database contents. Metadata-
only operation is a first-class mode, not an afterthought. Raw payload
capture is opt-in, configurable, and redactable — never an implicit
default.

## 8. Stable contracts

Public SDK APIs and emitted telemetry are contracts. They follow
Semantic Versioning once declared stable. Experimental interfaces are
explicitly labeled experimental (see
`agent_reliability.experimental` and
[COMPATIBILITY.md](COMPATIBILITY.md)) and may change without notice.

## 9. Framework independence

The core domain works with zero agent frameworks installed. No import in
`domain`, `application`, or `ports` may require LangChain, CrewAI,
AutoGen, or any other framework to be present.

## 10. Dependency discipline

Runtime dependencies are minimal by default and zero at M0. Every
runtime dependency must justify itself in the PR that introduces it —
"it's convenient" is not sufficient justification.

## 11. Composition over framework magic

Prefer protocols, typed interfaces, explicit dependency injection, and
immutable value objects. Avoid global mutable state, decorators that
hide substantial behavior, reflection-heavy designs, and magical
registries.

## 12. Observability of the observability system

The SDK must eventually expose its own operational health: dropped
events, queue pressure, exporter failures, evaluation failures, internal
latency, processing errors. A reliability SDK that fails silently is
worse than useless.

## 13. Backpressure must be explicit

No unbounded queues, ever. Every queue has a documented capacity and a
documented behavior when that capacity is exceeded (drop oldest, drop
newest, block with timeout — pick one and document it).

## 14. Time semantics are first-class

All domain timestamps are timezone-aware UTC. Naive `datetime` values
are never accepted into a domain contract. Observation windows have
explicit, documented boundary semantics (closed/open, inclusive/
exclusive).

## 15. No premature distributed architecture

No Kafka, Kubernetes, microservices, Redis, ClickHouse, or service mesh
during initial SDK development, unless justified by an ADR that
demonstrates a concrete scaling requirement the modular monolith cannot
meet.

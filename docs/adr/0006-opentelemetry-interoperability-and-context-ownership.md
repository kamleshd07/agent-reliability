# ADR-0006: OpenTelemetry interoperability and context ownership

## Status

Accepted

## Context

M3 adds optional OpenTelemetry interoperability while preserving the M2.1
run lifecycle, failure isolation, privacy posture, and vendor-neutral domain.
An Agent Reliability run must provide a current OpenTelemetry span while user
code executes so nested HTTP, database, model, and agent instrumentation can
join the same trace.

The existing `EventSink` receives point-in-time events. OpenTelemetry span
creation does not itself activate a span; activation returns a scope/token
whose lifetime must surround user execution. Leaving a context attached after
`EventSink.emit` returns would give a sink invisible ownership of execution
scope and no reliable, paired teardown. It also makes partial startup and
nested-run cleanup difficult to reason about.

OpenTelemetry's GenAI agent conventions are Development status, and its event
model is moving from span events to log-based events. The Python API/SDK and
general tracing/logs specifications are stable, but not every GenAI mapping or
ergonomic event API is.

## Decision

1. Add a narrow `RunContextBridge` port. `start(run)` returns a
   run-specific scope; `finish(status, exception_type)` closes it. This is a
   lifecycle port, not a generic plugin mechanism.
2. `AgentReliability` owns invocation timing. It activates the bridge after
   the SDK run/context exists and finishes it after the terminal event but
   before the SDK context is restored.
3. Add an optional OpenTelemetry adapter. It creates one constant-name
   `INTERNAL` span per non-degraded run, activates it with OpenTelemetry's
   context manager, restores the prior context, and ends the span.
4. The adapter depends only on `opentelemetry-api`. It never installs an SDK,
   exporter, processor, sampler, propagator, or global provider. The host owns
   all OpenTelemetry configuration.
5. Use official semantic attributes only where their specified span applies.
   Use project-prefixed Experimental attributes for remaining run identity and
   outcome fields, with an explicit mapping version and no false schema URL.
6. Do not record exception objects, messages, stack traces, prompts,
   responses, tool data, arbitrary attributes, user data, or baggage.
7. Do not map `EvaluationRecorded` in M3. Continue emitting it through the
   vendor-neutral `EventSink` while OpenTelemetry's log-based event and GenAI
   evaluation conventions mature.
8. Bridge failures are isolated as diagnostics. They must not degrade an
   already valid SDK run, suppress SDK events, or replace a user exception.
   Cleanup is best-effort and attempts every independent cleanup action.
9. The default is `None`, adding no required dependency, provider lookup, or
   span work to installations that do not opt in.

The normative attribute/status mapping is in
[`docs/OTEL_MAPPING.md`](../OTEL_MAPPING.md).

## Alternatives Considered

### Implement OpenTelemetry as an `EventSink`

Rejected. A sink invocation is shorter than the required context lifetime.
Retaining an activation token across unrelated `emit` calls creates hidden
scope ownership and unreliable teardown when initialization or other sinks
fail.

### Add OpenTelemetry objects to the domain or public run handle

Rejected. This reverses dependency direction, makes the base package require a
vendor API, and leaks infrastructure state into vendor-neutral contracts.

### Use hooks or a generic plugin list

Rejected. M3 needs exactly one paired context lifecycle. A generic extension
mechanism enlarges the public surface and creates ordering and failure-policy
questions unrelated to this milestone.

### Configure a default SDK/exporter or global provider

Rejected. Library configuration would conflict with host applications, add
backend and worker scope, and make the optional integration surprising.

### Encode run IDs as trace/span IDs or baggage

Rejected. OpenTelemetry owns identifier generation and propagation. Reusing
application identifiers can violate formatting/randomness expectations and
creates privacy and interoperability risks.

### Emit evaluations as span events

Rejected for M3. OpenTelemetry has announced the migration away from span
events. Binding a new contract to that API would incur avoidable migration and
could duplicate sensitive evaluation payloads.

## Consequences

- User code and nested instrumentation see the run span as current.
- Nested runs and multiple SDK instances compose via OpenTelemetry's normal
  context stack without shared Agent Reliability state.
- The SDK gains one optional constructor dependency and one small port.
- OpenTelemetry integration can fail independently of the run/event lifecycle.
- Evaluation interoperability remains future work with an explicit rationale.
- If the OpenTelemetry runtime itself cannot restore a corrupt context, the
  adapter can diagnose and end its span but cannot guarantee repair of that
  external runtime's context stack.

## Security Impact

Positive. The adapter has an allowlist mapping and disables automatic
exception recording. It exports no content payloads or baggage. Operators must
still ensure agent identity values and run IDs contain no secrets; the core
types intentionally do not impose deployment-specific content policies.

## Performance Impact

Without the optional bridge, the hot path adds only a `None` branch. With it,
one span and one context activation are created per run, subject to the host's
sampler and SDK limits. Attribute keys are fixed and no event payloads are
copied. The adapter does not flush or perform I/O.

## Compatibility Impact

The base dependency set remains empty and existing constructor calls continue
to work. The OpenTelemetry adapter is imported explicitly from its optional
module, so importing the base package and existing adapters works without
OpenTelemetry installed. All APIs remain pre-alpha under the repository's
compatibility policy.

# OpenTelemetry interoperability mapping

This document defines the M3 mapping from an Agent Reliability run to
OpenTelemetry. It is an interoperability contract, not a replacement for the
SDK's vendor-neutral event model.

## Standards baseline

The design was checked on 2026-08-25 against:

- [OpenTelemetry Specification 1.60.0](https://opentelemetry.io/docs/specs/otel/)
- [OpenTelemetry Semantic Conventions 1.44.0](https://opentelemetry.io/docs/specs/semconv/)
- [OpenTelemetry Python API and SDK 1.44.0](https://opentelemetry.io/docs/languages/python/)
- [OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai),
  whose agent conventions are Development status. The former specification
  location now redirects readers to this independently versioned repository.

The Python package uses the OpenTelemetry API only at runtime. A host
application decides whether to install and configure an SDK, processors,
samplers, propagators, and exporters. Agent Reliability installs none of
those and never changes the global provider.

## Lifecycle and context ownership

One Agent Reliability run maps to one internal span. The SDK creates the run
first, asks the configured run-context bridge to start and activate its span,
emits the vendor-neutral `RunStarted` event, executes the user's body, emits
the terminal event, then asks the bridge to deactivate and end the span.

```text
parent OpenTelemetry context
          |
          v
AgentReliability.run() enters
  create AgentRun and SDK context
  bridge.start(run)
    create INTERNAL span
    make span current  -------------------------------+
  emit RunStarted                                      |
  execute user code and nested instrumentation         |
  emit RunCompleted / RunFailed / RunCancelled         |
  bridge.finish(status, exception_type)                 |
    set terminal attributes/status                      |
    restore previous OpenTelemetry context  <-----------+
    end span
  close SDK run and restore previous SDK context
```

Span creation and context activation are distinct OpenTelemetry operations.
Consequently, an `EventSink.emit(RunStarted)` cannot safely implement this
lifecycle: its call has returned before user code executes, while the
activation token must remain owned and later closed by the same run scope.
M3 therefore uses a separate, narrow run-context bridge port. The SDK owns
when it is called; the adapter owns only OpenTelemetry objects and cleanup.

Nested runs naturally inherit the current OpenTelemetry context. Multiple SDK
instances require no singleton and compose through OpenTelemetry's context
stack. No Agent Reliability identifier is used as a trace ID or span ID.

## Span mapping

The span name is the constant `invoke_agent`, and its kind is `INTERNAL`.
The current Development convention says an internal agent span SHOULD include
`gen_ai.agent.name` in its span name when readily available. This adapter makes
a documented, intentional deviation from that non-normative recommendation:
the constant name avoids user-controlled or high-cardinality span names while
the agent name remains available as an attribute. Because the upstream agent
conventions are not stable, this mapping is EXTERNAL-EVOLVING under the GA
contract; the Python bridge API remains STABLE. The bridge records the
following bounded set of attributes:

| Agent Reliability concept | OpenTelemetry signal | Mapping | Decision |
|---|---|---|---|
| `AgentIdentity.agent_id` | Span attribute | `agent_reliability.agent.id` | Project Experimental. |
| `AgentIdentity.name` | Span attribute | `gen_ai.agent.name` | Official GenAI Development. |
| `AgentIdentity.version` | Span attribute | `agent_reliability.agent.version` | Project Experimental. |
| `AgentIdentity.environment` | Span attribute when present | `agent_reliability.agent.environment` | Project Experimental. |
| `run_id` | Span attribute | `agent_reliability.run.id` | Project Experimental; correlation, never an OTel identifier. |
| `parent_run_id` | Span attribute when present | `agent_reliability.run.parent_id` | Project Experimental; OTel context independently controls trace parentage. |
| `RunStarted` | Span start | One `invoke_agent` span | Not duplicated as an event. |
| `RunCompleted` | Span end and attribute | `agent_reliability.run.status=completed` | Not duplicated as an event. |
| `RunFailed` (failure) | Span end, attributes, status | `run.status=failed`, `error.type`, OTel `ERROR` | No exception object/content. |
| `RunFailed` (cancellation) | Span end and attribute | `run.status=cancelled`, OTel status `UNSET` | No exception object/content. |
| `EvaluationRecorded` | Deferred | None in OTel M3 | Remains in the Agent Reliability `EventSink`. |
| `indicator` | Deferred with evaluation | None in OTel M3 | Would be a bounded event field, not a metric dimension by default. |
| `EvaluationOutcome` | Deferred with evaluation | None in OTel M3 | Future mapping must preserve `pass`, `fail`, and `unknown`. |

| Attribute | Source/value | Stability | Notes |
|---|---|---|---|
| `gen_ai.operation.name` | `invoke_agent` | OpenTelemetry GenAI Development | Operation represented by the span. |
| `gen_ai.agent.name` | `AgentIdentity.name` | OpenTelemetry GenAI Development | Only official agent identity field applicable to this internal span. |
| `error.type` | exception class name | OpenTelemetry stable general convention | Present only for failed runs. No message or traceback is recorded. |
| `agent_reliability.schema.version` | `1` | Project Experimental | Version of the project-owned mapping below. |
| `agent_reliability.agent.id` | `AgentIdentity.agent_id` | Project Experimental | Stable application identity; not a trace identifier. |
| `agent_reliability.agent.version` | `AgentIdentity.version` | Project Experimental | Agent release/version. |
| `agent_reliability.agent.environment` | `AgentIdentity.environment` | Project Experimental | Omitted when absent. |
| `agent_reliability.run.id` | `AgentRun.run_id` | Project Experimental | Correlation only. |
| `agent_reliability.run.parent_id` | `AgentRun.parent_run_id` | Project Experimental | Omitted when absent. OpenTelemetry parentage remains authoritative. |
| `agent_reliability.run.status` | `completed`, `failed`, or `cancelled` | Project Experimental | Set at terminal transition. |

The project does not claim an OpenTelemetry schema URL: it has not published a
schema file or schema transformation. Project-owned names are explicitly
Experimental and versioned by `agent_reliability.schema.version`. Any breaking
mapping change requires a new version and an ADR.

### Terminal status

- Completed: `agent_reliability.run.status=completed`; OpenTelemetry status is
  left `UNSET`.
- Failed: `agent_reliability.run.status=failed`, `error.type` is the exception
  class name, and span status is `ERROR` without a description.
- Cancelled: `agent_reliability.run.status=cancelled`; OpenTelemetry status is
  left `UNSET` because cancellation is not necessarily an application error.

The adapter disables OpenTelemetry's automatic exception recording and status
handling. It never passes the exception object to OpenTelemetry.

## Events and evaluations

The vendor-neutral `RunStarted`, terminal, and `EvaluationRecorded` events
continue through the configured `EventSink`; they are not duplicated as span
events. OpenTelemetry is migrating events to the Logs data model and has
announced deprecation of the span-event API. Python's first-class ergonomic
Events API and the GenAI evaluation mapping are not stable enough to make a
durable M3 contract. Evaluation export is therefore deliberately deferred.

This deferral avoids coupling the package to a Logs SDK/provider or to an API
that is still changing. It does not drop Agent Reliability events.

## Privacy and cardinality

The bridge exports no prompts, responses, tool arguments/results, exception
messages, stack traces, user identifiers, arbitrary event attributes, or
baggage. It copies only the identity, correlation, and outcome fields listed
above. The span name and attribute-key set are fixed.

Agent identity values and run IDs remain user/application supplied strings.
The adapter imposes no surprising truncation; hosts should use OpenTelemetry
SDK `SpanLimits` and backend policy for deployment-specific limits. These
values must not contain secrets or unbounded end-user input.

No project attribute is put into OpenTelemetry baggage. Downstream trace
propagation is entirely the responsibility of the host's configured
OpenTelemetry propagator and child instrumentation.

## Failure and sampling behavior

The default configuration has no bridge and preserves M2.1 behavior. With the
bridge installed, OpenTelemetry failures are instrumentation failures: they
are reported through the SDK diagnostic handler and do not invalidate a
successfully created Agent Reliability run, suppress its events, or replace a
user exception. A failure during partial span startup is cleaned up by the
adapter before it reports the error. Terminal cleanup attempts both context
restoration and span ending even if one operation fails.

The bridge honors the host provider and sampler. It performs no force-sampling
and no exporting. With only the OpenTelemetry API/no-op provider installed,
calls remain valid but no recording span or external trace is produced.
Agent Reliability `EventSink` events may still exist when the corresponding
OTel trace is unsampled; neither signal is a correctness dependency of the
other.

OpenTelemetry Python context and the SDK's run context both use context-local
semantics. They isolate normal `asyncio` tasks, but M3 adds no automatic OS
thread propagation guarantee. Callers that use `contextvars.copy_context()`
for a new thread propagate both contexts present in that copied context;
otherwise a new thread should be treated as a new context. Multiprocessing is
not covered by M3.

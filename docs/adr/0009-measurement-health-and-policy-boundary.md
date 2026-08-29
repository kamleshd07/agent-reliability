# ADR-0009: Measurement health and application policy boundary

Status: Accepted

## Context

The 1.0 SDK suppresses instrumentation failures so application code continues.
Task reliability cannot communicate whether its evidence was complete and
trustworthy. `UNKNOWN` is an evaluator-produced outcome, while
`EvaluationExecutionFailure` means no outcome was produced; neither may be
changed after GA.

## Decision

### Public term and exact subject

The public term is **Measurement Health**. For one explicitly scoped run or
reliability report, it states whether SDK-observed collection, attribution,
and retention produced enough structurally valid evidence for the requested
reliability interpretation. It does not measure agent quality, application
risk, or exporter uptime in general.

“Evidence Health” is accurate at rest but less clear for evaluation and
timestamping failures that prevent evidence creation. “Measurement Health”
covers the end-to-end local path. We expose no synonym.

### States and composition

- `HEALTHY`: no SDK-observed failure compromised required evidence in scope.
- `DEGRADED`: trustworthy evidence remains, but an expected local evidence
  element is missing or was not retained.
- `UNAVAILABLE`: no safe basis remains for the requested interpretation, or
  incompatible provenance makes that interpretation invalid.

Reasons are typed, bounded, structural, and contain no exception or payload.
Reports compose by reason-set union; severity is derived. Composition is
deterministic, commutative, associative, idempotent, and monotonically
non-improving.

### Scope and lifecycle

Runtime health belongs to one `RunHandle`. It starts healthy after successful
initialization and only degrades. Failed initialization yields an unavailable
handle. Parent and child health do not propagate. Existing ContextVar task
isolation also isolates health. At most one member of each bounded reason enum
is retained: O(1) auxiliary space and no exception history.

`ReliabilityReport` exposes health independently. Existing math does not
consult it. `AggregationConflict` remains authoritative for incompatible
evidence, exposes unavailable health, and never returns a partial number.

### Failure taxonomy

| Failure | Scope | Health | Reason | Agent execution |
|---|---|---|---|---|
| evaluator raises/invalid result | evaluation/run when associated | unavailable | no outcome exists | continues under safe runner |
| evaluator timestamp clock | evaluation/run when associated | unavailable | required provenance time absent | continues |
| run ID, start clock, run construction, ContextVar setup | run | unavailable | no valid evidence scope exists | body runs degraded |
| record/end clock | run | degraded | expected event cannot be timestamped | continues |
| event sink | run | degraded | attempted evidence delivery was not retained | continues |
| diagnostic handler | diagnostic channel | none | not reliability evidence | continues; handler error dropped |
| run-context/OTel bridge | optional external context | none | local evidence remains intact | continues |
| missing provenance on manual observation | observation | none | intentional manual cohort | unchanged |
| missing evaluator provenance | evaluation | unavailable | `EvaluationResult` forbids it; importers must report it | no authorization effect |
| conflicting provenance | aggregation | unavailable plus `AggregationConflict` | incompatible methods | no authorization effect |
| partial expected evidence | scoped report | degraded | meaningful compatible evidence remains | no authorization effect |
| OTel exporter failure | host exporter | none locally | outside local measurement path | unchanged |

The SDK cannot infer global health from local failures.

### Policy boundary

`MeasurementPolicy[T]` accepts a `MeasurementHealthReport` and returns an
application-owned `T`. `RunHandle.evaluate_measurement_policy()` invokes it
explicitly. The SDK defines no criticality, context bag, ALLOW/DENY result, or
automatic hook. Policy exceptions propagate; suppressing them would silently
choose fail-open.

### Trust boundary

Run health derives from private SDK state. Applications can construct values
for transport/testing, but values are not attestations. Decisions should use
the live run snapshot or a trusted persisted copy, never agent-generated
content. No public API mutates a run back to healthy.

## Alternatives Considered

- Reuse `UNKNOWN` or manufacture it on failure: rejected; this changes 1.0
  semantics and invents an outcome.
- Global boolean: rejected; it contaminates concurrent/nested runs and loses
  partial versus unavailable distinctions.
- SDK authorization results or untyped contexts: rejected as business-policy
  scope and weak compatibility/privacy boundaries.
- Mark OTel/diagnostic failures unhealthy: rejected because optional
  observability is not local reliability evidence.

## Consequences

Applications can implement fail-open, fail-closed, or bounded degradation.
Inspect a retained handle after context exit to include terminal delivery or
timestamp failures.

## Security Impact

Only enums and a frozenset are retained. No messages, exceptions, prompts,
outputs, arguments, tracebacks, tokens, PII, or arbitrary metadata enter
health. The bounded set prevents unbounded growth.

## Performance Impact

One bounded set per active run. Snapshot/composition cost is bounded by the
fixed enum and is O(1) with respect to run duration and event count.

## Compatibility Impact

The new `agent_reliability.measurement` namespace and `RunHandle` members are
additive. All 1.0 namespace exports, callable signatures, outcomes, SLO math,
event payloads, and non-blocking behavior remain unchanged. Candidate: 1.1.0.

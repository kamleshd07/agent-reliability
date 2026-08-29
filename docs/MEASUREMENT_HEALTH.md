# Measurement health

Reliability answers “how often did the agent satisfy an indicator?”
Measurement health answers “is the evidence for that interpretation complete
and trustworthy?” These are independent dimensions.

## Semantics

`HEALTHY` means no SDK-observed failure compromised required evidence in the
scope. `DEGRADED` means meaningful trustworthy evidence remains but part of
the expected local evidence is missing. `UNAVAILABLE` means there is no safe
basis for the requested interpretation. Reasons identify only bounded
structural failure classes.

`EvaluationOutcome.UNKNOWN` means an evaluator ran and deliberately returned
an indeterminate outcome. `EvaluationExecutionFailure` means it produced no
result. An execution failure changes run health only when explicitly
associated:

```python
result = runner.evaluate(evaluator, value)
with sdk.run(agent_id="a", name="Agent", version="1") as run:
    if isinstance(result, EvaluationExecutionFailure):
        run.record_evaluation_failure(failure=result)
```

Successful `PASS`, `FAIL`, and `UNKNOWN` observations can all be healthy.

## Scope, provenance, aggregation, and async work

`run.measurement_health` is an immutable run-local snapshot. Reasons only
accumulate. Inspect after context exit to include terminal failures. Parent and
child runs do not inherit health. Concurrent tasks retain ContextVar isolation.

Manual observations intentionally lack evaluator provenance and form a valid
manual cohort. Evaluator results require provenance. Incompatible provenance
still returns `AggregationConflict`; health is unavailable and no partial
number is exposed.

The engine does not remove degraded observations or alter UNKNOWN/SLO math.
`ReliabilityReport.measurement_health` remains separate (healthy by default),
so reliability counts and evidence health are independently inspectable.

## Application policy examples

`MeasurementPolicy[T]` returns an application-owned type. These examples are
application policy, not SDK defaults:

```python
from enum import Enum
from agent_reliability.measurement import MeasurementHealth


class Decision(Enum):
    PROCEED = "proceed"
    STOP = "stop"
    READ_ONLY = "read_only"


class HighCriticalityFailClosed:
    def evaluate(self, *, measurement_health):
        return (
            Decision.PROCEED
            if measurement_health.health is MeasurementHealth.HEALTHY
            else Decision.STOP
        )


class LowCriticalityFailOpen:
    def evaluate(self, *, measurement_health):
        return Decision.PROCEED


class BoundedDegradation:
    def evaluate(self, *, measurement_health):
        return (
            Decision.PROCEED
            if measurement_health.health is MeasurementHealth.HEALTHY
            else Decision.READ_ONLY
        )
```

Invoke policy explicitly with `run.evaluate_measurement_policy(policy)`. The
SDK does not classify actions, invoke policy automatically, or catch policy
exceptions.

## Privacy and trust

Health contains only enum reasons—never prompts, outputs, tool data, exception
messages, tracebacks, credentials, PII, or evaluator payloads. A custom
diagnostic handler remains a separate trusted boundary under the 1.0 contract.

Live run health is SDK-derived and cannot be reset by the agent. Constructed
values are data, not attestations; do not trust a value supplied by acting
agent content. See [ADR-0009](adr/0009-measurement-health-and-policy-boundary.md)
for the complete failure matrix.

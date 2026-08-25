# Agent Reliability 1.0 GA contract

This document is normative for `agent-reliability 1.0.0`. It defines what a
consumer may rely on and must be read with the normative semantic documents
linked below. README and examples are explanatory; they do not override this
contract.

## Contract classes

- **STABLE:** preserved throughout 1.x under [VERSIONING.md](VERSIONING.md).
  This includes runtime behavior, Python signatures, typing, enum values, and
  documented semantics—not merely successful imports.
- **EXTERNAL-EVOLVING:** our integration API remains stable, but an emitted
  mapping follows an identified upstream standard that may evolve. A mapping
  change must be documented, tested, and follow its mapping-specific version.
- **INTERNAL:** unsupported implementation detail. It may change in any
  release. Importability does not create a promise.
- **EXPERIMENTAL:** explicitly named public functionality that may change in a
  minor release with release notes. No experimental API exists at 1.0.

## Public namespace rule

A Python name is public only when re-exported by the `__all__` of one of the
stable package namespaces below. Files, private names, submodules, and names in
their module-level `__all__` that are not re-exported by a listed package are
internal. The package root exports only `__version__`.

### Stable domain API

`agent_reliability.domain`:

```text
AgentIdentity, AgentRun, RunStatus, EvaluationOutcome
ObservationCounts, RatioResult, UnknownPolicy, compute_ratio
ObjectiveDirection, Slo, SloEvaluation, SloStatus, evaluate_slo
BudgetStatus, ErrorBudget, BurnRate, compute_error_budget, compute_burn_rate
```

### Stable instrumentation and evaluation API

`agent_reliability.sdk`:

```text
AgentReliability, RunHandle, current_run, EvaluatorRunner
SdkDiagnostic, DiagnosticHandler, LoggingDiagnosticHandler
```

`agent_reliability.evaluation`:

```text
SyncEvaluator, AsyncEvaluator, EvaluatorIdentity
EvaluationDecision, EvaluationProvenance, EvaluationResult
EvaluationFailureStage, EvaluationExecutionFailure
EqualityEvaluator, PredicateEvaluator
```

### Stable reliability API

`agent_reliability.reliability`:

```text
ReliabilityObservation, ReliabilityCohort
AggregationConflictReason, AggregationConflict
ReliabilityReport, evaluate_reliability
```

### Stable port and adapter API

`agent_reliability.ports`:

```text
Clock, RunIdGenerator, EventSink
RunContextBridge, RunContextScope
RunStarted, RunCompleted, RunFailed, EvaluationRecorded
InstrumentationEvent
```

`agent_reliability.adapters`:

```text
SystemClock, UuidRunIdGenerator
NoOpEventSink, InMemoryEventSink, CompositeEventSink
```

`agent_reliability.adapters.otel`:

```text
OpenTelemetryRunContextBridge
```

The OTel Python constructor and bridge lifecycle are stable. The precise span
mapping is external-evolving as described below.

## Callable and value-object contract

Public parameter names, positional/keyword-only behavior, defaults, return
unions, and documented exceptions are stable. Compatibility tests selectively
lock the highest-risk signatures; type checking protects the broader surface.

Public dataclasses are immutable value objects with structural equality. Their
field order and existing positional construction are stable. Adding a required
field, changing equality/hash behavior, making positional calls invalid, or
changing a field's meaning is breaking. A future optional trailing field may
be added only after compatibility analysis; consumers should prefer keyword
construction when maintainable.

Public Protocol members are stable. Adding a required member can break
structural implementations and is therefore a breaking change. Protocols do
not imply inheritance or registration requirements.

Enum member names and values are stable. Removing, renaming, or changing a
value is breaking. Adding a member is also treated as potentially breaking
because downstream exhaustive matches may exist; it requires explicit
compatibility review rather than being assumed safe.

## Frozen outcome and uncertainty semantics

- `PASS`: evaluation completed and the measured condition was satisfied.
- `FAIL`: evaluation completed and the measured condition was not satisfied.
- `UNKNOWN`: evaluation completed but could not determine a definitive result.
- `EvaluationExecutionFailure`: evaluation or provenance timestamping failed;
  it is not an outcome and produces no reliability observation.

`UnknownPolicy` is mandatory at each ratio/reliability calculation:

- `EXCLUDE`: unknown outcomes count in raw totals but not the denominator.
- `TREAT_AS_BAD`: unknown outcomes enter the denominator as failures.
- `TREAT_AS_GOOD`: unknown outcomes enter the denominator as passes.

There is no implicit, global, SDK, or environment-variable policy.

## Frozen reliability mathematics

All normative ratios use `fractions.Fraction`. Display conversion to decimal
or float is a caller concern. Every supplied observation is counted once; the
library performs no deduplication. Compatible observation multisets are order
independent and iterables are consumed once with O(1) auxiliary aggregation
memory.

No considered observations means `pass_ratio`/`fail_ratio` are `None`, SLO
status is `UNKNOWN`, and budget status is `NO_DATA`. Reliability is never
invented from empty data.

An SLO is met when observed bad fraction is **less than or equal to** allowed
bad fraction. Exact equality is met for both `AT_LEAST` and `AT_MOST`.

Error-budget consumption and burn rate use the same exact formula:

```text
observed bad fraction / allowed bad fraction
```

Error budget uses the supplied full-window ratio. Burn rate uses a separately
supplied lookback ratio; Agent Reliability does not choose time windows.
Remaining budget is not clamped and may be negative.

Zero-tolerance objectives produce `ZERO_TOLERANCE_INTACT` with exact value
zero when no bad outcome exists, or `ZERO_TOLERANCE_EXCEEDED` with no numeric
consumption when any bad outcome exists. No NaN or infinity is introduced.

Normative detail: [SLO semantics](SLO_SEMANTICS.md) and
[local reliability engine](LOCAL_RELIABILITY_ENGINE.md).

## Measurement-integrity contract

Evaluated observations are compatible only when these values match exactly:

```text
indicator
evaluator identity.name
evaluator identity.version
evaluator identity.configuration_id (including None)
provenance.deterministic
```

Manual observations form a separate cohort and cannot mix with evaluated
observations. Full and non-empty lookback cohorts must match. Incompatibility
returns `AggregationConflict` with bounded reasons and no partial number.
Evaluator timestamps do not form part of the compatibility key.

Normative detail: [evaluation provenance](EVALUATION_PROVENANCE.md).

## Failure contract

- Programmer misuse and invalid public values raise `TypeError`, `ValueError`,
  `RuntimeError`, or ordinary underlying Python errors as documented. Exact
  prose is diagnostic, not a machine protocol.
- Instrumentation dependency `Exception`s are diagnosed and isolated; they do
  not prevent the run body or replace its exception. Initialization failure
  produces a degraded handle with no fabricated run ID or events.
- `KeyboardInterrupt`, `SystemExit`, `GeneratorExit`, and async cancellation
  are not swallowed. Cleanup may catch `BaseException` only to restore state,
  then re-raises the original control signal.
- Raw evaluator calls have ordinary exception behavior. `EvaluatorRunner`
  converts evaluator `Exception`s to `EvaluationExecutionFailure` and never to
  `FAIL` or `UNKNOWN`.
- Analytical incompatibility is a returned `AggregationConflict`, not an
  exception and never a partial `ReliabilityReport`.
- Empty data is a valid typed no-data report, not an exception.

## OpenTelemetry boundary

`OpenTelemetryRunContextBridge` and host-ownership semantics are **STABLE**.
The exact span name, upstream `gen_ai.*` fields, and upstream convention
alignment are **EXTERNAL-EVOLVING**. Project-owned
`agent_reliability.*` attributes are Experimental mapping fields governed by
`agent_reliability.schema.version`; they are not stable Python APIs.

The adapter depends only on the optional OTel API, never installs a provider,
sampler, propagator, processor, exporter, or SDK, and never changes the global
provider. See [OTEL_MAPPING.md](OTEL_MAPPING.md).

## Concurrency and process boundary

Sync and async context managers, nested runs, normal `asyncio` task isolation,
and tested thread behavior are stable. Explicitly copied `contextvars`
contexts carry SDK/OTel context. Automatic propagation to arbitrary new OS
threads is not promised. Fork/multiprocessing behavior is not specified.

## Privacy and offline contract

Base instrumentation, deterministic evaluation, and reliability calculation
perform no network I/O and require no hosted service. They do not automatically
capture prompts, responses, tool arguments/results, exception messages,
tracebacks, PII, credentials, or arbitrary payloads.

Structural metadata includes agent/run identity, bounded indicator and
evaluator identifiers, outcomes, timestamps, lifecycle state, reason codes,
and exception class names. A custom diagnostic handler deliberately receives
the original exception and is a trusted boundary. See
[SECURITY_MODEL.md](SECURITY_MODEL.md).

## Internal and experimental inventory

`agent_reliability.application`, private names, underscore-prefixed evaluator
validation, SDK session implementation, and concrete OTel scope implementation
are internal. Direct imports are unsupported.

`agent_reliability.experimental` exports nothing in 1.0. No experimental
Python functionality is invented for GA.


# Evaluator Framework (M4)

Status: accepted M4 design; implementation follows ADR-0007.

## Purpose and boundary

M4 makes an evaluation an attributable measurement without becoming an
evaluation platform. An evaluator answers one narrow question about a typed
input. It does not require an active agent run, retain that input, manage a
dataset, call an LLM, or know about a hosted backend.

The architecture separates four concepts:

```text
typed input
    |
SyncEvaluator[T] / AsyncEvaluator[T]
    |
EvaluationDecision                 (outcome + optional reason code)
    |
EvaluatorRunner + injected Clock   (safe execution + attribution time)
    |
EvaluationResult                   (decision + immutable provenance)
    |
RunHandle.record_evaluation(...)   (optional run association)
```

An evaluator returns a decision rather than constructing historical
provenance itself. The runner owns the observation time and binds the
evaluator's declared identity and determinism to the result. This prevents
every custom evaluator from reimplementing timestamp/provenance assembly and
keeps direct evaluator execution independently useful.

## Public values

`EvaluatorIdentity` contains:

- `name`: 1-64 lowercase ASCII letters/digits with internal hyphens; begins
  and ends alphanumeric.
- `version`: opaque 1-128 character machine identifier. It is never parsed or
  ordered as SemVer.
- `configuration_id`: optional caller-supplied, non-sensitive, stable machine
  identifier, also bounded to 128 characters.

Changing code, policy, threshold, or other configuration that can materially
change judgments requires changing `version` or `configuration_id`. The
library never hashes configuration: hashing arbitrary configuration could
retain or leak secrets and cannot determine semantic significance.

`EvaluationDecision` contains an `EvaluationOutcome` and optional bounded
`reason_code`. It is an evaluator's immediate, non-historical answer.

`EvaluationResult` contains that outcome and reason code plus
`EvaluationProvenance`. It deliberately contains no score, confidence,
free-form message, evidence dictionary, input, output, callable, or exception.

## Protocols and typing

`SyncEvaluator[InputT]` and `AsyncEvaluator[InputT]` are separate structural
protocols. Both expose immutable-by-contract `identity` and `deterministic`
properties. Sync evaluation returns `EvaluationDecision`; async evaluation is
an `async def` returning the same type.

There is no union of `EvaluationDecision | Awaitable[EvaluationDecision]`, no
coroutine detection, and no `asyncio.run()` inside the library. A custom
evaluator needs no base class or registry.

## Safe and raw execution

Calling `evaluator.evaluate(value)` directly is raw execution. Its exception
propagates normally, which is useful in tests and when evaluator failure is a
programming error the caller wants to handle.

`EvaluatorRunner.evaluate(...)` and `.evaluate_async(...)` are the optional
failure-isolated paths. They catch `Exception`, never `BaseException`, report
the original exception through the existing sanitized SDK diagnostic channel,
and return `EvaluationExecutionFailure`. They never manufacture `FAIL` or
`UNKNOWN`.

An execution failure stores only evaluator identity when available, failure
stage, and exception class name. The raw exception exists only ephemerally in
the trusted in-process diagnostic handler. Generic timeouts are deferred.

## Built-ins

M4 includes two small deterministic building blocks:

- `EqualityEvaluator[T]`: `actual == expected` is `PASS`, otherwise `FAIL`.
- `PredicateEvaluator[T]`: a typed callable returning `True`, `False`, or
  `None` maps to `PASS`, `FAIL`, or `UNKNOWN` respectively. The caller declares
  whether that callable is deterministic.

Both require an explicit `EvaluatorIdentity`. Python class names and package
versions are never substituted for behavioral identity. The predicate itself
is trusted application code and is not serialized, registered, or sandboxed.

## Run integration and manual compatibility

Evaluators remain independent of run execution:

```python
result = runner.evaluate(evaluator, value)
if isinstance(result, EvaluationResult):
    run.record_evaluation(indicator="task_success", result=result)
```

`indicator` answers what reliability property was measured. Evaluator
identity answers how it was judged. They are never combined.

Existing `run.record(indicator=..., outcome=...)` remains the low-level manual
assertion API. Its event has no provenance. A manual assertion is not assigned
a fake evaluator identity.

## Concurrency and performance

The framework owns no registry or shared mutable state. Independent evaluator
and runner calls may execute concurrently. Evaluator authors remain
responsible for the thread/task safety of state inside their own evaluator or
predicate. The framework never deep-copies, renders, or serializes evaluation
input.

## M5 consumption

M5 binds a completed result to its separate indicator as a
`ReliabilityObservation`, then validates evaluator identity, configuration,
and determinism before aggregation. It never aggregates
`EvaluationExecutionFailure` and never treats it as `UNKNOWN`. See
[LOCAL_RELIABILITY_ENGINE.md](LOCAL_RELIABILITY_ENGINE.md).

# ADR-0007: Evaluator architecture and provenance semantics

## Status

Accepted

## Context

M1 intentionally implemented only `EvaluationOutcome`; M2 allowed callers to
record those outcomes manually. Historical reliability cannot safely compare
agent versions until an evaluated outcome identifies which evaluator behavior
and configuration produced it. M4 must add that attribution without assuming
LLM judges, capturing sensitive input, coupling evaluation to an active run,
or making evaluator failure look like agent failure.

The existing M1 domain specification also listed evaluator failure among
possible reasons for `UNKNOWN`. That is too lossy for M4: a completed evaluator
may legitimately return `UNKNOWN` because evidence is insufficient, whereas an
evaluator exception means no judgment was produced.

## Decision

1. Add a cohesive `agent_reliability.evaluation` package above the domain.
   `EvaluationOutcome` remains in the unchanged domain kernel.
2. Define frozen, slotted `EvaluatorIdentity`, `EvaluationDecision`,
   `EvaluationProvenance`, `EvaluationResult`, and
   `EvaluationExecutionFailure` values. Results contain no generic metadata,
   evidence payload, score, confidence, human message, input, or exception.
3. Identity consists of a validated name, opaque version, and optional
   caller-supplied configuration identifier. Class names and package versions
   are never authoritative. The library does not hash configuration.
4. Define distinct generic `SyncEvaluator[T]` and `AsyncEvaluator[T]`
   structural protocols. Both return `EvaluationDecision`; there is no
   awaitable union or runtime coroutine detection.
5. The optional SDK-layer `EvaluatorRunner` executes evaluators, uses the
   existing injected `Clock` to attach completion time, and constructs
   provenance from the evaluator's declared identity/determinism.
6. Raw evaluator calls may raise. Safe runner calls catch `Exception` only,
   report through the existing `SdkDiagnostic` mechanism, and return a bounded
   `EvaluationExecutionFailure`. `BaseException` control signals propagate.
7. `UNKNOWN` means a completed judgment lacked enough evidence. Execution
   failure is never converted into `PASS`, `FAIL`, or `UNKNOWN`.
8. Extend `EvaluationRecorded` additively with optional provenance and reason
   code. Existing `RunHandle.record(...)` emits `provenance=None` and remains a
   manual assertion. New `record_evaluation(...)` records a completed result.
9. Include only equality and typed predicate evaluators. No global registry,
   plugin discovery, remote calls, timeout machinery, or LLM adapter is added.
10. Evaluation input is never retained, copied, rendered, placed in events, or
    supplied to diagnostics automatically.
11. Refine ADR-0001's statement that ports are expressed only in domain types:
    ports may also reference immutable, vendor-neutral evaluation contract
    values. They still may not depend on evaluator execution, SDK runtime, or
    concrete adapters. This permits `EvaluationRecorded` to carry typed
    provenance without flattening it into duplicate string fields or moving
    evaluator attribution into the M1 mathematical domain.

## Alternatives Considered

- **Evaluator directly returns `EvaluationResult`.** Rejected because every
  custom evaluator would need to reproduce clock injection and provenance
  assembly, and could accidentally mismatch its result identity.
- **One protocol returning a result or awaitable.** Rejected because typing,
  cancellation, and runtime behavior become ambiguous.
- **Async-only protocol.** Rejected because local deterministic evaluation is
  synchronous and forcing coroutines adds cost and ceremony without I/O.
- **Convert exceptions to `UNKNOWN`.** Rejected because this silently mixes an
  absent judgment with a completed inconclusive judgment.
- **Create a fake `manual` evaluator.** Rejected because manual assertion did
  not execute an evaluator and historical analysis must see that distinction.
- **Generic evidence/metadata dictionaries.** Rejected due to privacy,
  cardinality, serialization, and compatibility risk.
- **Generic score/confidence.** Rejected because scale, direction, calibration,
  and statistical meaning are not universal.
- **Automatic configuration hashing.** Rejected because raw configuration may
  contain secrets and hashing does not identify semantic relevance.
- **RunHandle executes evaluators.** Rejected because it hides latency/failure
  behavior, complicates async semantics, and prevents offline evaluation.

## Consequences

Evaluation has a stable, serializable-friendly attribution contract before M5
consumes observations. Evaluator execution and run association remain separate.
Custom evaluators require only structural compatibility, but their authors are
responsible for accurate identity/determinism declarations and internal
concurrency safety.

Changing `EvaluationRecorded` is intentional and pre-1.0. Existing keyword and
positional construction remains valid because new fields are optional and
appended. Consumers should begin treating absent provenance as manual.

## Security Impact

Positive: no input/output or arbitrary evidence is retained; identity fields
are bounded; default diagnostics expose only exception class and structural
operation data. A caller-supplied diagnostic handler still receives the raw
exception as an explicit trusted in-process boundary. User evaluator code and
predicate callables are trusted application code; M4 does not sandbox Python.

## Performance Impact

Local evaluation adds one evaluator call, validation of a small immutable
decision, one clock read, and construction of small frozen values. No copying,
serialization, reflection-heavy dispatch, registry lookup, thread, queue, or
I/O is introduced. Benchmarks record engineering baselines.

## Compatibility Impact

All new public symbols are pre-alpha and exported only from
`agent_reliability.evaluation` or `agent_reliability.sdk`. The package root
stays small. M1 APIs and mathematics do not change. `EvaluationRecorded` gains
two optional fields while preserving the four existing fields and manual
recording behavior.

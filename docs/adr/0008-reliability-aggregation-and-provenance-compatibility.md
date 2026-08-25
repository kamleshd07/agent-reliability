# ADR-0008: Reliability aggregation and provenance compatibility

## Status

Accepted

## Context

M1 provides exact ratio, SLO, error-budget, and burn-rate mathematics. M4
provides evaluator identity and immutable provenance. M5 must connect them
without treating equal categorical outcomes as proof that their measurement
methods are comparable. Indicator changes, evaluator changes, configuration
changes, manual/evaluated mixing, and contradictory determinism declarations
can all make an otherwise valid percentage methodologically false.

The analytical API is invoked explicitly, unlike M2 instrumentation. A valid
but incompatible dataset is an expected analytical condition, not necessarily
a caller programming error, and must never produce a partial report that a
consumer could accidentally use.

## Decision

1. Add a pure `agent_reliability.reliability` package. It has no clock,
   registry, persistence, network, telemetry, or framework dependency.
2. `ReliabilityObservation` binds the exact, case-sensitive indicator (what
   was measured), outcome, and optional M4 provenance (how it was measured).
   It adds no timestamp: M4's nested `evaluated_at` remains available on the
   input provenance but is ignored for compatibility and window selection. It
   carries no input, output, reason, evidence, or run identity.
3. `ReliabilityCohort` represents compatibility. A manual cohort has no
   evaluator identity and no determinism value. An evaluated cohort has the
   complete `EvaluatorIdentity` plus its determinism declaration. Evaluation
   completion time is deliberately excluded because observations in one
   cohort naturally complete at different instants.
4. Two non-empty observations are compatible exactly when their cohort values
   are equal: indicator, manual/evaluated source, evaluator name, evaluator
   version, configuration identity, and determinism must match. A determinism
   disagreement for otherwise equal identity is corrupt/inconsistent
   provenance and is rejected, not split into two trusted methodologies.
5. Empty input has no inferred cohort. It still produces an ordinary no-data
   report by delegating to M1 with zero counts.
6. Valid incompatible data returns an immutable `AggregationConflict` with
   typed reasons and no ratio, SLO result, budget, or burn rate. Invalid API
   arguments and malformed observation objects raise `TypeError` or
   `ValueError` at the boundary.
7. `evaluate_reliability` consumes each supplied iterable once, counts each
   item once, and delegates to M1's `compute_ratio`, `evaluate_slo`, and
   `compute_error_budget`. The caller must always supply `UnknownPolicy`.
8. Burn rate is optional and exists only when an explicit lookback iterable is
   supplied. The lookback is aggregated independently under the same indicator
   and UNKNOWN policy. A non-empty lookback must have the same cohort as the
   non-empty full window; otherwise no report is produced. M1's
   `compute_burn_rate` performs the only burn-rate mathematics.
9. Input order has no effect. Conflict discovery tracks only bounded flags and
   one structural cohort candidate; observations are not retained. Complexity
   is O(n) time and O(1) auxiliary memory for one full window, plus O(m) time
   for an optional lookback.
10. Input multiplicity is meaningful. Every supplied observation is counted;
    M5 invents neither observation identifiers nor deduplication semantics.

## Alternatives Considered

- **Aggregate by indicator alone.** Rejected: evaluator changes would silently
  rewrite the measurement methodology inside one reported number.
- **Partition and return multiple reports.** Rejected: M5 answers one
  reliability question. Callers may deliberately partition and invoke it
  separately; a group-by analytics surface is outside this milestone.
- **Raise an exception for provenance conflict.** Rejected for valid datasets:
  incompatibility is a typed analytical outcome. Construction and argument
  errors still raise normally.
- **Return a partial report plus warnings.** Rejected: downstream callers can
  ignore warnings and consume an invalid number. The boundary fails closed.
- **Use complete `EvaluationProvenance` as the cohort key.** Rejected because
  `evaluated_at` describes one observation, not its methodology.
- **Ignore determinism.** Rejected: conflicting declarations under the same
  evaluator identity indicate inconsistent provenance.
- **Manufacture a manual evaluator identity.** Rejected by ADR-0007 and because
  absence of evaluator provenance is meaningful.
- **A stateful engine class.** Rejected: the operation has no state or injected
  dependency. A function is the smaller and more honest abstraction.
- **Independent formulas or float arithmetic.** Rejected: M1 is the sole
  mathematical authority and uses exact `Fraction` values.

## Consequences

The public result is either complete and methodologically coherent or contains
no reliability mathematics. Reports compose M1 result types instead of copying
their fields. A full-window collection and lookback collection are selected by
the caller; M5 does not validate calendar containment or perform windowing.

M1's earlier decision not to add a single-field observation wrapper remains
correct for the math kernel. M5's observation adds two facts the kernel did not
need: indicator and methodology at the application aggregation boundary.

## Security Impact

Positive. Aggregation needs only bounded indicator identifiers, categorical
outcomes, and already-bounded M4 provenance. It never renders observations,
retains inputs, stores exception content, accepts arbitrary metadata, logs, or
performs I/O. A pathological iterable can still run forever or raise because
Python's general `Iterable` contract provides no safe way to prevent that;
timeouts and process isolation are caller concerns.

## Performance Impact

Each iterable is streamed once. Only integer counters, a cohort candidate, and
a bounded set of conflict flags are retained. M1 ratio construction adds exact
`Fraction` arithmetic after counting. M5 benchmarks record local results for
1,000 through 1,000,000 observations without establishing a marketing SLA.

## Compatibility Impact

All M5 symbols are new and pre-alpha, exported only from
`agent_reliability.reliability`. The package root and M1-M4 public contracts
are unchanged. M5 imports M1 and M4 immutable values; neither lower layer
depends on M5.

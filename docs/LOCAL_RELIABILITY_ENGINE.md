# Local Reliability Engine (M5)

Status: accepted M5 design; implementation follows ADR-0008.

## One reliability measurement

One measurement is one explicitly named indicator evaluated over one
methodologically compatible collection under one explicit `UnknownPolicy` and
one existing M1 `Slo`. M5 refuses to produce mathematics from incompatible
observations.

`ReliabilityObservation` contains only:

```text
indicator
outcome
provenance | None
```

`indicator` states what was measured. Provenance states how. Outcome is the
completed categorical judgment. M5 adds no observation-time field; the
`evaluated_at` already present inside M4 provenance is ignored for compatibility
and window selection. Run identity, reason code, input, output, and evidence
are unnecessary because callers select the window before invoking M5.

Each supplied observation is counted exactly once. Duplicate detection is not
attempted; input multiplicity is meaningful.

## Indicator identity

Indicators are 1-128 printable ASCII characters with no whitespace. Equality
is exact and case-sensitive; no normalization occurs. Therefore
`task_success`, `Task_Success`, and `task-success` are three distinct valid
identifiers. This remains an open local naming space, not a global taxonomy.

## Cohort and provenance compatibility

An immutable `ReliabilityCohort` contains the indicator plus either:

- manual source: `evaluator_identity=None`, `deterministic=None`; or
- evaluated source: the complete M4 `EvaluatorIdentity` and a boolean
  determinism declaration.

Two observations are compatible only if these cohort values are exactly equal.
That compares evaluator name, opaque version, optional configuration identity,
and determinism. `evaluated_at` is excluded: it varies per observation and is
not methodology identity.

Manual observations for the same indicator aggregate. Manual and evaluated
observations never mix. Distinct evaluator names, versions, configurations, or
determinism declarations never mix. M5 supplies no override.

## Conflicts and invalid input

Valid incompatible data returns `AggregationConflict`, carrying typed reasons
and no report fields. No partial ratio or warning-bearing report exists.
Malformed direct arguments and non-observation iterable members raise
`TypeError` or `ValueError` as programmer errors. An
`EvaluationExecutionFailure` is not a `ReliabilityObservation` and cannot enter
counts.

## UNKNOWN and empty data

The caller must pass one M1 policy; there is no default:

| Policy | UNKNOWN in denominator | UNKNOWN treated as good |
|---|---:|---:|
| `EXCLUDE` | no | no |
| `TREAT_AS_BAD` | yes | no |
| `TREAT_AS_GOOD` | yes | yes |

M5 streams outcomes to M1 `compute_ratio()` unchanged. An empty collection is
not equivalent to an UNKNOWN observation: it produces zero raw and considered
counts, undefined ratios, `SloStatus.UNKNOWN`, and `BudgetStatus.NO_DATA`.

## SLO, error budget, and burn rate

M5 accepts the existing M1 `Slo`, including both `AT_LEAST` and `AT_MOST`.
It calls `evaluate_slo()` and `compute_error_budget()` directly and exposes
their immutable values in the report.

Burn rate is calculated only when `burn_rate_lookback` is explicitly supplied.
M5 does no window selection: the caller supplies both the full-window
observations and the already-selected lookback. The lookback uses the same
indicator and UNKNOWN policy and, when non-empty, must match the full-window
cohort. M5 then calls M1 `compute_burn_rate()` on the lookback ratio. An empty
lookback truthfully produces `BudgetStatus.NO_DATA`; a non-empty lookback
cannot be paired with an empty full window because comparability cannot be
established.

All numerical values remain M1 `Fraction` values or explicit typed no-data/
zero-tolerance states. M5 adds no float arithmetic or formatting.

## Report and execution properties

`ReliabilityReport` contains:

```text
indicator
cohort | None
ratio                 M1 RatioResult
slo_evaluation        M1 SloEvaluation
error_budget          M1 ErrorBudget
burn_rate | None      M1 BurnRate
```

The report is frozen. Given the same observations, SLO, and policy, it is
identical regardless of observation order. Iterables are consumed once. The
engine is O(n) time and O(1) auxiliary memory, plus O(m) time for an explicit
lookback. There is no clock, randomness, logging, registry, or ambient state.

## Privacy and trust

The engine and report never request, inspect, render, log, copy, or retain prompts,
responses, tool arguments, model output, evaluation input, exception content,
reason text, evidence, or arbitrary metadata. Evaluator provenance is an
attribution claim, not cryptographic proof. M5 validates internal consistency;
it cannot prove that an evaluator declared its identity or determinism
truthfully.

## Worked examples

### 1. Clean cohort

`990 PASS, 10 FAIL, 0 UNKNOWN`, `AT_LEAST 99%` gives ratio `99/100`, exact
boundary status `MET`, and measured budget consumption `1`.

### 2. UNKNOWN excluded

`90 PASS, 5 FAIL, 5 UNKNOWN` with `EXCLUDE` considers 95 observations and
produces pass ratio `18/19`; the five UNKNOWN observations remain visible in
the raw counts.

### 3. UNKNOWN treated as bad

The same observations with `TREAT_AS_BAD` consider all 100 and produce pass
ratio `9/10`; observed bad events are 10.

### 4. No data

An empty iterable produces `pass_ratio=None`, `fail_ratio=None`, SLO status
`UNKNOWN`, and error-budget status `NO_DATA`. It produces neither 0% nor 100%.

### 5. Evaluator-version conflict

`task_success` observations from `exact-task-check` versions `v1` and `v2`
return an `AggregationConflict`; no combined number exists.

### 6. Manual/evaluated conflict

Manual `task_success` observations mixed with attributed evaluator results
return an `AggregationConflict`; no synthetic manual identity is introduced.

### 7. Zero tolerance

For `AT_LEAST 100%`, a non-empty all-PASS cohort has
`ZERO_TOLERANCE_INTACT`, consumption `0`, remaining `1`. One FAIL produces
`ZERO_TOLERANCE_EXCEEDED` and no finite consumption ratio.

### 8. Explicit burn-rate lookback

A full-window `task_success` cohort under `AT_LEAST 99%` may supply a lookback
with `97 PASS, 3 FAIL`. M1 computes the lookback bad fraction `3/100` divided
by allowance `1/100`, giving burn rate `3`. A different evaluator version in
that lookback returns a conflict instead.

## Explicit non-goals

M5 does not provide window selection, rolling aggregation, streaming, mutable
accumulators, multi-indicator or multi-cohort reports, storage, serialization,
file readers, CLI output, OTel mapping, evaluation coverage, evaluator health,
remote analytics, agent identity selection, or commercial-platform behavior.

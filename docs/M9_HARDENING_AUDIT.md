# M9 measurement-health hardening audit

Status: internal release-contract audit against the installed PyPI `1.1.0`
artifact on 2026-08-29. This document records the baseline before M9 test and
example changes; it does not define a new public contract.

## Installed baseline

The wheel installed into a clean environment as version `1.1.0`, declared no
base runtime dependency, exposed the optional `otel` extra unchanged, and
successfully imported the base SDK, measurement namespace, and OTel bridge.

| Public surface | Installed 1.1.0 contract | Stability |
|---|---|---|
| `agent_reliability.measurement.__all__` | `MeasurementHealth`, `MeasurementHealthReason`, `MeasurementHealthReport`, `MeasurementPolicy` | stable |
| `MeasurementHealth` | `HEALTHY=healthy`, `DEGRADED=degraded`, `UNAVAILABLE=unavailable` | stable enum |
| `MeasurementHealthReason` | eight members from `RUN_INITIALIZATION_FAILURE` through `INCOMPATIBLE_EVIDENCE` | stable enum |
| `MeasurementHealthReport` | `(health=HEALTHY, reasons=frozenset())` | stable immutable value |
| `MeasurementHealthReport.from_reasons` | `(reasons: frozenset[MeasurementHealthReason])` | stable canonical constructor |
| `MeasurementHealthReport.combine` | `(self, *others: MeasurementHealthReport)` | stable monotonic composition |
| `MeasurementPolicy.evaluate` | `(self, *, measurement_health: MeasurementHealthReport) -> T` | stable application boundary |
| `RunHandle.measurement_health` | read-only property | stable SDK-derived snapshot |
| `RunHandle.record_evaluation_failure` | keyword-only `failure: EvaluationExecutionFailure` | stable explicit association |
| `RunHandle.evaluate_measurement_policy` | `(policy: MeasurementPolicy[T]) -> T` | stable explicit invocation |
| `ReliabilityReport.measurement_health` | constructor field with healthy factory default | stable orthogonal report field |
| `AggregationConflict.measurement_health` | read-only unavailable property | stable conflict signal |

## Invariants preserved by M9

1. Task reliability and measurement health are independent.
2. `UNKNOWN` means a completed indeterminate evaluation, never execution,
   telemetry, provenance, or exporter failure.
3. `EvaluationExecutionFailure` is not PASS, FAIL, UNKNOWN, or a health value.
4. Health composition remains commutative, associative, idempotent, and
   monotonically non-improving through bounded reason-set union.
5. Health is run-local. Parent, child, sibling, task, and thread state do not
   propagate implicitly.
6. Diagnostic and optional OTel bridge failures do not affect local health.
7. Policy results, action criticality, and authorization remain
   application-owned. Policy exceptions propagate.
8. Freely constructed reports are data values, not attestations. A live
   `RunHandle` snapshot is SDK-derived and cannot be overwritten by a caller.
9. Health retains bounded structural reasons, never exception objects,
   tracebacks, application payloads, or arbitrary history.
10. SLO, error-budget, burn-rate, UNKNOWN, and no-data mathematics remain
    unchanged.

## Executable failure-matrix contract

| Scenario | Body | Evaluation/observation | Health | Diagnostics/events |
|---|---|---|---|---|
| healthy | executes | produced/recorded | healthy | normal lifecycle |
| evaluator UNKNOWN | executes | UNKNOWN produced/recorded | healthy | normal |
| evaluator throws | executes | failure/no observation | unavailable when associated | sanitized evaluator diagnostic |
| sink throws | executes | result may exist; delivery absent | degraded | sink diagnostic; failed events absent |
| start clock or run ID fails | executes degraded | no run observation | unavailable | one initialization diagnostic; no events |
| record/end clock fails | executes | expected event absent | degraded | clock diagnostic |
| diagnostic handler throws | executes | underlying behavior unchanged | no additional impact | last-resort drop; no recursion |
| bridge start/finish fails | executes | local evidence unchanged | unchanged | bridge diagnostic; local events continue |
| manual provenance absent | executes | valid manual cohort | healthy | normal |
| provenance mismatch | n/a | no report; typed conflict | unavailable | no partial number |
| nested/concurrent child failure | executes | run-local | child only | no cross-contamination |
| combined failures | executes | depends on evaluation path | deterministic reason union | each independent attempt follows 1.1.0 isolation |

M9 implements this table in contract, unit, property, security, integration,
and example tests. No production symbol or behavior is added.

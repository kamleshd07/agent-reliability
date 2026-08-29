# Final 1.0 public API review

Date: 2026-08-25. This independent M7 review supersedes the M6 recommendation.
The normative inventory and semantics are in [GA_CONTRACT.md](GA_CONTRACT.md).

## Result

| Namespace | Classification | Decision |
|---|---|---|
| `agent_reliability` | FREEZE | `__version__` only |
| `agent_reliability.domain` | FREEZE | All 18 package exports |
| `agent_reliability.sdk` | FREEZE | All 7 package exports |
| `agent_reliability.evaluation` | FREEZE | All 10 package exports |
| `agent_reliability.reliability` | FREEZE | All 6 package exports |
| `agent_reliability.ports` | FREEZE | All 10 package exports; Protocol evolution is compatibility-sensitive |
| `agent_reliability.adapters` | FREEZE | All 5 concrete adapters |
| `agent_reliability.adapters.otel` | FREEZE API / EXTERNAL-EVOLVING MAPPING | Bridge constructor/lifecycle stable; exact OTel mapping separately governed |

No symbol is classified `INTERNALIZE BEFORE 1.0` or `CHANGE BEFORE 1.0`.
Internal submodules remain unsupported even where they define a module-local
`__all__`. The empty `experimental` package exports no API.

## Signature and construction review

Parameter names, positional/keyword-only behavior, defaults, return unions,
sync/async behavior, context manager behavior, and Protocol structure were
inspected. Existing keyword-only boundaries on SDK/aggregation entry points
are appropriate. Existing positional construction of public frozen values and
evaluators is already valid and remains supported.

Frozen dataclasses intentionally expose structural equality and their existing
field order. Adding required fields or changing equality is breaking. Protocol
members cannot be added casually because structural implementations would
break. Enum member names and values are frozen; additions require explicit
compatibility review because exhaustive downstream matching exists.

## Naming review

`EvaluationDecision`, `EvaluationResult`, and `EvaluationExecutionFailure`
encode real distinctions and should not be shortened. `ReliabilityCohort` and
structured conflicts make measurement compatibility inspectable. `Slo`
follows Python class casing. No rename, root flattening, renderer, CLI,
serialization contract, or extra conversion helper is justified for GA.

## M7 hardening changes

- Package metadata now derives its version from `agent_reliability.__version__`
  instead of duplicating the literal in `pyproject.toml`.
- `SdkDiagnostic.exception` is excluded from generated `repr` while remaining
  available to the explicitly trusted custom-handler boundary.

Neither change alters a public callable signature or reliability semantic.

## M8 additive measurement-health API

| Symbol | Module | Purpose and stability rationale |
|---|---|---|
| `MeasurementHealth` | `agent_reliability.measurement` | Stable evidence trust/completeness states; avoids string branching. |
| `MeasurementHealthReason` | `agent_reliability.measurement` | Bounded privacy-safe structural causes. |
| `MeasurementHealthReport` | `agent_reliability.measurement` | Immutable scoped snapshot and composition value. |
| `MeasurementPolicy[T]` | `agent_reliability.measurement` | Generic application boundary; result semantics remain application-owned. |
| `RunHandle.measurement_health` | `agent_reliability.sdk` | SDK-derived run-local snapshot. |
| `RunHandle.record_evaluation_failure` | `agent_reliability.sdk` | Associates a no-result attempt without inventing UNKNOWN. |
| `RunHandle.evaluate_measurement_policy` | `agent_reliability.sdk` | Explicit policy invocation; exceptions propagate. |
| `ReliabilityReport.measurement_health` | `agent_reliability.reliability` | Orthogonal report visibility; healthy default preserves construction. |
| `AggregationConflict.measurement_health` | `agent_reliability.reliability` | Marks incompatible evidence unavailable without weakening conflict. |

The enum members are also stable: `HEALTHY`, `DEGRADED`, `UNAVAILABLE`, and
the eight bounded `MeasurementHealthReason` members documented by ADR-0009.
`MeasurementHealthReport.health`/`.reasons`, its canonical `from_reasons()`
constructor, and monotonic `combine()` method are public value operations.
`MeasurementPolicy.evaluate()` is the single protocol member and returns its
application-chosen generic result type.

No helper, accumulator, severity map, or mutable state is public. Frozen 1.0
namespace `__all__` sets and function signatures are untouched.

## M9 hardening review

M9 adds **no public symbols** and changes no production module. The exact
installed 1.1 exports, enum values, constructors, methods, properties, and
high-value signatures are protected by `tests/compat/test_public_api_1_1.py`.
Policy decisions in `examples/` remain application-local demonstration types.

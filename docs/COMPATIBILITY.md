# Compatibility

Agent Reliability `1.0.0` is released. The normative 1.0 contract is
[GA_CONTRACT.md](GA_CONTRACT.md) and the release policy is
[VERSIONING.md](VERSIONING.md).

## 1.x promise

Package-level exports documented as stable, their typing, signatures, value
semantics, and reliability behavior follow SemVer starting at `1.0.0`.
Compatibility includes UNKNOWN interpretation, exact SLO boundaries, no-data
behavior, error-budget/burn-rate formulas, provenance compatibility,
evaluator failure classification, and instrumentation failure isolation.
Pre-1.0 versions (`0.1.0.dev0`, `1.0.0rc1`) carried no compatibility
guarantee.

Internal names have no compatibility guarantee. Experimental names, if ever
introduced, must be explicitly labeled. The OTel adapter API is stable while
its identified external semantic mapping is external-evolving.

## Python

The supported and CI-tested matrix is Python 3.11, 3.12, and 3.13. See
[VERSIONING.md](VERSIONING.md) for removal policy.

## Telemetry

Telemetry compatibility is tracked separately because a mapping can break a
consumer without changing Python imports. See [TELEMETRY_SPEC.md](TELEMETRY_SPEC.md)
and [OTEL_MAPPING.md](OTEL_MAPPING.md).

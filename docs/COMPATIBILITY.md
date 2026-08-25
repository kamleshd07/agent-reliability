# Compatibility

The current development version is `0.1.0.dev0`; it is being prepared for the
first 1.0 release. The normative 1.0 contract is [GA_CONTRACT.md](GA_CONTRACT.md)
and the release policy is [VERSIONING.md](VERSIONING.md).

## Pre-GA

Core semantics are substantially complete, but no 1.0 artifact has been
published. Until the release tag, public APIs may receive a documented change
only when the GA audit identifies a material correctness, safety, or long-term
compatibility problem.

## 1.x promise

At 1.0, package-level exports documented as stable, their typing, signatures,
value semantics, and reliability behavior follow SemVer. Compatibility
includes UNKNOWN interpretation, exact SLO boundaries, no-data behavior,
error-budget/burn-rate formulas, provenance compatibility, evaluator failure
classification, and instrumentation failure isolation.

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

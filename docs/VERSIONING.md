# Versioning and compatibility

Agent Reliability follows Semantic Versioning for its stable public contracts.
The normative contract inventory is [GA_CONTRACT.md](GA_CONTRACT.md).

## Release numbers

- **Patch (`1.x.Y`)**: bug, security, diagnostic, documentation, and internal
  performance fixes that preserve stable APIs and semantics.
- **Minor (`1.X.0`)**: backward-compatible functionality, optional
  integrations, or carefully reviewed new public APIs. Existing stable API,
  runtime behavior, and typing remain valid.
- **Major (`X.0.0`)**: may make intentional breaking changes with release
  notes and migration guidance.

Documentation-only corrections may ship in any release. A security release is
not exempt from compatibility analysis; if an emergency security correction
must break a contract, it is explicitly disclosed with mitigation/migration
guidance.

## What counts as breaking

Compatibility includes:

- package namespaces, exports, callable signatures, defaults, and exceptions;
- enum names/values and public value-object fields/equality;
- Protocol requirements and supported sync/async context behavior;
- valid downstream typed code because the package ships `py.typed`;
- outcome, UNKNOWN, SLO boundary, no-data, exact-arithmetic, error-budget,
  burn-rate, provenance, and failure-isolation semantics;
- documented telemetry and privacy behavior according to its stability class.

A source-compatible signature change can still be semantically breaking.
Fixing behavior that contradicts a normative contract is a bug fix; the
release notes must identify any observable correction.

## Deprecation policy

Stable API deprecations are announced in a minor release through the
changelog, API documentation, and migration instructions. When runtime
warnings are useful, use `DeprecationWarning`; library consumers and test
suites can opt into displaying it. No warning is added merely to demonstrate
the policy.

The deprecated API remains functional for the rest of the current major
series unless retaining it creates an exceptional security or correctness
risk. Normal removal occurs only in the next major release. Type declarations
must remain usable throughout the support window.

Experimental APIs, if introduced later, require an explicit experimental
namespace/label and may evolve in a minor release with prominent notes. This
does not weaken stable contracts.

## Supported Python and dependencies

The 1.0 support matrix is Python 3.11, 3.12, and 3.13. Dropping a supported
minor Python version during 1.x is breaking unless that Python version has
reached upstream end-of-life and the change is announced in advance.

Base runtime dependencies remain empty. Optional dependency bounds may widen
compatibly after testing. A lower-bound increase that invalidates a currently
supported environment requires compatibility and security justification.

## OpenTelemetry evolution

The OTel adapter's Python API and host-ownership behavior are stable. Exact
alignment with external semantic conventions is external-evolving and follows
[OTEL_MAPPING.md](OTEL_MAPPING.md). Mapping changes require release notes,
tests, compatibility analysis, and a project mapping schema-version change
when a project-owned field changes incompatibly.


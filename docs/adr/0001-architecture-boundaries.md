# ADR-0001: Core architecture and dependency boundaries

## Status

Accepted

## Context

This project's core value is a set of reliability semantics (SLOs,
error budgets, burn rates, reliability indicators) that must remain
correct, deterministic, and trustworthy regardless of which LLM
provider, agent framework, or telemetry backend a user has chosen. If
vendor- or framework-specific concerns are allowed to leak into the
reliability math, three things go wrong over time: (1) the math becomes
implicitly coupled to one vendor's behavior, (2) supporting a second
vendor or framework requires touching domain code instead of adding an
adapter, and (3) a domain-layer bug becomes indistinguishable from a
vendor SDK bug during debugging.

We also need the domain kernel (M1) to be usable, and testable, with
zero network access, zero database, and zero LLM calls — both for
correctness confidence (deterministic, property-testable math) and so
the project is genuinely useful standalone, per
[VISION.md](../VISION.md)'s requirement that the OSS SDK not depend on
a hosted backend.

## Decision

Adopt a hexagonal (ports-and-adapters) layering:

```text
User API → Application → Domain
                ↑            
              Ports ← Adapters
```

with these rules, enforced by code review until tooling can enforce
them automatically:

- `domain` imports nothing else in this project and no vendor SDK,
  telemetry library, or agent framework. It may use the Python standard
  library and (if ever justified) small, general-purpose, dependency-
  free libraries.
- `application` imports `domain` and `ports` (interfaces) only — never
  a concrete adapter.
- `ports` defines typed interfaces (initially: exporter, clock,
  evaluator, storage) in terms of domain types only.
- `adapters` implements `ports` and is the only layer permitted to
  import a specific vendor SDK, transport library, or agent framework.
- `experimental` is a separate namespace for anything not yet subject
  to the compatibility guarantees in
  [COMPATIBILITY.md](../COMPATIBILITY.md).

See [ARCHITECTURE.md](../ARCHITECTURE.md) for the full diagram and
current (M0) implementation state.

## Alternatives Considered

- **Flat module layout** (`agent_reliability/runs.py`,
  `agent_reliability/slos.py`, ... with no layer boundary). Rejected:
  nothing would structurally prevent a vendor import from ending up
  inside SLO math; the vendor-neutrality principle would depend
  entirely on reviewer vigilance forever, with no architectural signal
  in the diff.
- **Framework-first design** (build directly against one agent
  framework's execution model, generalize later). Rejected outright by
  the project's stated anti-goals and vendor-neutrality principle — see
  [ENGINEERING_PRINCIPLES.md](../ENGINEERING_PRINCIPLES.md) #3, #9.
- **Split into multiple packages immediately** (`agent-reliability-core`,
  `agent-reliability-otel`, ... from day one). Rejected for M0: no
  adapter exists yet to justify a package boundary, and multiple
  packages before there is working code multiplies release/versioning
  overhead for no present benefit. A single package with internal layer
  boundaries can be split later without changing the domain model,
  precisely because the boundaries described here already exist inside
  it.

## Consequences

- Adding support for a new telemetry backend, evaluator type, or agent
  framework should only ever require a new adapter, never a change to
  `domain`.
- A missing capability (e.g. "we need a new port method") will
  sometimes require touching `ports`, `application`, and an `adapter`
  together — an accepted three-file cost in exchange for the boundary
  guarantee.
- This ADR does not decide the *contents* of `ports` (exact method
  signatures for the evaluator/exporter/clock protocols) — those remain
  open per [ARCHITECTURE.md](../ARCHITECTURE.md)'s list of deferred
  decisions.

## Security Impact

Concentrating all external I/O in `adapters` narrows the surface that
needs security review for injection, deserialization, and credential-
handling risk (see [SECURITY_MODEL.md](../SECURITY_MODEL.md)) to one
layer, rather than that risk being diffusely possible anywhere in the
codebase.

## Performance Impact

None measurable yet — no runtime code exists. The layering itself adds
at most one indirection (calling through a port interface) per
operation, which is expected to be negligible relative to any real I/O
an adapter performs; this will be confirmed with benchmarks once M2
introduces runtime instrumentation.

## Compatibility Impact

None yet — no public API exists beyond `__version__`. This ADR
constrains *where future public API can live* (the User API layer,
thin and re-exported from the package root) rather than defining any
API surface itself.

# Architecture Decision Records

This directory records significant, hard-to-reverse architectural
decisions and the reasoning behind them, so that future contributors
understand *why*, not just *what*.

## When to write an ADR

Write one for a decision that is expensive to reverse or that
future contributors will otherwise have to re-derive from scratch —
for example: choosing a distributed-architecture component (see
[ENGINEERING_PRINCIPLES.md](../ENGINEERING_PRINCIPLES.md) #15),
committing to an OpenTelemetry integration strategy, freezing a
telemetry schema versioning mechanism, or defining run-lifecycle or
SLO-calculation semantics that other code will depend on.

Do not write one for a reversible implementation detail (e.g. choice of
build backend, internal module layout within a single package) — record
those briefly in the relevant doc instead (see
[ARCHITECTURE.md](../ARCHITECTURE.md), "Deviations" section, for an
example of that lighter-weight treatment).

## Format

Each ADR is a numbered file, `NNNN-short-title.md`, and contains:

```text
Status            (Proposed | Accepted | Superseded by ADR-NNNN | Rejected)
Context
Decision
Alternatives Considered
Consequences
Security Impact
Performance Impact
Compatibility Impact
```

## Process

1. Copy the format above into a new numbered file.
2. Open it for review alongside the code/doc change it justifies, if
   any.
3. Once accepted, ADRs are not edited to reflect new decisions — a
   changed decision gets a new ADR that supersedes the old one, so the
   historical record of *why* the original choice was made stays
   intact.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-architecture-boundaries.md) | Core architecture and dependency boundaries | Accepted |
| [0002](0002-reliability-mathematics-and-undefined-data-semantics.md) | Reliability mathematics and undefined-data semantics | Accepted |

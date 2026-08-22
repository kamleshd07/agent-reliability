# Contributing

Thank you for your interest. This project is pre-alpha and its domain
model and semantics ([docs/DOMAIN_MODEL.md](docs/DOMAIN_MODEL.md),
[docs/SLO_SEMANTICS.md](docs/SLO_SEMANTICS.md)) are still being
validated — questions and critique on those documents are as valuable
as code right now.

## Branch naming

`<type>/<short-description>`, e.g. `feat/slo-window-boundaries`,
`fix/burn-rate-division-by-zero`, `docs/clarify-unknown-policy`.

## Commit expectations

Commits should be small enough to review in isolation and should not
mix unrelated concerns (e.g. a domain-semantics change and a formatting
pass belong in separate commits).

## Before opening a PR

Run locally:

```bash
ruff check .
ruff format --check .
mypy src
pytest
python -m build
```

All must pass. CI re-runs the same checks (see
[.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Testing requirements

New behavior needs tests in the correct category — see
[docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md) for the
unit/property/contract/integration distinction. Reliability mathematics
changes require property-based tests demonstrating the relevant
invariants, not just example-based tests.

## ADR requirements

If your change makes a hard-to-reverse architectural decision (see
[docs/adr/README.md](docs/adr/README.md) for the bar), include an ADR in
the same PR. Don't retrofit an ADR to justify a decision already made
elsewhere — write it before or alongside the implementation.

## Breaking-change policy

During pre-alpha, any public API or telemetry contract may change; see
[docs/COMPATIBILITY.md](docs/COMPATIBILITY.md). Once the project reaches
a stable release, breaking changes require a major version bump, a
documented migration path, and a deprecation window for anything they
replace.

## Documentation requirements

If a PR changes semantics described in `docs/`, update the relevant
document in the same PR. Code and docs must not describe different
behavior.

## What a PR description should answer

- What changed?
- Why?
- What alternatives were considered?
- What are the compatibility implications?
- What are the security implications?
- What are the performance implications?
- How was this verified?

## Scope discipline

This project has explicit anti-goals (see
[docs/ROADMAP.md](docs/ROADMAP.md) and the vision document's framing in
[docs/VISION.md](docs/VISION.md)). PRs that expand scope toward a
generic tracing platform, an agent framework, a prompt-management tool,
or similar adjacent products will be redirected, not merged.

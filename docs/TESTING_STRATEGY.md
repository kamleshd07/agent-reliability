# Testing Strategy

Testing is an architectural requirement, not an afterthought bolted onto
finished code — this is why test categories and their directories exist
before there is business logic to fill them.

## Categories

### Unit tests (`tests/unit/`)

Pure behavior of a single unit, no I/O. At M0, this contains only a
package smoke test (`test_package.py`): import succeeds, version is
correct, public API surface is exactly what's documented. Once the
domain kernel (M1) exists, this category will hold the bulk of tests for
`domain` and `application` logic.

### Property-based tests (`tests/property/`)

Reserved for [Hypothesis](https://hypothesis.readthedocs.io/)-driven
tests, especially for SLO mathematics, error-budget calculations,
boundary values, time-window behavior, and percentage invariants.
Example invariants to enforce once M1 lands (see
[SLO_SEMANTICS.md](SLO_SEMANTICS.md)):

```text
0 <= SLI <= 1
error_budget_remaining_fraction is never NaN
identical input always produces identical output
result does not depend on irrelevant input ordering
```

Empty at M0 — there is no math to property-test yet.

### Contract tests (`tests/contract/`)

Reserved for verifying that a concrete implementation of a port
(exporter, evaluator, future storage adapter) actually satisfies that
port's documented contract, run against every implementation of a given
port with the same test suite. Empty at M0 — no ports have
implementations yet.

### Integration tests (`tests/integration/`)

Reserved for tests that exercise a real external boundary (a real OTLP
endpoint, a real database). A test that merely exercises multiple
in-process modules together is a unit test, not an integration test —
this distinction is enforced by category, not by vibes. Empty at M0 —
there is no external boundary yet.

## What M0 actually verifies

At M0, the only claims under test are: the package imports, is
versioned correctly, and its public surface is exactly
`{__version__}`. This is deliberately small and is the correct amount of
testing for a milestone that contains zero business logic.

## Coverage policy

A sensible initial coverage floor is enforced via `pytest --cov` in CI
once there is enough code for a floor to be meaningful (see
`.github/workflows/ci.yml`, currently running the suite without a hard
coverage gate at M0). High coverage is a signal, not a goal — 100%
coverage will not be chased mechanically. The domain kernel's reliability
mathematics (M1) is the one area expected to approach exhaustive
behavioral coverage, because it is the part of the system whose
correctness the entire project's credibility rests on.

## Determinism requirement

Per [ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md) #2, tests for
the domain kernel must never depend on wall-clock time, network access,
or non-deterministic ordering. A `Clock` port (see
[ARCHITECTURE.md](ARCHITECTURE.md)) is the anticipated mechanism for
making time an explicit, injectable, test-controllable dependency rather
than an ambient call to `datetime.now()` scattered through domain code —
finalized when the domain kernel is implemented.

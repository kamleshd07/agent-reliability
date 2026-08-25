# Testing Strategy

Testing is an architectural requirement, not an afterthought bolted onto
finished code — this is why test categories and their directories exist
before there is business logic to fill them.

## Categories

### Unit tests (`tests/unit/`)

Pure behavior of a single unit, no I/O for `domain/`; the M2 SDK's own
runtime logic (`tests/unit/sdk/`) is also "unit" in this project's sense
even though it exercises `contextvars`/`asyncio` — no *external* I/O
(network, disk, real sinks) is involved, only in-process, injected test
fakes (see "Test fakes" below). `tests/unit/adapters/` covers the
concrete `Clock`/`RunIdGenerator`/`EventSink` implementations shipped
in M2.

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

M1 landed these as `tests/property/test_sli_properties.py` and
`test_error_budget_properties.py`; M2 added
`test_sdk_properties.py` for nesting-depth, run-id-uniqueness, and
event-ordering invariants at the SDK layer.

### Contract tests (`tests/contract/`)

Reserved for verifying that a concrete implementation of a port
(exporter, evaluator, future storage adapter) actually satisfies that
port's documented contract, run against every implementation of a given
port with the same test suite. Still empty at M2: `EventSink`,
`Clock`, and `RunIdGenerator` each currently have exactly one shipped
implementation (plus test fakes), so there was no meaningful shared contract
suite at M2. M3 starts contract testing with the paired context-lifecycle port;
the OpenTelemetry adapter is intentionally not an `EventSink`.

### Integration tests (`tests/integration/`)

Reserved for tests that exercise a real external boundary (a real OTLP
endpoint, a real database). A test that merely exercises multiple
in-process modules together is a unit test, not an integration test —
this distinction is enforced by category, not by vibes. Still empty at
M2 — the SDK's default components are all in-process by design (see
[SDK_DESIGN.md](SDK_DESIGN.md)); there is no external boundary yet.

## Benchmarks (`benchmarks/`)

Introduced at M2 (`bench_sdk.py`) — the first milestone with a real
runtime instrumentation path to measure. Uses only `time.perf_counter`
and the standard library, per
[ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md) #10 (no
heavyweight benchmarking dependency). Numbers are recorded as local
engineering baselines in the M2 milestone report, not published as
marketing claims — see [ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md)
#6.

M4 adds `bench_evaluation.py` for raw equality evaluation, immutable result/
provenance creation, and `record_evaluation` on an active run. It performs no
input copying or serialization and reports local medians only.

M5 adds `bench_reliability.py` for 1,000, 10,000, 100,000, and 1,000,000
observation collections. Wall time is measured without allocation tracing;
transient engine allocation is measured separately with `tracemalloc` so the
memory instrument does not distort the reported timing sample.

## What M0/M1/M2/M2.1 actually verify

M0: the package imports, is versioned correctly, and its public surface
is exactly `{__version__}`. M1: the reliability domain kernel's
mathematics, exhaustively (100% coverage on every implemented module).
M2: the SDK's context/lifecycle/failure-isolation behavior — normal
completion, exception preservation, nested and concurrent runs, thread
propagation limits, and every documented suppressed-vs-raised failure
boundary — also at 100% coverage on every implemented M2 module (see
the M2 milestone report for exact numbers). M2.1 adds focused regression
coverage for sync/async degraded entry, exact application-exception
preservation, parent-context stability, diagnostic privacy and handler
failure, explicit unbounded in-memory retention, all composite child
failure positions, and `BaseException` control signals.

## M3 integration and contract coverage

M3 begins meaningful contract coverage with the paired `RunContextBridge`
lifecycle, ordering, degradation, and failure-isolation contract. Integration
tests use a real OpenTelemetry SDK, explicit per-test providers, and an
in-memory exporter: no collector, network, or global-provider mutation.

The suite verifies exact existing-parent and ordinary-child relationships,
nested agents, mixed standard/agent nesting, sync restoration, async task
isolation, privacy, degraded runs, provider ownership, and injected OTel
creation, activation, cleanup, and ending failures. `benchmarks/bench_otel.py`
compares the M2.1 no-bridge, API-only non-recording, and SDK in-memory paths.

## M4 evaluator coverage

M4 unit tests cover bounded evaluator identity, immutable decisions/results/
provenance/failures, exact equality and predicate behavior, structural custom
evaluators, injected UTC time, manual-versus-evaluated event contracts, and
degraded-run association. Property tests exercise evaluator name grammar and
equality behavior over generated values.

Failure tests prove raw evaluator calls raise while the optional runner returns
a distinct execution failure; `Exception` is isolated, `BaseException` and
async cancellation propagate, clock failure produces no result, and a broken
diagnostic handler cannot break the host. Privacy tests use sensitive inputs
and exception messages and assert their absence from results, events, and
default logs. Concurrent async execution verifies the framework owns no shared
per-evaluation state. M4 adds no external integration boundary; the existing
M3 OTel contract/integration suite remains the regression gate.

## M5 reliability-engine coverage

M5 unit and property tests verify observation/cohort construction, all
provenance conflict dimensions, manual isolation, UNKNOWN policy behavior,
empty versus UNKNOWN data, both SLO directions, exact boundaries,
zero-tolerance states, explicit lookback compatibility, immutable reports,
single-pass generators, order independence, partition counts, and direct
equality with M1 results. A focused contract regression ensures every report
component equals the corresponding public M1 computation.

## M6 example, wheel, and downstream-typing coverage

M6 adds `tests/contract/test_examples.py`, which subprocess-executes the four
`examples/` scripts and the exact fenced block extracted from `README.md`
between the `readme-quickstart-start`/`-end` markers, asserting each one's
stdout verbatim. This makes the README's advertised program executable
documentation: it cannot silently drift from what a new adopter actually runs.

`scripts/verify_release_artifacts.py` is a separate, non-pytest smoke test that
builds no code itself but exercises the *installed artifact* rather than the
source tree: it creates isolated venvs, installs the built wheel with
`--no-deps`, confirms `py.typed` ships and the base install stays
OpenTelemetry-free, runs the basic/async/conflict examples from the installed
package, type-checks `tests/typing/installed_consumer.py` with
`tests/typing/mypy.ini` against that same installed wheel (this is what
proves the public API is usable, and not just importable, by a strict-mypy
downstream consumer — `pyproject.toml`'s own `[tool.mypy]` section points
`mypy_path` at `src/` and so cannot substitute for this), and, unless
`--skip-otel` is passed, repeats the OTel example in a second venv with the
`[otel]` extra installed. The `.github/workflows/ci.yml` artifact job
builds the wheel and runs this script on every push, so this whole path is a
CI gate, not a one-time manual check.

## Coverage policy

A sensible initial coverage floor is enforced via `pytest --cov` in CI
once there is enough code for a floor to be meaningful (see
`.github/workflows/ci.yml`, currently running the suite without a hard
coverage gate at M0). High coverage is a signal, not a goal — 100%
coverage will not be chased mechanically. The domain kernel's reliability
mathematics (M1) is the one area expected to approach exhaustive
behavioral coverage, because it is the part of the system whose
correctness the entire project's credibility rests on.

## Test fakes (`tests/fakes/`)

M2 introduced the first ports with real runtime behavior to fake:
`Clock`, `RunIdGenerator`, `EventSink`, `DiagnosticHandler`. Reusable
fakes (`FakeClock`, `SequentialRunIdGenerator`, `RecordingSink`,
`BrokenSink`, `BrokenClock`, `BrokenRunIdGenerator`,
`CollectingDiagnosticHandler`, `BrokenDiagnosticHandler`, and variants)
live in `tests/fakes/`, not scattered inline across test modules —
per the M2 brief's explicit instruction, and because several of these
"broken" fakes are deliberately reused across many failure-isolation
tests. `tests/fakes/` is not part of the published package.

## Concurrency and async testing (M2/M2.1)

`asyncio_mode = "auto"` (pyproject `[tool.pytest.ini_options]`) lets
`async def test_...` functions run without a per-test marker.
Concurrency correctness (nested runs, 150+ concurrent `asyncio.Task`s,
cross-task isolation, cancellation classification) is tested with real
`asyncio.gather`/`asyncio.create_task`, never by sleeping to "probably"
observe a race — see `tests/unit/sdk/test_lifecycle_async.py`. Threads
are tested to prove both the documented non-propagation limitation and
the documented `contextvars.copy_context()` workaround actually work —
see `tests/unit/sdk/test_threading.py` and
[SDK_DESIGN.md](SDK_DESIGN.md).

## Determinism requirement

Per [ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md) #2, tests
must never depend on wall-clock time, network access, or
non-deterministic ordering. The domain kernel (M1) never reads the
clock or generates ids itself, by construction. `agent_reliability.ports.Clock`
and `RunIdGenerator` (finalized at M2 — see
[ADR-0003](adr/0003-python-sdk-runtime-and-context-architecture.md))
are the mechanism that makes time and id generation explicit, injectable,
test-controllable dependencies at the SDK layer, via `FakeClock` and
`SequentialRunIdGenerator` in `tests/fakes/`, rather than an ambient
`datetime.now()`/`uuid.uuid4()` call scattered through runtime code.

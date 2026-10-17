# P29 pilot runbook (SDK side) and pilot gates

Status: **SDK-side local artifacts only.** No pilot was run. No platform, shared TEST or production environment was contacted. The P28 exporter used here is the
uncommitted working-tree version; its D-1 fix (TLS-verification failure classification) is present in that working tree (P28 reports: "D-1 FIXED AND VERIFIED" / "VERIFIED", quoted in `docs/P29_IMPLEMENTATION_LOG.md`) but **nothing is committed or released**. Nothing here is independently verified.
This runbook is the S11 deliverable that the SDK repository can own (P29-S11-AC07); the platform half (PL1 guide, integrated PC-1 + PC-2 tree, machine credential) is outside it.

## 1. Prerequisites

| Path | Needs | State |
|---|---|---|
| Local demo (this repository) | Python 3.11+, `pip install -e ".[http]"` (the demo uses the exporter with a mocked transport), no model, no network | RUN locally (author-run, see `docs/P29_TEST_EVIDENCE.md`) |
| Primary pilot | integrated platform tree (PC-1 + PC-2 + migration 0019, branch `integration/p28-pc1-pc2`), OIDC mode with a real machine credential, an SDK exporter with D-1 fixed in the real source, authorization to commit/merge for any claim beyond local | **NOT AVAILABLE / NOT RUN** |
| Degraded fallback | JSON-lines capture and replay to a *local* platform | capture RUN; replay to a platform NOT RUN (only a loopback stub in tests) |
| Last resort | local platform in dev-header mode (disables machine dispatch): no authentication claim, not shared TEST | NOT RUN |

## 2. Commands and expected output (local demo)

```sh
python examples/judge_fake_provider.py                         # PASS, FAIL, UNKNOWN, one execution failure, coverage
python examples/judge_pilot_demo.py --out capture.jsonl        # two-question scenario plus a stopped provider
python examples/judge_pilot_replay.py capture.jsonl            # dry run: validates 15 envelopes, sends nothing
```

Expected from the pilot demo: Q1 and Q2 runs `healthy`, Q3 run `unavailable`; for `answer-correctness` and `groundedness` Q1 `pass`, Q2 `fail`; Q3 two
`JudgeProviderUnavailableError` execution failures; a coverage line per indicator reading `reliability 0.500 over 2 determinate of 3 attempted (determinate 66.7%, execution failures 33.3%, ...)`.
`replay ... --post ENDPOINT --token-file FILE` exists for a platform you operate and is never run by the repository's checks against anything but a loopback stub.

## 3. Semantic limits the pilot report must carry (architecture section 15.1)

* **Survivorship.** Execution failures and UNKNOWN leave the reliability denominator: 99 failed attempts plus 1 PASS reads as reliability 1.0. Read the failure rate and the UNKNOWN rate beside reliability
  (`coordinator.coverage()` prints them together; the demo shows 33.3% failures beside 0.500).
* **UNKNOWN coverage.** A high UNKNOWN rate does not change reliability, policy or gate.
* **Gate reach.** `on_no_data` fires only when a burn-rate window has no determinate evidence. A partial outage is not covered. Set `on_no_data` deliberately (BLOCK where an outage must stop deployment).
* **Run-level health.** Any failure sets run health `UNAVAILABLE`; health is not indicator-scoped on the platform, so every indicator in that scope and window shows an unavailable `measurement_state` (P29-D09, P29-D13).
* A judge PASS is not correctness, safety or business completion (docs/EVALUATE.md, Meaning of PASS per dimension); the reference rubrics are uncalibrated; no accuracy figure exists.

* **Sink behavior (gate).** Sinks and diagnostic handlers run inside the scope's recording gate and must be non-blocking and must not call the scope; "recorded" means handed to the run handle (a sink that raises is isolated by the handle, so also watch the exporter's delivery snapshot next to `coverage()`).
* **Sync providers.** A sync judge's timeout is best effort; the provider's own client timeout is the real bound (or wrap it in `ExecutorSyncProvider`).

## 4. Measurement-health safeguards SG-1 to SG-6 (condition of the P29-D09 approval)

Status words: IMPLEMENTED-in-SDK = SDK code, tests and documentation exist (author-run); PROCESS-GATE = a human/operational step that code cannot satisfy; NOT SATISFIED = the pilot condition is not met today.

| ID | SDK support | Pilot condition | Status |
|---|---|---|---|
| SG-1 generous budgets and limits | IMPLEMENTED-in-SDK: `JudgeLimits`, `JudgeBudget`/`BudgetTracker`, `max_pending`, `max_concurrency`, safe defaults and guidance (docs/EVALUATE.md); budget exhaustion and overload are failures visible in observer reports, coverage and failure evidence (`test_phase4_measurement_integrity.py`) | pilot budgets sized so R13/R14 do not occur; any occurrence reported as an incident | **NOT SATISFIED** (no pilot configured; PROCESS-GATE) |
| SG-2 runbook note | documented in docs/EVALUATE.md and section 3 of this runbook | the pilot report restates it | PROCESS-GATE; **NOT SATISFIED** until a pilot report exists |
| SG-3 failure and UNKNOWN rate beside reliability | IMPLEMENTED-in-SDK: `CoverageReport`/`IndicatorCoverage.describe()` (no single "healthy" value) | the same figures from platform P3 reads in the pilot report and any dashboard | local part satisfied; platform part **NOT SATISFIED** (no platform run) |
| SG-4 deterministic-indicator isolation | SDK supports a separate scope and run for judge evaluation (tested: a failure in one run leaves another run `healthy`); documented | the pilot evaluates whether judge evaluation can be bound to a separate scope | PROCESS-GATE; **NOT SATISFIED** |
| SG-5 observer counters wired to alerting | IMPLEMENTED-in-SDK: `JudgeObserver`, `coverage()` counters (failures by class, shed, skipped, observer errors) | the application wires them to its own alerting | SDK part satisfied; wiring is customer **PROCESS-GATE**, **NOT SATISFIED** for the pilot |
| SG-6 deliberate `on_no_data` | documented (docs/EVALUATE.md, section 3) | the pilot gate sets it explicitly and states partial outage is not covered | PROCESS-GATE; **NOT SATISFIED** (platform configuration) |

Consequence: P29-D09's approval **does not yet cover pilot use** (owner record section 4): no SG condition is fully satisfied for a pilot.

## 5. Fallback order (plan section 5)

1. Primary: integration worktree, OIDC mode, real machine credential, exporter with D-1 fixed in the real source. **Not available as a whole**: D-1 is fixed in the uncommitted working tree, but the integrated platform tree, a real machine credential and commit/merge authorization are missing.
2. Degraded: capture and replay (this runbook, section 2). Proves P29 semantics only, not P28 authentication or delivery.
3. Last resort: dev-header local platform. Disables machine dispatch; no authentication claim; never shared TEST.

## 6. What this runbook does not claim

No platform read (P3, P4, P6, P7) was exercised; S11-AC02, AC03, AC05, AC06 (platform tables) and AC10 are NOT_EXERCISED, AC04 is exercised only on the SDK side (failure evidence and run health, not platform counts).
Nothing is committed, merged or released.

<!-- Saved verbatim by the coordinator from the fresh independent reviewer's hand-back (2026-10-16). Not edited by the author or the coordinator. -->
# P29 SDK V1 independent review

Reviewer: fresh read-only reviewer. I wrote nothing earlier.
Workspace: <workspace>/agent-reliability-p29
Date: 2026-10-16

## Verdict: APPROVE_WITH_REQUIRED_CORRECTIONS

There is no BLOCKER and no HIGH finding. Core logic held up under static review, fuzzing, concurrency stress and mutation testing. The required corrections are one coordinator lifecycle bug, documentation gaps that the plan's own criteria demand, one flaky test, a test-coverage gap in the concurrency code, and one example-code credential issue. They are listed in section 12.

Every PASS in the author's matrix remains author-run. This review does not turn them into verified or released claims. The pilot gates SG-1..SG-6 are correctly marked NOT SATISFIED.

## 0. What I executed and what I only read

**Executed.**
- ruff check, ruff format --check, mypy src and the full pytest suite on 3.11, 3.12 and 3.13.
- 6 parallel full-suite runs on 3.13 and 5 parallel stress repeats on 3.11 and 3.13.
- Fuzzing of the identity grammars against the real SDK, exporter and platform regexes.
- Privacy-leak probes, timeout probes, cancellation and concurrency stress probes, and a parser edge-case probe.
- 44 mutation tests.
- Wheel and sdist build, wheel inspection and the wheel half of `scripts/verify_release_artifacts.py`.
- A fresh-process import check plus a static AST scan.
- The demo run against a v1.2.1 source tree.
- A local redirect experiment on the example provider.
- Baseline manifest and drift checks.

**Only read.**
- The design documents.
- The ADR and the user docs.
- Most of the S06 to S11 test bodies.
- The calibration harness, partially.

**Not run (no network, or paid or out of scope).**
- The platform cross-repository test (S09-AC03). It needs a scratch venv with platform dependencies from the package index.
- The sdist-install step of `verify_release_artifacts.py`.
- The OTel and typing steps of `verify_release_artifacts.py`, which I skipped with `--skip-otel --skip-typing`.
- Any real model, platform, benchmark or load test.

All writes went to scratch under the session scratchpad. The workspace was read only. No commits were made.

## 1. Baseline, original-tree protection and drift

**Manifest check** (read-only `shasum -c docs/P29_WORKSPACE_BASELINE.sha256`).
- Exactly 8 files differ from the baseline. All are documented P29 edits: README.md, docs/EVALUATE.md, GA_CONTRACT.md, ROADMAP.md, VERSIONING.md, ADR-0007 Status paragraph, adr/README.md, and scripts/verify_release_artifacts.py.
- No `src/` file outside `experimental/judge/` differs, and `pyproject.toml` is identical. That is every file under `src/` and `pyproject.toml` in the manifest.
- All 11 hash-pinned files in baseline section 1.2 match: `sdk/context.py`, `evaluator_runner.py`, the `evaluation/*` files, `ports/event_sink.py` and the three compat tests.

**Original tree.** `git status --porcelain` of <workspace>/agent-reliability shows no P29 file. It shows only the P28 overlay set plus the D1 files.

**Drift claim verified by timestamps.**

| File in the original tree | Modified | Workspace baseline doc |
|---|---|---|
| docs/HTTP_EXPORTER.md | 15:50 | 13:02 |
| tests/unit/test_http_exporter_tls_real.py | 16:04 | 13:02 |
| docs/P28_SDK_D1_INDEPENDENT_REVIEW.md | 15:49 | 13:02 |
| docs/P28_SDK_D1_REMEDIATION_REPORT.md | 16:11 | 13:02 |

- The workspace copies of the first two differ from the original, as the author said.
- The author did not re-sync the baseline, and the evidence doc discloses this.
- Merging onto a D-1-fixed exporter needs a re-run of the evidence. I classify this as EXTERNAL VERIFICATION.

## 2. Gate results (executed)

| Python | ruff check | ruff format --check | mypy src | pytest |
|---|---|---|---|---|
| 3.11 | pass | 237 files formatted | 65 files, no issues | 1522 passed, 1 skipped |
| 3.12 | pass | 237 files | 65 files, no issues | 1522 passed, 1 skipped (clean re-run); 1 failure in a parallel run, see F-5 |
| 3.13 | pass | 237 files | 65 files, no issues | 1522 passed, 1 skipped (and 6 parallel runs) |

- The one skip is the platform check, which is NOT_EXERCISED without its two environment variables.
- Counts match the author's pytest figures (1522 passed plus 1 skipped).
- The author's "235 files formatted" is stale. The real count is 237 (LOW, doc staleness).
- The implementation log says 214 and 1322 tests, which are older figures.

## 3. Scope conformance and the acceptance matrix (item 1)

**What I inspected.**
- Stages S00 to S12 map to code and tests.
- S07 and S08 are optional in the plan and were implemented. Both stay inside the experimental namespace, so I do not count them as scope creep.
- No registry or entry points exist, and no wire member was added.
- I sampled well over 25 criteria and read in full the tests for all S03, S05 and S09 criteria.

**Checks that stood up.**
- S03-AC01..AC08 are real, not vacuous.
- The mutation results below tie the S03 retry, backoff, budget, timeout and leak tests to behaviour. Each of those mutants was killed.
- S05-AC01..AC09 are mostly real.
- S09 conformance is genuine, with these limits:
  - Mocked transport only.
  - The platform model check was not re-run by me.
  - The matrix states this correctly.

**Vacuous or overstated PASS claims found.**
- **S05-AC09(e).** The plan says "the docs state that customer sinks and diagnostic handlers run inside the gate and must be non-blocking". The statement exists only in the `coordinator.py` module docstring. It is not in README, EVALUATE.md, ADR-0010 or the runbook; I grepped them. The matrix still says PASS with "Outstanding: -". See F-3.
- **`test_p29_s05_ac09_c_nothing_reaches_the_handle_after_drain`.** It only checks that a closed scope raises `RuntimeError`. Real late-completion discard is covered elsewhere, in `test_s05_coordinator` AC05 sync late completion, and that test kills mutant M15. The AC09(c) name is cosmetic.

**Honest NOT_EXERCISED, BLOCKED and PARTIAL rows.** The matrix is honest on S11-AC02, AC03, AC05 and AC10, S12-AC01, AC02 and AC05, and the platform halves of S11-AC01, AC04 and AC06.

## 4. API compatibility and packaging (items 2, 12)

- The existing compat snapshots (1.0, 1.1, 1.2) pass.
- `dependencies = []` is unchanged.
- `agent_reliability/experimental/__init__.py` is untouched, so the sub-package does not leak into the experimental root.
- Fresh-process check with `python -I`:
  - Importing the whole judge namespace, including `executor`, `calibration`, `testing` and `structured`, loads no non-stdlib module outside `agent_reliability`.
  - `socket`, `ssl` and `urllib.parse` appear only transitively through `asyncio`.
- Static AST scan: no third-party imports, no `eval`, `exec` or `open`, no `os.environ` or `getenv` use, and no logging import.
- Wheel and sdist built offline from a scratch copy, using a copied uv cache.
  - The wheel contains the 19 judge modules, the 5 rubric JSONs and the 2 schema JSONs.
  - `py.typed` is present.
  - `verify_release_artifacts.py` passed "artifact metadata and contents: ok", "installed metadata/import probe: ok" and "base wheel and offline examples: ok".
  - The sdist-install step failed only because there is no network for hatchling. See the external item in section 13.
- Recorder capability detection against SDK 1.2.1:
  - I extracted `v1.2.1` with `git archive` into scratch and overlaid the judge package.
  - The v1.2.1 `RunHandle.record_evaluation_failure(*, failure)` has no `indicator` parameter.
  - Running `examples/judge_fake_provider.py` against that tree worked.
  - Results recorded, the failure went to local health only, run health was `unavailable`, and coverage printed "failure evidence not delivered 1".
  - Mutant M20 (always pass `indicator=`) is killed by the suite.

## 5. Security and privacy (item 3)

**Leak probe (executed).**
- Planted a secret in the request text and in the provider reply, and had a provider raise a `ValueError` and then a `Boom` exception echoing the prompt.
- Ran sync and async judges through the coordinator with an observer, a diagnostic handler, a sink, `logging` at DEBUG, coverage, `repr` and `traceback.format_exception` over the full cause and context chain.
- 6 of 6 scenarios were clean.
- `retain_cause=False` is the default.
- `__context__` is empty because the failures are raised outside any `except` block.
- Mutant M10 (chain the cause) is killed.

**Prompt injection.**
- The nonce is 16 hex characters and is redrawn per attempt until absent from every part text. Mutant M02 is killed.
- The system message holds no content.
- Role and trust come from enums, and trust promotion is rejected. Mutants N12 and N13 are killed.

**Structured-output strictness (parser probe, executed).** The parser rejects:
- duplicate members, NaN, depth 9, and a 5000-digit integer,
- booleans or floats used as citation indexes, duplicate citation indexes,
- case variants such as `HIGH` or `Pass`, and a code taken from another verdict's list.

It accepts a lone-surrogate escape in `reason` and a newline in `reason`, both as the contract allows.

**Provider isolation.** Provider exceptions are reduced to fresh constant-message classes. Non-Judge exceptions become `JudgeProviderError`. A `ProviderReply` that is not a `ProviderReply` becomes `JudgeProviderError`.

**Example adapters.** See F-4. Credentials are not read from the environment.

## 6. Outcome correctness (item 4)

- The ten failure classes match contract section 7 exactly, in order.
- Mutant M01 (turn a failure into UNKNOWN) is killed.
- Mutant M04 (UNKNOWN to PASS) is killed.
- Mutant N14 (UNKNOWN ignores its mapping) is killed.
- The confidence threshold is strict `<`. Mutant M07 is killed.
- Mutants M11 (repeats disagreement), M12 (pre-check) and M13 (input limit) are killed.
- Mutants N15, N16 and N17 are killed.
- `aggregate_repeats` precedence is PASS-and-FAIL, then the first UNKNOWN, then the first decision. This matches CON-07 and is a documented interpretation.
- The pre-check makes no provider call.
- Cancellation, shed and skip never produce an outcome.

## 7. Identity (item 5, executed)

- 300,000 random strings were fuzzed over `[aZ09._-+:/ \n]`. Everything the P29 grammar accepts is also accepted by all three of these:
  - the SDK's `EvaluatorIdentity` validation,
  - the exporter `_OPAQUE` pattern in `adapters/_http_delivery.py`,
  - the platform `_OPAQUE_ID_PATTERN` in `evidence_schemas.py`, read-only and replicated.
- Bad-input results:
  - `+`, `:` and `/` are rejected.
  - A trailing newline is rejected.
  - Leading or trailing `.`, `_` or `-` is rejected.
  - 129 characters is rejected; 128 is accepted.
- The composed `configuration_id` is 86 characters at a 64-character label. A 65-character label is rejected.
- Mutant M08 (allow `+`) is killed.

## 8. Concurrency and recording (item 6)

**Stress and flakiness.**
- The recording-gate, coordinator and sync/async suites (122 tests) were repeated 5 times in parallel on both 3.11 and 3.13. All passed.
- The full suite was run 6 times in parallel on 3.13. All passed.
- One flaky test was found, F-5.

**My own cancellation-race stress.**
- 450 runs, each with 40 evaluations at concurrency 3 and random cancels while queued and running.
- The invariants held in every run:
  - Admission `_running` returned to 0.
  - No waiters were left.
  - The number of events recorded equalled the number of dispositions.
  - Coverage attempted equalled dispositions.
  - No leaked tasks.
- The implementation is correct here. The suite does not prove it, see F-6.

**Sink exception.** A sink that raises inside the gate is isolated by `RunHandle`. The coordinator reports `RECORDED_RESULT` while the event was dropped. See F-9. An observer that raises is suppressed and counted.

**Re-entrancy.** F-3 (deadlock).

**Unreproduced theoretical race.** Between `_complete` releasing the gate and popping the in-flight entry, a concurrent drain could in principle record a `JudgeTimeoutError` failure after the result was already recorded. I tried 300 trials with a slow sink and a tiny drain timeout and saw 0 double records. The window is not closable by the tests. I classify it as LOW and unproven.

**Mutation of the gate.**
- M03 (remove the gate lock) is killed by the 8-thread test.
- P01 (drain recording unguarded) survived.
- See F-6.

## 9. Budget, retry, timeout and shutdown (item 7, executed)

- **Async.** A hanging provider with 0.1 s per attempt, a 0.5 s deadline and 3 attempts failed with `JudgeTimeoutError` after 0.38 s, with 3 attempts counted.
- **Sync, plain `SyncLLMJudge`.**
  - A provider sleeping 1.0 s against a 0.1 s timeout returned `JudgeTimeoutError` only after 1.0 s. The timeout is post-hoc and not enforced. See F-2.
  - A provider that never returns would hang the caller forever.
- **`ExecutorSyncProvider`.**
  - The same slow provider timed out in 0.27 s.
  - Helper threads are daemon threads, bounded by `max_threads`, and drained to 0 after the late result.
  - At the thread bound the call fails fast with `JudgeProviderUnavailableError`.
- **Budget.**
  - The check happens before every attempt, retries included.
  - Mutants M05 (drop the check), M24 (off by one), N20 (never record usage) and M23 (retry-after ignored) are killed.
  - The late-reply tokens of a discarded sync reply are not counted. See F-11.
- **Backoff.** Mutants M14 (jitter times 2) and N08 (cap ignored) are killed.
- **Retry and repair counts.** Mutants N06 and N07 are killed.
- **Provider timeout.** Mutant M06 (ignore the timeout) is "killed" only by a hang. See F-12.

## 10. Measurement integrity and SG-1..SG-6 (item 9)

- The docs and runbook honestly mark every pilot gate NOT SATISFIED. SG-1, SG-3 and SG-5 are implemented SDK-side. SG-2, SG-4 and SG-6 are process gates.
- `coverage().describe()` always prints reliability beside determinate coverage, failure rate and UNKNOWN rate.
- No `healthy`, `ok`, `score` or `verdict` member exists. Mutant M19 (reliability over attempts) is killed.
- Cross-indicator health limitation: documented in EVALUATE.md and the runbook, and tested with a failure in one run leaving a separate run healthy.
- No accuracy or calibration claim anywhere. I grepped README, EVALUATE.md, ADR-0010, the judge package, the examples, the runbook and the rubrics. Only "uncalibrated", "no accuracy claim" and similar negations appear. The five reference rubrics say "UNCALIBRATED ... no accuracy claim".
- `calibration.py` is local only and writes nothing. Its report carries case ids, not content. The metrics and the `accuracy_on_answered` field are labelled and never framed as a product claim.
- Weak points:
  - `determinate_rate` excludes cancelled, late-discarded and skipped evaluations from its denominator. They are printed beside it, so this is not misleading.
  - Dropped sink events still count as recorded (F-9).

## 11. Docs and ADR-0010 (item 11)

- The ADR stays inside the V1 scope.
  - It is experimental, provider-neutral and stdlib-only, with its own timeout machinery.
  - `EvaluatorRunner` is unchanged.
  - There is no registry or entry points, and no new wire member.
  - It leaves ADR-0007 decisions 1 to 8, 10 and 11 unchanged.
- Status and provenance wording is honest:
  - "Accepted ... owner-approved on 2026-10-16 by explicit owner instruction", unsigned, "approver identity and time not recorded".
  - The number is provisional.
  - The ADR-0007 body is untouched, with only a Status paragraph pointer.
  - The wording does not invent an approver or a time.
- The ADR does not name the coordinator, the calibration harness, the executor or the structured-output evaluator. They fit "provider-neutral adapter" and "timeout machinery" under items 2 and 3. I read this as acceptable. The coordinator and calibration pieces are not mentioned at all.
- Doc gaps are in F-2 and F-3. The EVALUATE.md quick start was not executed.
- The ADR's claim of owner G-C approval cannot be verified by a reviewer. It needs owner confirmation (section 13).

## 12. Findings

### MEDIUM

**F-1. `EvaluationScope.submit()` called outside a running loop leaves a ghost evaluation.**
- File: `coordinator.py:619-635`.
- Cause: `_prepare` registers the in-flight entry and the `_seen` indicator before `asyncio.get_running_loop()` raises `RuntimeError`.
- Repro (executed, `atk/submit.py`): call `submit` from a plain thread, outside any loop, while the scope is open.
- Expected: raise with no state change.
- Actual:
  - The scope exit blocked for the full `drain_timeout_seconds` (2.0 s in my run; the default is 60 s).
  - It then recorded a spurious `JudgeTimeoutError` failure for an evaluation that never ran.
  - Coverage showed 1 execution failure with no provider call, and run health went `UNAVAILABLE`.
- Remediation: resolve the loop before `_prepare`, or unregister the entry and the indicator on failure. Add a regression test.

**F-2. The sync timeout is not enforced without the optional executor, and user docs do not say so.**
- File: `sync.py` `_call`.
- Behaviour: a blocking provider is never interrupted. The deadline is only checked after the provider returns. A provider that never returns hangs `evaluate_sync` forever, and the scope drain in the same thread cannot help.
- Documentation: the `SyncLLMJudge` and `executor.py` docstrings say this. EVALUATE.md and the README say nothing, and do not mention `ExecutorSyncProvider`. ADR-0010 item 3 says the judge "may enforce a per-attempt timeout".
- Remediation: document in EVALUATE.md that sync timeouts are best effort and show `ExecutorSyncProvider` as the enforcement option. State that the provider's own socket timeout is the real bound.

**F-3. Recording-gate constraints are not in the user docs, and re-entrancy deadlocks silently.**
- (a) Required by plan S05-AC09(e): the docs must say sinks and diagnostic handlers run inside the gate and must be non-blocking. They do not. The matrix PASS is overstated.
- (b) Executed (`atk/a1.py`): a sink `emit` that calls `scope.evaluate_sync(...)` on the same scope deadlocks. `_prepare` takes the non-reentrant `threading.Lock` while the same thread already holds it. The thread was still alive after 8 s.
- Remediation:
  - Add a documentation paragraph in EVALUATE.md and the ADR consequences.
  - Optionally record the gate-holder thread and raise `RuntimeError` on re-entry instead of hanging.
  - Correct the matrix note for S05-AC09.

**F-4. Example `default_post_json` forwards credentials on cross-host redirects.**
- File: `examples/judge_providers.py` (`default_post_json`, `urllib.request.urlopen` with the default redirect handler).
- Repro (executed, `atk/redir.py`): a loopback server answering `302` to a second loopback server. The second server received `x-api-key: KEY123`.
- The default handler also allows redirect to a plain `http` target.
- The response body is read unbounded, which is a memory risk. `_check_url` validates only the initial URL.
- Remediation: install a redirect handler that refuses redirects, or strips auth headers, and cap the response size. Example code only, but the plan advertises "secrets handling in example adapters".

**F-5. A flaky test under load: `test_p29_s11_demo_runs_locally_and_captures_the_two_question_scenario`.**
- File: `tests/unit/experimental_judge/test_s11_pilot_artifacts.py:46`.
- Repro (executed): 8 of 64 runs failed with 8 parallel loops, and one 3.12 full-suite run in parallel failed once.
- Cause: it asserts the list order of captured envelopes, which come from the exporter's delivery worker. The failing assertions compare `['pass','fail']` against `['fail','pass']`, and a per-run health order.
- Remediation: compare per-run sorted or keyed data, or order by `producer_run_id`.
- It can also fail CI under load, so it should be fixed before merge.

**F-6. The test suite misses concurrency-code mutants I confirmed behaviourally.**
- P01 (drain recording without the gate) survives all 700 judge tests.
- P02 (cancel while queued leaks a granted slot) survives. My own cancel stress shows `_running=1` leak.
- P03 (no abandon on cancel while queued) survives, and my stress hangs.
- P04 (FIFO bypass in admission) survives.
- The shipped suite only has `test_p29_s05_ac05_*`, which does not cover queued-cancel.
- Remediation: add a stress test that cancels queued and granted waiters and asserts admission returns to idle. Add a drain-time recording overlap test using the `OverlapHandle`.

### LOW

**F-7. Stricter-than-contract salt grammar.**
- `SamplingPolicy.salt` requires alphanumeric first and last characters (`values.py` `_SALT_PATTERN`). The contract says `[A-Za-z0-9._-]` for 0 to 64 characters.
- The salt never reaches identity, so the stricter rule has no visible justification.
- It rejects salts like `_pilot` or `x-`.
- Judgement: acceptable, but record it. Either relax it or leave a note.

**F-8. Boundary survivor on C1 controls.**
- Mutant N05 survives: `127 <= ord(c) <= 159` in `core.py:291` changed to 158 still passes every test.
- U+009F in `reason` is therefore untested. Add the vector.
- Mutant N10 (sampling `<=`) is an equivalent mutant (probability 2^-64).

**F-9. Dropped sink events still count as recorded.**
- Executed (`atk/sinkexc.py`): a sink that raises in `emit` is isolated by `RunHandle`. The coordinator returned `RECORDED_RESULT`, and coverage counted the evaluation as determinate.
- This follows ADR-0004 and cannot be detected by the coordinator.
- The docs should say "recorded" means "handed to the handle".

**F-10. Sync waiter leaks a slot on `BaseException` while queued.**
- `waiter.event.wait()` at `coordinator.py:888` has no timeout and no abandon.
- A `KeyboardInterrupt` in a queued sync caller leaves a dead waiter in the queue. When it is granted, the slot never returns, so `_running` stays inflated.
- Read only, not executed.

**F-11. Late-discarded sync replies are not counted in the token budget.**
- Tokens consumed by a reply that arrives after the deadline are never recorded, so budgets undercount (`_engine.py` `_account` runs only for `Replied`, and `sync.py` converts an overrun into `Raised(TimeoutError)`).
- It is within the documented overshoot.

**F-12. A hang kills mutant M06, not an assertion.**
- Without `asyncio.timeout` the suite hangs instead of failing, which would turn a regression into a CI timeout.
- Add a bounded guard to the test.

**F-13. Smaller items.**
- A custom `jitter` returning a negative value gives a `ValueError` from `time.sleep`. It reaches the wire as `exception_type` `ValueError`, not one of the ten literals. Programmer error only.
- `judge_abstained` is not enforced as an unknown code (deviation 4).
- The CRLF-fenced reply (` ```json\r\n`) is rejected. Strict, and costs a repair re-ask.
- `_CAPABILITY_CACHE` holds strong references to handle classes, so it grows with dynamic classes.
- Evidence counts are stale (235 vs 237 files; log 214 and 1322).
- README places the P29 paragraph under "License".
- Mode flags changed from 100644 to 100755 on README and pyproject, inherited from the overlay.
- The `.coverage` and `.hypothesis` files are in the workspace root.

### HUMAN DECISION

- **D2, `min_confidence` default `None`.** Accept. The contract sketch's own comment says "overrides rubric default when set", which `None` honours. Identity encodes the effective value, so cohorts differ.
- **D3, token budget requires `reports_tokens`.** Accept (fail closed). It is stricter than the contract, which states it only for the monetary budget.
- **D4, `repeats > 1` requires `judge_disagreement`.** Accept. It is a reasonable narrowing of contract section 8.
- **D6/D7, salt.** Needs correction or owner note (F-7).
- **Per-handle-type capability detection at scope creation.** Accept. The contract says "once, at construction", but the handle type is only known when the scope is created.
- **`evaluate` / `submit` vs `evaluate_sync` split with `TypeError` on mismatch.** Accept. It fails before any state change.
- **ADR status "Accepted", ADR number 0010.** Provisional by the author. It needs owner confirmation of the G-C text and the number.

### EXTERNAL VERIFICATION

- The platform wire check (S09-AC03) is skipped in a default run. I did not re-execute it because it needs a scratch venv with platform dependencies from the package index.
- The sdist-install, OTel and typing steps of `verify_release_artifacts.py`: not run offline. Only the wheel steps passed.
- The CI workflow itself, the real-model walkthrough, benchmarks and load tests: not run.
- Re-run the evidence on the final committed tree after the D-1 exporter fix lands (baseline drift, section 1).
- Owner confirmation of the G-C approval wording quoted in ADR-0010.

## 13. Mutation summary (executed)

I ran 44 mutants across three batches against the judge package, using the judge-focused tests (unit, contract vectors, property, security and compat). I excluded only the flaky demo test.

| Result | Count |
|---|---|
| Killed by an assertion | 38 |
| Killed by hang only | 2 (M06, P05) |
| Equivalent | 1 (N10) |
| Real survivors | 5 (N05, P01, P02, P03, P04) |

Of the 5 real survivors, P02, P03 and P04 are admission-queue mutants and P01 is the drain-recording gate. Together they are F-6 and F-8.

All 24 critical-logic mutants of the first batch were killed. They covered the failure mapping, nonce, gate lock, UNKNOWN to PASS, budget, timeout, confidence threshold, identity `+`, unsampled recording, cause chaining and the cases listed in sections 5 to 9.

## 14. Required corrections before merge

1. Fix `submit()` so a missing loop causes no state change (F-1) and add a test.
2. Document sync timeout semantics and `ExecutorSyncProvider` in EVALUATE.md (F-2).
3. Document the gate constraints in the user docs and either guard or document the re-entrancy deadlock (F-3). Correct the S05-AC09 matrix note.
4. Fix the flaky demo test (F-5).
5. Add tests for queued-cancel admission and drain-recording overlap (F-6) and the C1 control vector (F-8).
6. Harden the example `default_post_json`: no cross-origin redirects, a response size cap (F-4).
7. Refresh evidence counts and re-run on the final merged tree.

Items F-7 and F-9 to F-13 can follow.

<!-- Saved verbatim by the coordinator from the fresh independent reviewer's hand-back (2026-10-16). Not edited by the author or the coordinator. -->
# P29 targeted verification of the review remediation

Reviewer: fresh independent, read-only. Date 2026-10-16. Workspace `<workspace>/agent-reliability-p29`.
Scratch only under the session scratchpad. Nothing in the workspace was edited, no commits, no network, no paid calls, no load tests.

Method note: the venvs install `agent_reliability` editable from the real workspace. So every mutant run set `PYTHONPATH=<copy>/src` and asserted `agent_reliability.__file__` resolves into the mutated copy. Each mutant ran in a fresh `rsync` copy with no `__pycache__`, `-B` and `PYTHONDONTWRITEBYTECODE=1`. A first mutant pass without that path override gave a false "survived" for everything, which is the editable-install trap, and I discarded it.

## Verdict: APPROVE

No BLOCKER, HIGH or MEDIUM defects found. Three LOW or informational notes are listed under "New defects". None needs a code change before merge.

## Finding verification

| Finding | Result | Evidence (executed unless marked "read") |
|---|---|---|
| F-1 submit outside a loop | VERIFIED | My own repro on 3.11, 3.12 and 3.13 with `drain_timeout_seconds=6`. `submit()` raised `RuntimeError`. `_seen=set()` and `_inflight={}`. Health `healthy`, `sink.failures=[]`, scope exit took 0.00 s, no `JudgeTimeoutError`. Fix reverted on a copy (loop resolved after `_prepare`): the mutant is KILLED by `test_f1_submit_outside_a_running_loop_raises_with_no_state_change` and `test_f1_the_indicator_stays_usable_after_a_rejected_submit`. |
| F-3 re-entrancy guard | VERIFIED | My own repro with a hard thread timeout. A sink calling `scope.evaluate_sync("b")` on the same scope inside `EvaluationRecorded` gets `RuntimeError("re-entrant use of an evaluation scope ...")`. The outer evaluation still returns `RECORDED_RESULT` on all three Pythons. A sink calling `scope.__exit__` from inside the gate waits for the drain timeout (2 s in my repro), then gets `RuntimeError`. It does not deadlock. A mutant with the guard off is KILLED: `test_f3_sink_reentering_...`. |
| F-3 docs and matrix | VERIFIED (read) | EVALUATE.md lines 175-179 say sinks and handlers run inside the gate, must be non-blocking, and re-entry raises `RuntimeError`. The same is stated in the runbook line 37, ADR-0010 consequences (lines 150-151) and README. Matrix S05-AC09 now says the documentation half was missing and is now added. |
| F-2 sync timeout docs | VERIFIED (read) | EVALUATE.md line 163 ("best effort"; provider socket timeout is the real bound; `ExecutorSyncProvider` is the enforcement option). Also runbook line 38 and ADR-0010 line 148. |
| F-4 `default_post_json` | VERIFIED | My own loopback experiment: server A answered 301, 302, 303, 307 and 308 with `Location` to server B. The call raised `HttpStatusError(<code>)` each time, and B received 0 requests, so no `Authorization` or `x-api-key` was forwarded. `_NoRedirect.redirect_request` returns `None` for any redirect, which also blocks an https-to-http downgrade. I could not test the downgrade over TLS offline; this is a read-only inference. A 2 MB response raised `ValueError("response too large")`, mapped to `JudgeProviderError` by `_raise_for_transport`. Non-loopback `http://` raised `ValueError`. Mutants "redirects followed" and "no size cap" are both KILLED. |
| F-5 demo test stability | VERIFIED | 8 parallel loops x 8 iterations = 64 runs of `test_s11_pilot_artifacts.py` (5 tests each) on 3.13: 64 of 64 passed. Two lines carried the pre-existing pytest-asyncio loop-scope deprecation warning, which is config noise. |
| F-6 mutants P01..P04 | VERIFIED | P01 (drain recording without the gate) KILLED by `test_f6_drain_recording_is_serialized_against_a_concurrent_completion`. P02 (granted waiter leaks its slot) KILLED by `..._cancelled_after_grant_hands_the_slot_on`. P03 (no abandon on cancel) KILLED by `test_f6_cancelling_queued_evaluations_returns_admission_to_idle`. P04 (LIFO) KILLED by two f6 tests. A "new arrival bypasses queued waiters" variant (P04b) survives the whole judge suite, but it is an equivalent mutant. `running < max` with waiters queued is unreachable, because `release()` hands the slot over without decrementing and a queued abandon does not change `_running`. |
| F-8 C1 vectors | VERIFIED | `127 <= ord(c) <= 159` mutated to `<=158`: KILLED by `reason-c1-upper-9f`. Mutated to `<=160`: KILLED by `reason-just-above-c1-a0-ok` and the s04 parity test. Lower bound mutated to `128`: KILLED by the `reason-del` and `reason-del-7f` vectors. |
| F-10 sync waiter abandon | VERIFIED | My own repro (`max_concurrency=1`, a held slot, a queued waiter whose `event.wait` raises `KeyboardInterrupt`): afterwards the queue was 0, `_running` 0 and no waiters. The mutant with abandon removed is KILLED by `test_f10_...`. |
| F-12 bounded guard | VERIFIED | The mutant removing `asyncio.timeout` in `judge.py` is KILLED by `test_f12_removing_the_provider_timeout_fails_instead_of_hanging` as an assertion, with no hang and no 240 s harness timeout. |
| F-7 salt (declined) | ACCEPTABLE, documented | The original review said "acceptable, but record it. Either relax it or leave a note". A note is now in the `SamplingPolicy` docstring (`values.py:331-334`) and EVALUATE.md "Vocabulary notes" lines 204-205, with the rejected example `_pilot`. The strict form is a subset of the contract charset, so tightening now and relaxing later is the safe direction. The reasoning cites plan P29-S01-AC02. I could not find the plan file in the workspace tree, so that citation is unverified, but the reasoning is internally consistent and acceptable. |
| F-9 recorded semantics | VERIFIED (read) | EVALUATE.md line 179, runbook line 37, ADR-0010 line 151. |
| F-11 late-reply tokens | VERIFIED (read) | EVALUATE.md line 168. |
| F-13a jitter | VERIFIED | NaN, bool and out-of-range values raise `ValueError("jitter must return a number in [0, 1]")`. The mutant "unchecked" is KILLED. Documented at EVALUATE.md line 170. |
| F-13b, F-13c | VERIFIED (read) | EVALUATE.md lines 203-206 (`judge_abstained` not enforced; CRLF-fenced reply rejected). |
| F-13d `WeakKeyDictionary` | VERIFIED | The cache is a `weakref.WeakKeyDictionary` (`coordinator.py:398`). The mutant with a plain dict is KILLED. |
| F-13e stale evidence | VERIFIED | My counts below (1547 passed, 1 skipped on all three Pythons) match the remediation report and `P29_TEST_EVIDENCE`. |
| F-13f README placement | VERIFIED | The P29 section is at README line 179, before "Documentation" (186) and "License" (203). |
| F-13g file modes | VERIFIED | `stat` shows README.md, pyproject.toml, ci.yml and verify_release_artifacts.py are 755 in both the workspace and the original tree. This work changed no mode. |
| F-13h root artifacts | VERIFIED, with a caveat | No `.coverage` or `.hypothesis` in the workspace root. A `.ruff_cache` directory is there; it is git-ignored and was probably created by my own `ruff format --check .` run, and it is harmless. |

## Requested cross-checks

**(a) Baseline and dependencies.**
- `shasum -c docs/P29_WORKSPACE_BASELINE.sha256` reports exactly 8 mismatches: README.md, docs/EVALUATE.md, docs/GA_CONTRACT.md, docs/ROADMAP.md, docs/VERSIONING.md, docs/adr/0007-…md, docs/adr/README.md, scripts/verify_release_artifacts.py.
- All 8 are named in `docs/P29_IMPLEMENTATION_LOG.md`. No pre-existing src module, `pyproject.toml`, workflow, platform or wire file differs.
- `dependencies = []` is intact.
- A grep of imports in the judge package found no non-stdlib, non-`agent_reliability` import.
- There is no P28 wire or platform change.

**(b) Review file integrity.** `docs/P29_INDEPENDENT_REVIEW.md` has mtime 16:46:44. Every remediation edit is later: tests 16:53, runbook 16:54, coordinator and engine 16:55, matrix and evidence 17:00 to 17:01. The first line is the coordinator's "Saved verbatim" comment. Content is consistent with what I read earlier (F-1..F-13, P01-P04 and N05 text unchanged). I did not keep a byte hash of my earlier reading.

**(c) Gates, run on 3.11, 3.12 and 3.13 (identical results; run from scratch copies against the same code).**
- `ruff check .`: all checks passed.
- `ruff format --check .`: 240 files already formatted. The remediation report says 239. The count differs by one, a trivial documentation discrepancy.
- `mypy src`: no issues in 65 source files.
- Full pytest in default mode: 1547 passed, 1 skipped on each Python (about 16-17 s).

**(d) Coordinator regression risk.**
- I could not recover a pre-remediation copy, so I read the changed regions (`_locked`, `submit`, `_run_sync` and `_run_async` abandon paths, `abandon()`, `_backoff`) rather than diffing.
- `submit()` now resolves the loop before `_prepare`, so the dedupe set and in-flight entry are never touched when it raises.
- 200-run cancellation-race stress on each of 3.11, 3.12 and 3.13. Setup: concurrency 3, 8 indicators with random provider delays, random cancel timing, about 50% of queued and running evaluations cancelled. All 200 runs per Python ended with `_running == 0`, no waiters, an empty `_inflight` and no hang.
- Observer/sink-exception sweep on 3.13: 24 combinations of sink raising, diagnostic handler raising, observer raising (`Exception` or `KeyboardInterrupt`), and success or provider failure. Every combination ended with `_running` 0, no waiters, empty `_inflight` and the gate released with `_holder=None`. Combinations with Exception-level raises exited cleanly. The `KeyboardInterrupt` observer propagated `KeyboardInterrupt`, which is correct for a `BaseException`.
- I did not count the events-versus-dispositions invariant separately beyond the existing tests.

**(e) Honesty.**
- Matrix header: "Pilot-ready NO", "Released NO", and "Independently verified: PARTIAL" with the final targeted re-verification pending. S12-AC02 reads BLOCKED, and the matrix says every PASS is author-run.
- Runbook SG-1..SG-6 remain IMPLEMENTED-in-SDK or documented, with process gates "NOT SATISFIED".
- No accuracy or calibration claim in the changed docs. The runbook says "reference rubrics are uncalibrated; no accuracy figure exists".

## New defects

- **LOW-1, informational.** A sink that calls `scope.__exit__` from inside the gate blocks until `drain_timeout_seconds` (default 60 s), then gets `RuntimeError`. It is bounded, not a deadlock, and it is a pathological use. The documented rule "sinks must not call the scope" covers it. No action required.
- **LOW-2, test-hygiene only.** The "P04b" variant (admission lets a new arrival bypass queued waiters) survives, but it is an equivalent mutant as argued above. A `# unreachable` note or an assertion in `_Admission.begin` would document that, but it is not required.
- **LOW-3, documentation.** The remediation report says 239 files formatted; the actual count is 240. This is a trivial update to the evidence text.

I found no regression in any pre-existing behavior.

## Executed versus read

- **Executed:**
  - ruff, ruff format, mypy and the full pytest on 3 Pythons.
  - The baseline hash check.
  - 16 mutants (F-1, F-3, P01, P02, P03, P04, P04b, F-10, N05 at 158, 160 and 128, F-12, jitter, cache, F-4 redirect, F-4 cap).
  - My own F-1, F-3 (sync, exit and submit variants), F-10 and F-4 loopback repros.
  - The 200-run stress on 3 Pythons and the 24-combination sink/observer sweep.
  - The 64-run demo-test stability loop.
  - `stat` mode comparison against the original tree.
- **Read only:** the F-2, F-7, F-9, F-11, F-13b and F-13c doc text, the matrix and runbook honesty review, the ADR consequences, the README placement, the mtime ordering, and the coordinator diff regions. My F-3 "submit" variant hit a `TypeError` because my second indicator was a sync judge. That was my repro's flaw, not a product defect, and the sync re-entrancy path was exercised on all three Pythons.
- **Not run:** the platform wire check, sdist/OTel/typing steps, CI, real models and load tests, as the task scope excludes them.

**Final verdict: APPROVE.** SG-1..SG-6 remain not satisfied and ADR-0010 owner confirmation is still pending, as the author already states; those are human gates, not code defects.

# P28 SDK D-1 - targeted verification of the review remediation (2026-10-16)

Independent verifier (fresh context). Scope: R-1..R-4 and R-6 fixes, scope of the change set, re-runs, E2E against the real SDK. This document claims no commit, release, publication or approval. I wrote only this file in the SDK repo; every experiment ran on copies under `<scratch>` (`agent_reliability.__file__` was checked and pointed into the copy each time).

## Verdict: VERIFIED

No new defect. One wording nit (N-1) below.

## 1. Fixes

| ID | Result | Evidence |
|---|---|---|
| R-1 | Fixed | New `test_sent_flag_is_per_attempt_so_a_later_verification_failure_still_counts` (plan "GWWW"). Real code: 16 passed in 3.3 s. Mutant deleting `record.sent = False` in `Core.take()` (`_http_delivery.py:851`): the new test FAILS (`_wait(_paused)` is False after the 90 s wait; 1 failed, 15 passed in 92.9 s). |
| R-2 | Fixed; root cause independently supported | See below. |
| R-3 | Fixed | `test_real_verification_failures_are_tls_verification_failed` asserts on the real httpx error: `__cause__` is `httpcore.ConnectError`, whose `__cause__` is None, `__suppress_context__` is True and `__context__` is `ssl.SSLCertVerificationError`; also asserts no request bytes reached the server. |
| R-4 | Fixed | Mutant without the cycle guard: `test_traversal_is_cycle_safe_and_bounded` FAILS on the `_bounded` assertion ("classifier did not terminate") in 26.9 s total, no hang. Mutant without the 64-node bound (`while pending:`): FAILS in 0.3 s (`network_not_sent` expected, got `tls_verification_failed`). |
| R-6 | Fixed | `docs/HTTP_EXPORTER.md` now defines "Consecutive" (see section 2). |

R-2 details. The test server's old behaviour (reply with `sendall`, then close immediately) was restored on a copy of the test file (everything else, including zeroed backoff and the 90 s wait, left as new).
- `test_a_completed_exchange_resets_the_failure_streak`, 8 parallel loops of 10 runs, old server: 79 of 80 passed; 1 failed at the same assertion the reviewer saw (`server.connections >= 6 and len(server.requests) >= 2`, after a 90 s wait). So the failure is independent of the backoff and of the 30 s timeout, and is caused by the server-side close. (I did not instrument the client to show the reset directly; the evidence is the reproduction with only the server behaviour changed.)
- New server (orderly `shutdown(SHUT_WR)` and drain), whole test file, Python 3.11: 6 parallel loops x 8 runs = 48 of 48 passed. Python 3.13 (run at the same time as the 3.11 loops): 10 of 10 passed.
- Seam: `sink._core._backoff = lambda _n: 0` in the new tests is the same attribute the existing exporter tests patch (`tests/unit/test_http_exporter.py:47` `result._backoff = lambda _n: 0` and `:535` `exporter._core._backoff = lambda n: 0`); the method is `Core._backoff` at `_http_delivery.py:867`, used at lines 959 and 1043.

## 2. Change-set scope

- `http_event_sink.py`: reverse-applying `gentlity-p28-e2e/patches/sdk_tls_verification_chain.patch` to the e2e `sdk-patched` copy gives sha256 `97689b8a687de630...` = the recorded original. Current file vs `sdk-patched`: comment line-wrapping only (code lines identical after stripping comment lines). Versus the original, only the body of `_failure` differs.
- Against `sdk_d1_before.txt` / `sdk_d1_before_status.txt`: the only changed hashes are `src/agent_reliability/adapters/http_event_sink.py` (97689b8a -> ddabd121) and `docs/HTTP_EXPORTER.md` (229c0759 -> 47c564d2). New files: `tests/unit/test_http_exporter_tls_real.py`, 11 files in `tests/fixtures/tls/`, and the two D-1 docs (plus this file). Nothing else changed. Status lines differ by exactly those `??` entries.
- `HTTP_EXPORTER.md`: the original is preserved in `sdk_build` and `rev5/sdkcopy` copies; the diff is four added lines (one paragraph after the L2 bullet): "Consecutive" counts TLS verification failures only; refused/closed/reset/timeouts/protocol mismatch and sent-attempt failures neither advance nor reset; only a completed HTTP exchange or `resume_endpoint()` resets. Nothing else.
- N-1 (nit): the remediation report calls this "one sentence"; it is two sentences.

## 3. Re-runs (on scratch copies)

- Full SDK suite: Python 3.11.17, 3.12.15, 3.13.16: 857 passed each.
- `ruff check` clean; `ruff format --check` 189 files formatted (copy includes the docs-only additions, no new .py beyond the test and generate.py); `mypy src` no issues in 46 files.
- `verify_p28_fixtures.py --platform-root .../agent-reliability-platform-integration`: 4 fixture hashes verified, platform comparison True.
- Node v26.12.0 `verify_p28_reference.mjs`: 76 canonical and 74 acknowledgement vectors passed.
- Scratch `python -m build` (agent_reliability-1.2.1 sdist + wheel) and `scripts/verify_release_artifacts.py`: all stages ok (sdist install/quickstart, wheel import probe, HTTP extra mocked delivery, OTel extra, downstream strict mypy).

## 4. E2E against the real SDK

Scratch workspace copy of `d1_ws/gentlity-p28-e2e`, variant `real` (SDKSRC = `<workspace>/agent-reliability/src`; BASELINE xfail/skip applies only to `baseline`). The environment test asserts `/Development/agent-reliability/src/` is in `agent_reliability.__file__` for `real` and passed. I changed only my copy of `run_e2e.sh` to take the PostgreSQL port from 55901/55902 (it normally uses an ephemeral port); the harness servers still use ephemeral ports.
- `run_e2e.sh 16 real -- -q`: 80 passed in 111.0 s (PostgreSQL 16.15).
- `run_e2e.sh 17 real -- -q`: 80 passed in 111.7 s (PostgreSQL 17.11).
- Python 3.11.17, httpx 0.28.1, Node v26.12.0. No expected failures.

## 5. Governance wording

The remediation report states "nothing is committed, released or published", names no owner or reviewer, and lists the remaining gates: whole-change-set review, R-5 (throwaway private keys in the sdist; not changed), a CHANGELOG entry (there is none for the exporter), owner confirmation of "consecutive", commit/release authorization, platform-first release evidence, and D14 / ADR-0023 Appendix A.2 approval (stated as unapproved). The fixtures README labels the keys test-only. The review document is the earlier reviewer's own text; its figures (856 tests, 11 of 12 mutants) pre-date the fix and the remediation report says so ("see the review").

## Not done / limits
Windows and system-Python variants were not run. The R-2 root cause is supported by reproduction rather than direct client-side capture of the connection reset. R-5, CHANGELOG, D14 / ADR-0023 A.2 remain open and are not part of this verdict.

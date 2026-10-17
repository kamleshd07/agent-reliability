# P28 SDK D-1 fix - independent review

Reviewer: independent (fresh context). Subject: SDK repo `main @7aa6883` with uncommitted P28 work. Scope: the D-1 fix to `_failure()` in `src/agent_reliability/adapters/http_event_sink.py`, the new test file `tests/unit/test_http_exporter_tls_real.py` and the fixtures in `tests/fixtures/tls/`. This review does not claim commit, release, publication or approval of anything.

## Verdict

**D-1 FIXED AND VERIFIED** for the production code. There are no BLOCKER or HIGH findings. Two MEDIUM test-quality findings and four LOW/INFORMATIONAL items remain. Fixing the MEDIUM ones is recommended before the work is committed. They do not reopen D-1.

## Finding register

| ID | Sev | Location | Evidence | Impact | Reproduction | Remediation | Class |
|---|---|---|---|---|---|---|---|
| R-1 | MEDIUM | `tests/unit/test_http_exporter_tls_real.py` (no test covers the per-attempt reset of `record.sent`); source `src/agent_reliability/adapters/_http_delivery.py:851` | Mutant M10 (delete `record.sent = False` in `take()`) SURVIVES the whole new file and `test_http_exporter.py`. With my own TLS server, plan "D W W W" (attempt 1 sent a request and got no reply, then three verification failures): the real code reaches `endpoint_paused` at connection 4 and keeps `uncertain=True`. The M10 mutant never pauses (10 connections, `retry_exhausted`). | The stated safety property "a verification failure on a retry after an earlier SENT attempt is still classified correctly" is unguarded. A regression there would silently bring back D-1 on retries. | Delete `record.sent = False` in a copy of `_http_delivery.py` and run the new tests. They pass. | Add a test with a server plan like "DWWWG": first connection completes TLS, reads the request, closes with no reply; then three wrong-hostname handshakes. Assert the pause at 4 connections and that the record stays uncertain. | test-gap |
| R-2 | MEDIUM | `tests/unit/test_http_exporter_tls_real.py:334` (`test_a_completed_exchange_resets_the_failure_streak`) and the `_wait(... timeout=30)` helper | Under 8 parallel pytest processes (3.11) one of 96 runs failed: `_wait` timed out after 30s (run took 37s) because 6 connections need random backoff of up to 2s each plus CPU contention. Isolated: 20 of 20 pass on 3.11. 3.13: 5 of 5 pass. 5-way parallel: 60 of 60 pass, and one earlier 5-way run failed 1 of 25. | Rare CI flake on a loaded runner. | Run `pytest tests/unit/test_http_exporter_tls_real.py` in 8 parallel loops. | Raise the wait to 90s or patch backoff to zero (the module-level `random.uniform` in `_backoff`) in the slow tests. Do not use sleeps. | flake |
| R-3 | LOW | `tests/unit/test_http_exporter_tls_real.py:158-161` | The comment "The httpcore exception hides the SSL error: no __cause__, context suppressed" is followed by an unrelated assertion. The real-handshake test never asserts the D-1 premise (`__cause__ is None`, `__suppress_context__ is True`, SSL error present only via `__context__`) on the actual httpcore exception. The synthetic test covers the shape only. | If a future httpx makes the chain visible through `__cause__`, the real tests would still pass but would stop exercising D-1. | Read the test. | Walk the real error to the httpcore node and assert the premise, or delete the stale comment. | test-hygiene |
| R-4 | LOW | `tests/unit/test_http_exporter_tls_real.py:262-271` (cycle test) and mutant M5 | Removing the cycle guard turns the test into an infinite loop that ends only at an external timeout. No pytest-timeout is configured. | A regression shows up as a hung CI job rather than a clean failure. | Remove `if id(node) in seen: continue` in a copy. The test run hangs (killed by my 240s harness timeout). | Run the cyclic case in a worker thread with a join timeout, or use `faulthandler`/pytest-timeout. | test-hygiene |
| R-5 | LOW | `tests/fixtures/tls/*.key` (4 files), included in the sdist | `grep "BEGIN PRIVATE KEY"` finds 4 PEM keys in git-untracked-but-to-be-committed files. They are labelled by `README.md` and `generate.py`, and the CA key was not kept. `.gitignore` does not exclude them. A scratch `python -m build` shows the sdist contains `tests/fixtures/tls/*.key` and the new test. The wheel contains none of them (it ships only `src/agent_reliability`), and `verify_release_artifacts.py` passes. | Secret scanners (GitHub secret scanning, trufflehog, PyPI-side scanners) will flag 4 private keys. This causes noise and can block a policy-enforcing pipeline or hold the sdist upload. No real risk, since the keys protect nothing. | `tar tzf dist/*.tar.gz` on a scratch build. | Either generate the keys at test time in a session fixture (needs `cryptography`, which is not a dev dependency), allowlist the directory in the scanner config, or exclude `tests/fixtures/tls/*.key` from the sdist. Decide this before any release. | release-gate |
| R-6 | INFORMATIONAL | `_http_delivery.py:887,919-921` | Non-verification failures (protocol mismatch, TCP close, refused) neither increment nor reset the TLS streak. With plan "W P W P W" the pause occurs at the third verification failure (connection 5). A sent-attempt failure ("D D D D D") never counts. This matches the decision text ("only a verified exchange resets"), and "consecutive" is therefore read as "consecutive among verification outcomes". | None if intended. | `sinks.py` scenario "WPWPWPG" in `<scratch>`. | State that reading explicitly in `HTTP_EXPORTER.md`, or confirm it with the owner. | doc-clarity |
| R-7 | INFORMATIONAL | `http_event_sink.py:118-145` | Behaviour change from the original, which labelled a `SSLCertVerificationError` found in the `__cause__` chain as `tls_verification_failed` even when `sent` was True. It now returns `indeterminate` in that case. This is intentional and consistent with the spec, but it is a classification change beyond adding `__context__`. | None in practice: a verification failure cannot occur after the request was sent. | Compare against the reconstructed original. | None. Mention it in the change note. | note |

No public API or wire change was found. `CHANGELOG.md` has no entry for the exporter at all (pre-existing P28 gap, not specific to D-1).

## Areas checked and found sound

**(a) Code diff.**
- The real file differs from `gentlity-p28-e2e/sdk-patched/.../http_event_sink.py` only in comment line-wrapping (diff shown, no code lines differ).
- Reverse-applying the patch to the sdk-patched copy yields sha256 `97689b8a687de630...`, which matches the stated original. The real file differs from that original only in the `_failure` body plus comments. Nothing else changed in the file.
- The traversal follows both `__cause__` and `__context__`. It is bounded to 64 visited nodes and cycle-safe (an id set).
- `__suppress_context__` is ignored.
- The classification happens only when `record.sent` is False. `sent` is cleared in `take()` at `_http_delivery.py:851` for each attempt and set by `mark_sent()` on the `send_request_headers.started` trace.
- Both the sync sink (`http_event_sink.py:335`) and the async sink (`:627`) call the same `_failure`.
- Streak accounting is at `_http_delivery.py:919-921`. A completed exchange resets it at `:887`. `resume("endpoint_paused")` resets it at `:825`.

**(b) Independent real-TLS reproduction.** I used my own throwaway CA, certificates and TLS servers, real httpx 0.28.1 / httpcore 1.0.9 and OpenSSL 3.5.9. The SDK ran from a copy, and I verified `agent_reliability.__file__` was the copy.
- `tls_verification_failed`: untrusted CA, wrong hostname, expired, self-signed, leaf signed by a rogue CA, and a missing intermediate (chain incomplete).
- The complete chain connects (HTTP 500 returned).
- `network_not_sent`: plain-HTTP reply on an https URL (protocol mismatch), TCP close at handshake, no shared cipher/version, and connection refused.
- In every case the real exception has `__cause__` None on the httpcore node, with the SSL error reachable only through `__context__` and suppressed. The same errors given a SENT record classify as `indeterminate`.
- Pause behaviour:
  - Plan "WWWG": exactly 3 handshakes, then paused. The server saw 0 request bytes, so no credential was sent, and none after settling. The 2 records stayed queued (held, not dropped).
  - Plan "WWG" (two failures): no pause.
  - A completed exchange resets the streak ("WWGWWG" never pauses).
  - `resume_endpoint()` clears the streak and the gate. The next handshake happens and the record stays queued.
  - Async sink: same results (pause at 3, resume works, reset by exchange).
  - Mixed verification kinds (rogue, expired, selfsigned) count together.
  - A non-verification TLS failure between verification failures is neutral (R-6).
  - Verification failure on retries after an earlier SENT attempt (plan "DWWW") pauses at connection 4 and keeps `uncertain=True`.
- No sentinel credential appeared in `repr(sink)`, `repr(sink.status)` or any captured log (root logger at level 1, about 50 KB).

**(c) Mutation testing.** Twelve mutants were run against copies of the SDK src, with the new file plus `test_http_exporter.py`. Eleven were killed and one survived (R-1).

| Mutant | Result |
|---|---|
| `__cause__`-only (original D-1) | killed by 9 of the 15 new tests |
| `__context__`-only | killed |
| honour `__suppress_context__` | killed by the real-handshake tests (this proves honouring it re-introduces D-1 with real TLS) |
| drop the `not record.sent` condition | killed |
| remove the node bound | killed |
| remove the cycle guard | killed only by hang/timeout (R-4) |
| exchange never resets the streak | killed |
| `resume_endpoint` does not reset | killed |
| threshold 4 | killed |
| threshold 2 | killed |
| SSL error only on the first node | killed |
| `sent` not reset per attempt (M10) | SURVIVED (R-1) |

**Fixtures.**
- Validity is fixed: CA and valid leaves 2020-01-01 to 2120-01-01, the expired leaf 2020-01-01 to 2021-01-01. There is no time bomb, and the expired fixture stays expired.
- Strict X.509 extensions (SKI, AKI, key usage, EKU, SAN) are present. This is needed on Python 3.13 and harmless elsewhere.
- Tests use `Path` and loopback only. The server binds 127.0.0.1 while the URL uses `localhost`. I saw no Windows-specific concern, but I did not run on Windows.
- Ports are ephemeral.
- `generate.py` is not a test dependency.
- Flakiness: 20 of 20 passes on 3.11, 5 of 5 on 3.13, then the parallel-load failures in R-2.

**(d) Preservation.** I compared the tree against `sdk_d1_before.txt` and `sdk_d1_before_status.txt`.
- The only changed tracked-or-untracked content is `src/agent_reliability/adapters/http_event_sink.py` (hash changed from 97689b8a... to ddabd121...). That file was already untracked P28 work.
- There are 12 new files: `tests/unit/test_http_exporter_tls_real.py` and 11 under `tests/fixtures/tls/` (`README.md`, `ca.crt`, `generate.py`, and `.crt`/`.key` pairs for `expired`, `localhost`, `other`, `selfsigned`).
- All other hashes are identical. No platform or E2E workspace file was changed by this work.
- The scratch workspace `d1_ws/gentlity-p28-e2e` differs from the real workspace only in `scripts/run_e2e.sh` (adds the `real` variant) and `tests/test_a_delivery.py`.
- I wrote only this report in the SDK repo.

**(e) E2E uses the real SDK.**
- In the real workspace, `scripts/run_e2e.sh` uses `SDKSRC=$SDK/src` (the real SDK) for `baseline`, and the built `sdk-patched/src` copy for `patched`.
- The scratch copy adds `real`, which also maps to the real SDK src.
- The `real` variant disables the baseline xfails and skips (`BASELINE` is only true for `baseline`).
- `test_environment_is_the_integrated_platform_and_the_sdk_working_copy` asserts `/Development/agent-reliability/src/` in `agent_reliability.__file__` for `real`, and it PASSED.
- I re-ran on my own copy at `<scratch>`, with the PostgreSQL port moved to 55811/55812 and `E2E_TMPDIR` under rev5. PostgreSQL 16: 80 passed in 110s. PostgreSQL 17: 80 passed in 109s. The `test_g_tls_classifier.py` tests all ran as passes.
- Caveat: the harness's own test servers use ephemeral ports, which I could not constrain.

**(f) Re-runs on a copy, with `__file__` verified.**
- Full SDK suite: 856 passed on Python 3.11.17, 3.12.15 and 3.13.16.
- `ruff check` clean. `ruff format --check`: 187 files already formatted. `mypy src`: no issues in 46 files.
- `scripts/verify_p28_fixtures.py`: ok (4 fixture hashes verified).
- On a scratch copy, `python -m build` succeeded and `scripts/verify_release_artifacts.py` exited 0 (wheel, sdist, extras and downstream mypy all ok). The wheel contains no tests or keys. The sdist contains the fixtures and the new test (R-5).
- Not re-run: the Node reference check, and Windows or macOS system-Python variants.

## Governance

The work, tests, README and docs make no claim of commit, release, publication or approval. I found no such wording in the new files.

Remaining gates I can see (not approvals):
- Review of the whole uncommitted P28 exporter change set. The SDK tree is still on `main @7aa6883` with about 43 uncommitted entries.
- A decision on R-5 (secret-scanner policy for committed throwaway keys and sdist contents).
- A CHANGELOG/release-note entry, since none covers the exporter.
- Owner confirmation of the L2 "consecutive" reading (R-6).
- Version and release preparation, which are out of scope for D-1.

## Scratch artifacts

All experiments are under `<scratch>`:
- `my/` holds my own CA/certificate generator, the TLS server and the scenario scripts.
- `mut/` holds the mutant source copies.
- `ws/` holds the E2E workspace copy.
- `pkg/` holds the scratch build.
- The logs are in the same directory (`e2e16.txt`, `e2e17.txt`, `suite_*.txt`).

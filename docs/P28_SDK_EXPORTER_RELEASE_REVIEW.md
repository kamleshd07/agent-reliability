# P28 SDK HTTP exporter: independent release review (rev7)

Reviewer: independent, fresh context, read-only. Scope: the whole uncommitted change set on `main` @7aa6883. All experiments ran under `<scratch>`. This is a technical review. It is not a human approval and invents none.

## Verdict: FINDINGS TO FIX

Severity counts: BLOCKER 0, HIGH 1, MEDIUM 4, LOW 6, INFORMATIONAL 4.

No defect was found in the D-1 fix, and its review was not redone. The HIGH finding is a release-pipeline defect, not a production-code defect.

## Change set and delta of this task
- 11 modified tracked files, plus untracked files (git status is 36 entries). Re-verified against `<scratch>` (sha256 manifest).
- Exactly these changed in this task:
  - `CHANGELOG.md` (new)
  - `docs/HTTP_EXPORTER.md`
  - `pyproject.toml`
  - `scripts/verify_release_artifacts.py`
  - `tests/unit/test_http_exporter_tls_real.py`
  - `tests/fixtures/tls/*` (11 files removed)
- Nothing else differs.

## Re-run results
All commands used PYTHONDONTWRITEBYTECODE=1 and `-p no:cacheprovider`. `agent_reliability.__file__` was verified to be the real repo `src` in each venv. httpx was 0.28.1 and cryptography 50.0.2 in all three venvs.

| Check | Result |
|---|---|
| Full SDK suite, Python 3.11.17 | 857 passed |
| Full SDK suite, Python 3.12.15 | 857 passed |
| Full SDK suite, Python 3.13.16 | 857 passed |
| `ruff check` (0.17.1) | pass |
| `ruff format --check` | 188 files already formatted |
| `mypy src` (2.4.0) | no issues in 46 files |
| `verify_p28_fixtures.py --platform-root .../agent-reliability-platform-integration` | 4 hashes verified, platform comparison True |
| `verify_p28_fixtures.py` without a platform root (the CI form) | 4 hashes verified, comparison False, exit 0 |
| `node scripts/verify_p28_reference.mjs` (node v26.12.0) | 76 canonical vectors and 74 acknowledgement vectors passed |
| Real-TLS file, run once | 16 passed in 3.9 s; no temp dir left behind; import cost about 185 ms including httpx and cryptography |
| Real-TLS file, 30 sequential loops | 30 of 30 passed |
| Real-TLS file, 6 parallel loops of 8 (48 runs) under CPU contention | 48 of 48 passed |
| Wheel and sdist built on a scratch copy (hatchling 1.32.4) | built; 51 wheel entries, 207 sdist entries |

- Not run: E2E suites 16 and 17 (optional, time).
- Not run: `verify_release_artifacts.py` end to end, because it pip-installs `[http]` from an index and package-index access was out of scope. Only `_inspect_artifacts` and `_assert_no_private_keys` ran, directly.

## Finding register

### F-1 HIGH: release workflow and contributor docs do not install the `http` extra
- **Location:** `.github/workflows/release.yml:38` (unchanged by the change set); `CONTRIBUTING.md:15`.
- **Evidence:**
  - `release.yml` runs `pip install -e ".[dev,otel-test]" build`, then `mypy src` and `pytest`.
  - `ci.yml` was updated to `[dev,http]`, but the tag-triggered release job was not.
  - All three exporter test files import httpx at module top level. With httpx missing (simulated), collection fails: "2 errors during collection ... ModuleNotFoundError: No module named 'httpx'". A collection error aborts the whole pytest session.
  - `mypy src` under `strict` is expected to fail on `import httpx`. This was not run.
- **Impact:** the tag-triggered "Full quality gates" would fail, so a release could not be built. `pip install -e ".[dev]"` as documented in CONTRIBUTING breaks `pytest` for contributors. The failure is closed (nothing bad ships).
- **Reproduction:** `PYTHONPATH=rev7/nohttpx pytest tests/unit/test_http_exporter.py`.
- **Fix:** add `http` to `release.yml` and CONTRIBUTING, or put `httpx` in the `dev` extra. Optionally `pytest.importorskip("httpx")` in the test files (see F-12 on silent skips).
- **Class:** NEW defect in the uncommitted change set.

### F-2 MEDIUM: an explicit HTTPS proxy defeats TLS-verification classification and the endpoint pause
- **Location:** `http_event_sink.py:286-291` (the trace hook), `:118-145` (`_failure`).
- **Evidence:**
  - httpcore `http_proxy.py:286` builds the `CONNECT` request with `extensions=request.extensions`. The trace hook therefore fires `send_request_headers.started` for the CONNECT, and `mark_sent` is called.
  - Experiment `rev7/e2.py` used a local CONNECT proxy and a TLS server with a wrong-hostname certificate. The server received 0 HTTP bytes after 3 attempts, yet the record ended `retry_exhausted` with `may_have_committed=True`. `pause_reason` stayed None and the endpoint never paused.
  - The control run without the proxy pauses correctly.
- **Impact:** with the documented `proxy=` option, L2 (the third consecutive verification failure pauses the endpoint) never fires. Records burn their retries, and `exhausted_may_have_committed` gives false alarms although no request byte left. No credential is sent over the unverified channel, so there is no confidentiality loss.
- **Remediation:** in the trace hook, ignore requests whose `info["request"].method == b"CONNECT"`, or mark sent only after the tunnel is established. Add a CONNECT-proxy test.
- **Class:** NEW defect (the forward proxy was a stated unverified area; this is new evidence).

### F-3 MEDIUM: sync worker has no total per-attempt deadline; a slow-drip response pins both workers
- **Location:** `http_event_sink.py:308-322` (the sync body loop and timeouts at `:113`).
- **Evidence:**
  - Experiment `e3.py` used a plaintext loopback server that sends headers and then 1 byte per second. The read timeout is per read, so it never fires.
  - After 12 s with `active_delivery_seconds=3`, two records were reported `retry_exhausted`, but only 2 connections had ever been made. The third run stayed `queued` and was never dispatched.
  - The docs claim the workers "finish or time out in the background".
  - The async sink cancels via its maintenance task, so only the sync sink is affected.
- **Impact:** a degraded or hostile endpoint or proxy can stall all sync delivery for hours (roughly 64 KB at 1 byte/s). Header-phase drip behaves the same way.
- **Remediation:** check the record's presence and a wall-clock deadline between chunks, and use an abortable transport or a total timeout.
- **Class:** pre-existing in the uncommitted exporter.

### F-4 MEDIUM: compatibility class of the new public surface is undefined (owner decision and docs gap)
- **Location:** `docs/GA_CONTRACT.md` ("Public namespace rule"), `COMPATIBILITY.md`, `VERSIONING.md` (unchanged); `ports/__init__.py` does not re-export `HealthEvidenceSink`.
- **Evidence:** by GA_CONTRACT's own rule, submodules not re-exported by a listed namespace are INTERNAL. So `adapters.http_event_sink`, `HealthEvidenceSink` and `CompositeEventSink`'s new methods have no declared stability class. `HTTP_EXPORTER.md` states none. Separately, `RunHandle.record_evaluation_failure` gained a keyword (additive; the compat test was updated).
- **Impact:** an ambiguous support promise, and no version bump or `__version__` decision (`__version__` is 1.2.1).
- **Remediation:** the owner decides the class (EXPERIMENTAL is the likely fit) and the version; update GA_CONTRACT, COMPATIBILITY and VERSIONING at release time.
- **Class:** owner decision.

### F-5 MEDIUM: test-suite gaps (surviving mutants)
24 mutants of exporter, protocol and delivery code were applied on a scratch copy and run against the three exporter test files and the contract file. Mutants M1 to M14 and M18 to M21 were KILLED. M24 was KILLED and so was M17 (M17's pattern matched two sites, so it was not applied; it is listed below as unapplied).

Survivors:
- **M15** (naive-timestamp rejection removed at `_http_delivery.py:138`): no test asserts `timestamp_naive`. A naive datetime would be silently interpreted in local time.
- **M16** (request 64 KiB cap raised): no test covers `request_too_large`.
- **M22** (the `@` userinfo check removed in `_authority`): URLs of the form `https://user@host/` are untested. Only the colon form is exercised, and the colon form may be caught by the `count(":")` rule.
- **M23** (the explicit cookie-header pop removed): redundant with the reject-all cookie jar, so equivalent or defence-in-depth. Not a defect.
- **M17** (response cap): not applied because the pattern matched two sites (sync and async). The response cap is not shown to be mutation-tested.

Remediation: add the three tests. Class: pre-existing.

### F-6 LOW: the L2 paragraph of `HTTP_EXPORTER.md` over-claims test coverage
- **Location:** `docs/HTTP_EXPORTER.md:132` ("all implemented and covered by real-handshake tests").
- **Verified correct against the code:**
  - The streak is per instance.
  - Only an unsent cert-verification failure counts.
  - Other network failures neither advance nor reset it.
  - Any completed HTTP exchange resets it (`failure is None` branch).
  - `resume_endpoint` resets it.
  - A redirect pauses at once.
  - Records are held, not dropped, up to the residence limit.
  - "Third consecutive" is `>= 3`.
- **Not covered by tests:**
  - Neutrality of a non-TLS failure interleaved between TLS failures. Only the `_failure` classification is tested for refused and handshake-closed connections.
  - Cipher or protocol mismatch.
  - Reset on a status other than 500.
  - A pause that needs `retry_max_attempts` greater than the streak. With `retry_max_attempts=2` a single record exhausts before the third failure; only a later record can complete the streak.
- **Remediation:** soften the wording or add the tests.

### F-7 LOW: `httpx` logs the full endpoint URL at INFO
- **Location:** third-party behaviour; `HTTP_EXPORTER.md` Security section and CHANGELOG ("URLs ... never appear in diagnostics").
- **Evidence:** with logging at DEBUG, `INFO:httpx:HTTP Request: POST https://example.com/api/v1/evidence/runs?secretq=1 "HTTP/1.1 201 Created"`. The token did not appear.
- **Impact:** a query string, if it carries sensitive data, leaks to application logs. The docs only warn against logging raw request objects.
- **Remediation:** document it, or add a filter on the `httpx` logger.

### F-8 LOW: a missing httpx gives a bare `ModuleNotFoundError`
- **Location:** `http_event_sink.py:21`.
- **Evidence:** importing the module without httpx gives only "No module named 'httpx'", with no hint of `agent-reliability[http]`. Core import does not import httpx, which is verified.
- **Remediation:** wrap the import and raise an `ImportError` that names the extra.

### F-9 LOW: the sdist ships agent-instruction files and internal review reports
- **Evidence:** the built sdist contains `CLAUDE.md`, `AGENTS.md`, `docs/P28_SDK_*.md` (8 internal review and remediation reports), `tests/fixtures/p28`, the scripts and the exporter tests. There are no key files. The wheel contains only the 3 new modules (not tests, fixtures or scripts).
- **Remediation:** add an sdist `exclude` in the hatch configuration, or decide the inclusion deliberately.

### F-10 LOW: idle polling
- **Location:** `http_event_sink.py:273-281`.
- **Evidence:** each of the 2 workers wakes every 10 ms and builds a full status snapshot. Idle CPU was about 0.03 s per 5 s empty and about 0.12 s per 5 s with 900 history rows (roughly 2.4% of one core).
- **Remediation:** event-driven waits. Cosmetic otherwise.

### F-11 LOW: CHANGELOG "Fixed" entry, and a missing item
- **Evidence:** the D-1 entry describes a defect of the first implementation of unreleased code under "Fixed", which implies a released bug. It also invents no date, version or publication status, which is correct.
- **Verified:**
  - The Added items match the code.
  - "No runtime dependencies" is correct.
  - The Changed note on `_assert_no_private_keys` is correct.
- **Missing:**
  - The CI changes.
  - The automatic `submit_measurement_health` and `release_run` calls made at run finish when the sink supports them (a behaviour change for such sinks).
  - The new public methods on `CompositeEventSink`.
- **Remediation:** fold the D-1 item into Added and note the behaviour changes.

### Informational (no action required)
- **I-1:** `_assert_no_private_keys` was validated. It detected a PEM block in a wheel `.py`, in a sdist file, and a `.KEY` filename, and the real artifacts pass. The marker does not match PGP `PRIVATE KEY BLOCK`, JWK or PuTTY keys, which is acceptable for the purpose.
- **I-2:** the TLS test now skips the whole module if `cryptography` is missing (`pytest.importorskip`). That is acceptable only because the dev extra is installed in CI. If the dev extra is ever dropped, the 16 tests would pass silently. A guard is recommended, such as failing when `CI` is set. Temp-dir generation, `atexit` cleanup, 0600 key files and fixed 2020 to 2120 validity are sound. Windows was not run, and `atexit` `rmtree` ignores errors.
- **I-3:** `_client_options` uses `ssl.create_default_context(cafile=...)`. On Python 3.13 this adds strict X.509 verification flags that private-CA users may hit. Not a defect here: tests pass on 3.13.
- **I-4:** the code reads the private `_client._transport` to special-case `MockTransport`. Test-seam smell only. Minor items also noted: `AsyncHTTPEventSink` raises a raw `RuntimeError` outside a loop; endpoint host syntax beyond A-https-1 is validated only at send time.

## Areas checked and found sound
- **Isolation of ambient configuration:** verified with real handshakes. SSL_CERT_FILE, SSL_CERT_DIR, REQUESTS_CA_BUNDLE, CURL_CA_BUNDLE, HTTPS_PROXY and ALL_PROXY set to the test CA or an unreachable proxy had no effect: the handshake failed verification and no proxy connection was made.
- **Credential handling:** header-injection characters are rejected by the charset check (a mutant confirms the test). The token is absent from snapshots and logs.
- **Redirects:** never followed, and a 3xx pauses the endpoint (mutant killed).
- **Cookies:** a reject-all jar.
- **Evidence correctness:** the canonical digest matches the frozen v1 vectors, the Node reference and the platform integration tree. The v2 identity inputs are enforced by mutants. Retries reuse the stored bytes. Event ids are stable. Per-run FIFO is enforced. The closure reserve is enforced.
- **Delivery control:** the 429 handling, RA-b parsing and sticky uncertainty are mutant-checked.
- **Core import:** does not import httpx.
- **Backward compatibility:** existing `EventSink` implementations stay valid, and the compat signature test was updated for the additive keyword.

## Governance assessment (from the docs only; no approvals are invented)
- **D14 / ADR-0023 Appendix A.2:** open, "stated as unapproved" in the D1 targeted verification.
- **Platform-first per-instance release evidence:** required by `HTTP_EXPORTER.md` and still open.
- **SDK release or commit authorization:** none recorded. The reports say nothing is committed or published. The changes remain uncommitted.
- **Required sign-offs:** no named owner or reviewer sign-off exists. Subagent reviews are not human approval. The owner's confirmation of "consecutive" for L2 is listed as open.
- **Whole-change-set review:** this document is that review. Its verdict is FINDINGS TO FIX.
- **Windows:** not run. Only native-store emulation was exercised.
- **PostgreSQL 18:** not run.
- **Platform-terminated TLS and production-equivalent OIDC:** not demonstrated.
- **Real forward proxy:** only a local CONNECT stub was tried here, and it surfaced F-2. No production proxy was exercised.
- **Connect timeout:** not verified.
- **Live PC-1/PC-2 platform integration:** gated.

## Conclusion
Fix F-1 (mechanical, release-blocking in practice), F-2, F-3 and the F-5 test gaps. F-4 needs an owner decision. The remaining items are LOW or optional. The governance gates above are external and unresolved.

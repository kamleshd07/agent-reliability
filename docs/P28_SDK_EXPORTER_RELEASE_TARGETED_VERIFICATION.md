# P28 SDK exporter release remediation: targeted verification

Independent, targeted check of one remediation round for
`docs/P28_SDK_EXPORTER_RELEASE_REVIEW.md`. No commit, release or publication is
claimed or implied. Experiments ran only under `<scratch>`
(copies; `agent_reliability.__file__` confirmed to point into each copy).

## Verdict: VERIFIED

New findings: 0 HIGH, 0 MEDIUM, 0 LOW, 2 INFO.

## 1. Claimed fixes

| Finding | Result |
|---|---|
| F-1 | Confirmed. `release.yml` installs `.[dev,http,otel-test]` once, before the "Full quality gates" step (ruff, mypy src, pytest --cov). Nothing else in that workflow needs extras: the tag check uses the stdlib, build/verify need none, and `verify_release_artifacts.py` installs the `http` and `otel` extras itself in its own venvs. `ci.yml` installs `.[dev,http]` in the lint/mypy job and `.[dev,otel-test,http]` in the test matrix. Its `artifacts` job only builds and runs the verifier. CONTRIBUTING.md uses `.[dev,http,otel-test]`. No stale `[dev]`-only install remains (the TLS test comment about `cryptography` being in `dev` is accurate). |
| F-2 | Confirmed. I captured the real httpcore trace with a CONNECT stub proxy: for both the sync and the async client the only `http11.send_request_headers.started` event carries `request.method == b"CONNECT"`, so `_is_proxy_connect` matches real data. Neutralising the function to `return False` on a copy makes `test_verification_failures_through_an_explicit_proxy_pause_the_endpoint` fail (about 90 s `_wait` timeout). The async path is also fixed. A scratch async proxy test (not in the repo) passed on the real code (3 CONNECTs, paused, no request reached the server) and failed with the async `and not _is_proxy_connect(info)` removed. |
| F-3 | Mitigation behaves as claimed. With the body-budget condition removed on a copy, the trickle regression test fails. With `iter_raw(chunk_size=4096)` restored and the budget kept, the test also fails, so omitting `chunk_size` is load-bearing. Acknowledgement parsing is unaffected: a valid 201 acknowledgement delivered one byte at a time with 2 ms gaps was recorded as COMMITTED, and a 65,537-byte body was not an acknowledgement (retry_exhausted). A header trickle (1 byte every 0.5 s) still pins the worker: still 1 connection after 12 s, as HTTP_EXPORTER.md documents. The async sink still uses `aiter_raw(chunk_size=4096)`; that does not matter, because its maintenance task cancels expired attempts by time. |
| F-4, F-9, F-10 | Left unchanged, as stated. These remain owner decisions or optional. The sdist still ships CLAUDE.md, AGENTS.md and 9 `docs/P28_SDK_*` reports (including the two review reports) and `tests/fixtures/p28/*`. The release review and the earlier D1 review mention "PRIVATE KEY" in prose only, and the verifier's marker is the dashed PEM footer, so they do not trip it. |
| F-5 | Mutation-tested on copies; every mutant is killed. Removing the naive-timestamp check fails `test_naive_timestamps_are_rejected_before_admission`. Raising the cap to 70000 and tightening it to `>=` 65536 both fail `test_request_body_cap_is_exactly_64_kib`. Allowing `@` in the authority fails the userinfo tests. Removing the body budget fails the trickle test. The missing-httpx and core-import tests pass (see F-8). |
| F-6, F-7 | The interleaved plain-TCP test (`WXWWG`) passes. The L2 wording and the httpx URL-logging note are present in HTTP_EXPORTER.md. |
| F-8 | The ImportError text is "...pip install 'agent-reliability[http]'". It is exercised through a subprocess with `sys.modules['httpx'] = None`. Importing `agent_reliability`, `.sdk` and `.adapters` leaves httpx out of `sys.modules`. |
| F-11 and docs | CHANGELOG `[Unreleased]` and HTTP_EXPORTER.md claims were checked against the code: the 3-failure TLS streak and its resets (`tls_streak`), CONNECT handling, the 30 s body budget, the documented header-trickle limit, run-lifecycle health and release integration (`client.py`: `submit_measurement_health`, `release_run`, `submit_evaluation_failure`, `indicator=`), CI/CONTRIBUTING changes, the verifier's private-key check, and the dev-only `cryptography`. No inaccurate claim found. It says "no release date or version assigned, and nothing here is released or published". No invented date, version, owner or reviewer. The `[1.2.1] - 2026-09-08` entry is pre-existing. |

## 2. Preservation

Comparing sha256 and status against `rel_before*.txt` shows exactly these changes since the baseline:

- Modified: `CHANGELOG.md`, `CONTRIBUTING.md`, `.github/workflows/release.yml`, `docs/HTTP_EXPORTER.md`, `pyproject.toml` (the single `cryptography>=42` dev line plus its comment), `scripts/verify_release_artifacts.py`, `src/agent_reliability/adapters/http_event_sink.py`, `tests/unit/test_http_exporter_tls_real.py`.
- New: `tests/unit/test_http_exporter_release_regressions.py` and `docs/P28_SDK_EXPORTER_RELEASE_REVIEW.md`.
- Removed: all of `tests/fixtures/tls/*`.
- `tests/fixtures/p28/*` hashes are unchanged.
- Every other previously tracked/untracked file hash is identical. The porcelain status differs from the baseline only by the files listed above.

I did not change the repo. Running ruff and mypy there reused ignored cache dirs (`.mypy_cache`, `.ruff_cache`) and nothing else.

Other trees: the platform-integration tree and the E2E workspace show no files newer than the baseline. `agent-reliability-platform/docs/roadmap/P29/*` and `agent-reliability-p29/*` have newer files. That is P29 work, which I cannot attribute either way, and nothing in this P28 round refers to it.

## 3. Re-runs

- Full SDK suite: 868 passed on Python 3.11, 3.12 and 3.13 (about 10 s each).
- `ruff check` passes. `ruff format --check` reports 190 files already formatted. `mypy src` reports no issues in 46 source files.
- `verify_p28_fixtures.py --platform-root .../agent-reliability-platform-integration`: 4 hashes verified, platform comparison True.
- `node scripts/verify_p28_reference.mjs`: 76 canonical vectors and 74 acknowledgement vectors passed.
- The TLS and release-regression files (27 tests): 20 sequential runs all passed, and 18 runs in parallel loops (6 concurrent, 3 rounds) all passed.
- Packaging on a scratch copy: `python -m build` succeeded; `verify_release_artifacts.py` exited 0 (artifact contents, base wheel, sdist, HTTP extra, OTel extra and strict downstream mypy all ok). The wheel has 51 files and the sdist 209. No key-like filenames, and no PEM private-key content in either artifact.
- The E2E suite was not re-run (optional). I did not check the 80-passed claim on PostgreSQL 16/17.

## 4. Claims

No claim of commit, release, publication or approval, and no invented owner or reviewer, in CHANGELOG.md, CONTRIBUTING.md or HTTP_EXPORTER.md.

## New findings (all INFO)

- INFO-1: The async sink's proxy/CONNECT handling is fixed and correct (checked above), but the repo has no test for it. Only the sync sink is covered, and a regression confined to the async trace hook would go unnoticed. Optional: add a test like the scratch one.
- INFO-2: `_BODY_SECONDS` is only checked when a chunk arrives. A peer that sends nothing after the headers is bounded by the 30 s httpx read timeout, so there is no gap, and the docs describe it correctly.

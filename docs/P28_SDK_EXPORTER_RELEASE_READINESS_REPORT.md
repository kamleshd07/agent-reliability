# P28 SDK exporter - release-readiness report (2026-10-16)

Status: **`P28_SDK_EXPORTER_RELEASE_CANDIDATE_READY_WITH_EXTERNAL_GATES`**

This means the locally actionable technical work is complete. It is **not** a commit,
release or publication authorization, and it does not claim any approval. Nothing was
committed, pushed, merged, published or deployed. Author: Claude Code (SDK implementation
owner). Reviewers and verifiers were fresh subagent contexts (technical reviews only; they
are not the governance approver and no human reviewer or owner is named anywhere).

> **Later update (same day):** after this report, the sdist now excludes `CLAUDE.md`, `AGENTS.md`
> and `docs/P<nn>_*` (owner decision F-9 still PENDING), idle worker cost was reduced (F-10), the
> suite is 870 tests, and a stability-status section was added to `HTTP_EXPORTER.md`. Current
> numbers and the consolidated gate matrix are in `P28_P29_RELEASE_GATE_CONSOLIDATION.md`; the
> findings and gates below are otherwise unchanged and no approval has been recorded.

## 1. Repository and working-tree state

SDK `<workspace>/agent-reliability`, branch `main` @ `7aa6883` (the
`1.2.1` release commit), `origin/main` unmodified. **Everything below is uncommitted.**

| Class | Files |
|---|---|
| Modified (13) | `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `CHANGELOG.md`, `CONTRIBUTING.md`, `README.md`, `docs/ARCHITECTURE.md`, `pyproject.toml`, `scripts/verify_release_artifacts.py`, `src/agent_reliability/adapters/event_sinks.py`, `src/agent_reliability/ports/event_sink.py`, `src/agent_reliability/sdk/client.py`, `src/agent_reliability/sdk/context.py`, `tests/compat/test_public_api_1_1.py` |
| New source | `src/agent_reliability/adapters/{http_event_sink,_http_delivery,_http_protocol}.py` |
| New tests | `tests/unit/test_http_exporter.py`, `test_http_exporter_review_regressions.py`, `test_http_exporter_tls_real.py` (19), `test_http_exporter_release_regressions.py` (9), `tests/contract/test_p28_http_protocol.py`, `tests/fixtures/p28/*` (5 data-only fixtures) |
| New scripts/docs | `scripts/verify_p28_fixtures.py`, `scripts/verify_p28_reference.mjs`, `docs/HTTP_EXPORTER.md`, the `docs/P28_SDK_*` implementation, review, remediation, verification and this report, `AGENTS.md`, `CLAUDE.md` |

Changes made in THIS task relative to the state at its start (compared by sha256): the four
TLS private keys and the other static TLS fixtures were removed; `test_http_exporter_tls_real.py`
rewritten to generate disposable certificates; one `cryptography>=42` line added to the `dev`
extra in `pyproject.toml`; `scripts/verify_release_artifacts.py` (private-key guard);
`src/.../http_event_sink.py` (review fixes F-2, F-3 mitigation, F-8); `docs/HTTP_EXPORTER.md`;
`CHANGELOG.md`; `.github/workflows/release.yml` and `CONTRIBUTING.md` (install the `http`
extra); the new regression test file; the review and verification reports. No platform file,
E2E workspace file, P29 or P12.1 file was changed by this work (the P29 documents that appeared
in other trees during the session were not written by it).

## 2. Scope of the exporter change set

`HTTPEventSink` and `AsyncHTTPEventSink` (optional `agent-reliability[http]`, HTTPX), wire
schema v2 only with canonical digest preserving the v1 bytes, bounded queues with a closure
reserve, bounded retries with full jitter, sticky uncertainty, sink-wide 429/`Retry-After`
(RA-b), explicit pauses/resumes (auth, schema, deployment, endpoint), bounded `flush`/`close`,
immutable `DeliveryStatusSnapshot`, TLS/URL/proxy/redirect/cookie isolation, the optional
`HealthEvidenceSink` capability with composite fan-out and the run-finish integration in
`AgentReliability`, data-only P28 fixtures and their verification scripts. Governing documents:
`docs/HTTP_EXPORTER.md`, `docs/P28_SDK_EXPORTER_OWNER_DECISIONS_001.md` (owner decisions
relayed through ChatGPT, unsigned).

## 3. D-1 closure evidence

Fixed in the real SDK (`_failure()` walks both `__cause__` and `__context__`, bounded to 64
nodes, cycle-safe, deliberately ignores `__suppress_context__` because real httpcore sets it,
recognizes verification failure only for an attempt that had not sent). Evidence:
`docs/P28_SDK_D1_REMEDIATION_REPORT.md`, `P28_SDK_D1_INDEPENDENT_REVIEW.md`,
`P28_SDK_D1_TARGETED_VERIFICATION.md`; 19 real-handshake tests (untrusted CA, wrong hostname,
expired, self-signed; refused and TCP-close controls; exact third-failure pause; N-1; reset by
exchange and by `resume_endpoint()`; per-attempt `sent` reset; interleaved plain-TCP failure;
explicit proxy; async exporter incl. async proxy). Regression status in this task: all pass on
3.11/3.12/3.13; reverting the classifier to cause-only fails them; the E2E suite against the real
SDK passes (section 7). D-1 stays fixed.

## 4. Fixture-packaging resolution

Choice: **generate disposable certificates at test time**, store nothing. The sdist could not
simply exclude fixtures because source-tree tests need them, and static keys in the repository
would still trip secret scanners. `test_http_exporter_tls_real.py` builds a throwaway EC (P-256)
CA and leaf certificates (good, wrong hostname, expired, self-signed) in a private temp
directory with `cryptography` (a **development-only** dependency in the `dev` extra; no runtime
dependency added), removed at exit; the CA key is never written; validity windows are fixed (no
time bomb); certificates carry the extensions Python 3.13's strict verification requires; TLS
verification itself is unchanged and fully exercised. If `cryptography` is missing the module
skips (CI and the release workflow install the dev extra). `verify_release_artifacts.py` now
fails when either artifact contains key-like file names or PEM private-key blocks (its own marker
is assembled so it cannot match itself; negative tests with a planted key in a wheel and an sdist
were detected). Inspection (scratch build): wheel 51 files, sdist 209 files, **no key-like path,
no `fixtures/tls`, no private-key block in either**; wheel contains no `tests/`; the only HTTP
modules in the wheel are the three new ones. `verify_release_artifacts.py` exit 0.

## 5. Documentation and CHANGELOG

`docs/HTTP_EXPORTER.md` L2 paragraph now states the implemented streak semantics (scope: one
exporter bound to one endpoint; only certificate-verification failures of attempts that had not
sent; third consecutive failure pauses; any completed HTTP exchange or `resume_endpoint()`
resets; other network failures neither count nor reset; held, not dropped) and each claim was
checked against code and tests by two independent reviewers. Also added: the known limit that
header trickling can pin a synchronous worker (use the async exporter), the URL-logging
caution, and the missing-extra message. `CHANGELOG.md` has an `[Unreleased]` entry (no date, no
version, no publication status) following the file's Keep-a-Changelog conventions.

## 6. Independent review of the complete exporter, remediation, targeted verification

Review: `docs/P28_SDK_EXPORTER_RELEASE_REVIEW.md` (BLOCKER 0, HIGH 1, MEDIUM 4, LOW 6, INFO 4).
Verification: `docs/P28_SDK_EXPORTER_RELEASE_TARGETED_VERIFICATION.md` (VERIFIED; 2 INFO, one of
which, the missing async-proxy test, was then closed).

| ID | Sev | Disposition |
|---|---|---|
| F-1 release/CONTRIBUTING installed without the `http` extra (tag-triggered gates would fail at collection) | HIGH | **Fixed** (`.[dev,http,otel-test]`); verified no other job lacks it |
| F-2 explicit proxy: the CONNECT request marked the attempt "sent", so a TLS verification failure behind a proxy was never recognized and the endpoint never paused | MEDIUM | **Fixed** (`_is_proxy_connect`, sync + async); sync and async tests; neutralising it fails them |
| F-3 sync worker could be pinned by a trickling peer | MEDIUM | **Mitigated**: response body bounded to 30 s (and `iter_raw()` without chunk buffering); header trickling remains a documented limit (async exporter unaffected). A hard per-attempt deadline for the sync transport would be an architectural change: recorded as an optional improvement / owner decision |
| F-4 public surface classification (GA_CONTRACT: new API INTERNAL; `HealthEvidenceSink` not re-exported) | MEDIUM | **Owner decision, unchanged** |
| F-5 test gaps (naive timestamps, 64 KiB cap, userinfo URLs) | MEDIUM | **Fixed**, 4 mutants killed |
| F-6 L2 doc over-claimed test coverage | LOW | Fixed (reworded + interleaved-failure test) |
| F-7 httpx INFO logs full endpoint URL | LOW | Documented |
| F-8 bare ModuleNotFoundError without the extra | LOW | Fixed (actionable ImportError; core import proven httpx-free) |
| F-9 sdist ships `CLAUDE.md`, `AGENTS.md`, 9 internal `docs/P28_SDK_*` reports (no keys) | LOW | **Owner decision, unchanged** |
| F-10 idle polling about 2.4% of a core | LOW | Optional improvement, unchanged |
| F-11 CHANGELOG incomplete/odd "Fixed" entry | LOW | Fixed |
| INFO: key scan covers PEM/PKCS12-style names only; silent module skip without `cryptography`; Python 3.13 applies strict X.509 flags to a user CA bundle; `_client._transport` test seam | INFO | Recorded; no action |

## 7. Test matrix (final code)

| Check | Result |
|---|---|
| SDK full suite, Python 3.11.17 / 3.12.15 / 3.13.16 | **869 passed** each (868 earlier in the round + the async-proxy test) |
| Real-TLS + release-regression files (28 tests) | 36 of 36 sequential/parallel loop runs passed before the last test was added; the last test killed its mutant |
| `ruff check`, `ruff format --check`, `mypy src` (46 files) | clean |
| `verify_p28_fixtures.py` (vs integrated platform reference vectors) | 4 hashes verified, platform comparison True |
| Node reference check (Node v26.12.0) | 76 canonical byte/digest vectors, 74 acknowledgement vectors passed |
| Build wheel + sdist and `verify_release_artifacts.py` (scratch copy; before the last test-only addition) | built; exit 0; inspection in section 4 |
| P28 SDK-to-platform E2E against the REAL SDK, scratch copy of the workspace (variant `real`, no expected failures), PostgreSQL 16.15 and 17.11 | **80 passed** on each; run after the last production-code change |

Evidence for the E2E remains in `<workspace>/gentlity-p28-e2e` (untouched
by this task) and the integration-tree reports. Not run: Windows, PostgreSQL 18, system Python
variants outside 3.11-3.13.

## 8. Remaining compatibility and verification gaps

Windows (path/ssl behaviour of the temp-dir certificate generation and of the exporter);
PostgreSQL 18; platform-terminated TLS (the E2E TLS tests terminate TLS in a test fixture); a
real forward proxy (only a local CONNECT stub); connect-timeout scenarios (refusal is tested);
the platform rate limiter at its threshold; production-equivalent OIDC; Go/Java/other-language
conformance; load and sustained-duration behaviour; synchronous header-trickle bound (F-3).

## 9. Release-governance assessment (from the repository documents only)

1. **Satisfied by existing evidence:** exporter implemented and independently reviewed three
   times (original, D-1, this full-scope review) with all BLOCKER/HIGH closed; D-1 fixed; Python
   3.11-3.13 and PostgreSQL 16/17 local evidence; contract fixtures and cross-language vectors
   (Python, Node); wheel/sdist free of private keys; release-artifact checks.
2. **Completable locally (not done in this workflow):** platform-terminated TLS (uvicorn with
   TLS in the E2E workspace); a real forward-proxy scenario (needs a proxy tool); deterministic
   connect-timeout scenario; async header-trickle test; a hard per-attempt deadline for the sync
   transport (design decision first); a test for the PGP/JWK key-material scan limit; re-exporting
   `HealthEvidenceSink` (API decision).
3. **Owner decisions or external environments:** formal approval of D14 and the ADR-0023
   addendum (Appendix A.2): **recorded as unapproved**; ADR-0028 and the PC-2 decisions are
   recorded as relayed, unsigned owner decisions; **platform-first release evidence** (migration
   -> PC-2 -> PC-1 -> SDK, per-instance build evidence) is open; **no commit, release or
   publication authorization exists**; no human owner/reviewer/approver is assigned (Decision F
   roles `PENDING_ASSIGNMENT`/unassigned); F-4 public-surface classification and version/stability
   decision; F-9 what ships in the sdist; owner confirmation of the "consecutive" L2 reading;
   the pending platform policies (F-2 rate limiting, audit retention, verified identity in logs,
   production `dev_header` restriction, duplicate-header handling); Windows and PostgreSQL 18
   environments; GitHub Actions execution of the new CI/release workflow changes (never run).
4. **Optional future improvements:** idle-poll cost (F-10), richer secret scanning, native
   sync per-request deadline, header-trickle test, further proxy types.

The verified D-1 fix is not approval of the SDK release; the platform integration it depends on
is itself gated.

## 10. Next actions by decision category

| Category | Action |
|---|---|
| Owner (product/API) | Decide F-4 (stability class, version, whether to re-export) and F-9 (sdist contents); confirm the L2 "consecutive" wording; decide on a hard sync per-attempt deadline |
| Governance | Formal D14 / ADR-0023 A.2 decision; assign human owner and reviewer roles; platform-first release evidence; explicit commit/release authorization |
| Engineering (local) | Optional items in section 9.2; run GitHub Actions on a branch once authorized |
| Environment | Windows and PostgreSQL 18 verification; staging/TEST platform run |
| Release engineering | Choose the version and date only at release time (none assigned); review and normalize the large uncommitted change set into commits when authorized |

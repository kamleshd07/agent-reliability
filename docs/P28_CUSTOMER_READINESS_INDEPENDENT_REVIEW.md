# Independent Phase 0 / P28 review — 19 October 2026

Scope: read-only review of the isolated customer SDK/platform changes, built-distribution evidence, preservation manifest, and installed-wheel local PostgreSQL integration. The reviewer did not modify author files, authenticate to AWS/providers, or change resources. This report is review evidence, not release approval.

## Findings and resolution

1. **Medium, corrected:** the first quickstart implementation could report acknowledged delivery with an empty queue and zero acknowledgements. SDK failure isolation can suppress sink failures, so an empty queue alone is insufficient. The current sample requires a non-degraded run identity, healthy measurement state, exactly four committed/duplicate acknowledgements, an empty queue and no other dispositions. Seven focused regression cases cover committed and duplicate success, empty/partial acknowledgements, pending queue, permanent failure and a rejected sink with a synthetic secret. Reviewer independently ran these tests: **7 passed**. No secret was printed in the rejected-sink case.
2. **Evidence harness issue, corrected and reverified:** the first full integration run reports **77 passed, 1 failed, 2 deselected**. Its startup scenario hardcodes the former integration worktree name, despite the child process correctly importing the fresh customer-platform worktree. The external harness copy now asserts that the import resolves beneath `E2E_PLATFORM_ROOT`. Its targeted real-entrypoint run passed (1/1); the original failed evidence remains in `e2e.log` and the corrected run is recorded separately in `startup-e2e.log`.
3. **Low, editorial:** initial quickstart/release notes contained missing spaces around version numbers and malformed `-401` troubleshooting list markers. The author corrected the customer-facing quickstart spacing and troubleshooting list markers.

## Independent evidence checks

- Preservation manifest: **425 regular original/copy file pairs** match their recorded SHA256 values; **15 absent/nonregular entries** remain nonfiles, **zero mismatches** across all 440 entries. Original evidence was read, not altered.
- Built wheel `agent_reliability-1.2.1-py3-none-any.whl`: SHA256 `fd5985c1e1bce2837ea3d68013300098a793cf943871ca6d46eb74b4ccb4e5d8`. All **73 package files** match both the pinned SDK source and installed `site-packages` bytes. This verifies the local baseline artifact, not a future 1.3 artifact.
- Recorded baseline unit run: **1648 passed, 1 skipped**; static lint and mypy logs pass. Existing unit results alone do not establish end-to-end readiness.
- Artifact verification log covers wheel/sdist metadata and imports, base/offline examples, HTTP-extra mocked delivery, OTel extra/example and downstream strict mypy. It must remain distinguished from the real PostgreSQL scenarios.
- Real PostgreSQL customer-workflow scenario: **1 passed**, with two actual SDK runs / eight persisted events / two evaluations, pass1/fail1, reliability0.5, healthy measurement and SLO `breached` at target0.99. It asserts a foreign tenant receives404 for the SLO and a machine credential cannot use the human evidence read path. This is meaningful query evidence rather than seed-derived success. The final rerun in `query-e2e.log` passed after the final health assertion edit; file modification times independently confirm this ordering.
- Existing full E2E delivery scenario compares captured serialized SDK event IDs and canonical digests with PostgreSQL receipt rows and checks that requests use machine bearer authentication without tenant headers or cookies. Retry, replay, TLS, tenant/auth and concurrency scenarios are present in the reused harness.

## Scope/security/release assessment

The example transmits synthetic run/evaluation/health metadata and no prompts, responses, tool arguments or model credentials. Credentials are read from environment callbacks and the sample prints only fixed messages. Local loopback HTTP is explicitly bounded; external HTTPS requires verification. Public guide separates machine ingest from human read/SLO permissions, idempotent event replay from a fresh run, and local admission from durable acknowledgement.

The execution plan preserves approved roadmap authority and existing milestone IDs, labels operational-loop/P30 extensions proposed, and avoids broad architecture work. P29 remains Experimental and uncalibrated. Current main still reports1.2.1; it is explicitly **not** a1.3 candidate. API classification, release roles/version/artifact selection, experimental-package scope, final artifact rerun and release approval remain open. D14 stays OPEN / Phase B NO-GO. No merge, PyPI publication, hosted validation or production readiness follows from this review.

## Final evidence and disposition

Final full SDK tests: Python3.11,3.12 and3.13 each **1655 passed,1 skipped**, in `sdk-tests-final-3.*.log`. Final lint, format and source mypy passed. Final artifact install verification passed. Python canonical-contract fixture comparison against platform is now enabled and passing (`platform comparison: True`); Node canonical/acknowledgement reference vectors also passed. Startup targeted rerun **1 passed**, final-byte reliability/SLO customer workflow **1 passed**. Startup and query cleanup manifests both record verified ownership, stopped PostgreSQL and removal of the owned disposable directory.

**No remaining review blocker for the scoped local Phase0/P28-readiness documentation/example PRs.** No authentication or platform product code changes were needed. The reviewer does not treat the first integration run as fully passing: it remains 77passed/1failed/2deselected, with the single harness provenance assertion corrected and targeted-reverified separately. Two workload-measurement cases were deliberately deselected; no performance or capacity conclusion is supported.

SDK1.3 remains unreleased and not ready for publication until the explicit release gates above are resolved and the final selected artifact is rebuilt/revalidated. This scoped local review does not close D14, authorize PhaseB, authorize a real-provider evaluation pilot, or approve hosted/customer release.

## Final expanded evidence addendum

The final complete integration rerun now reports **79 passed, 2 measurement cases deselected, zero failures** (`final-e2e.log`/XML; exitcode0). This supersedes the intermediate startup-only revalidation as the strongest acceptance run while preserving the original failed run. `final-cleanup.json` confirms owner verified, PostgreSQL stopped and owned directory removed. Runtime wheel hash is unchanged; the final sdist SHA256 is `d6e0405d56c7e19cc0ee1714d543da9d2118d82c2951e449451a3899c7f08262`.

The earlier full-suite skip is specifically optional Experimental judge validation against platform-v2 models when `P29_PLATFORM_ROOT`/`P29_PLATFORM_PYTHON` are unset. It is not an exporter test and not a historical-manifest check. Explicitly enabled local validation passed **24 wire tests, zero skips** (`sdk-cross-platform-p29.log`), without provider/model calls. The subsequent fully enabled Python3.12 and3.13 suites each passed **1656 tests, zero skips**.

The fully enabled Python3.11 run exposed a pre-existing probabilistic unit-test defect: **1655 passed, 1 failed** (`sdk-tests-complete-3.11.log`). `test_ids_are_not_sequential` rejects two random UUIDv4 identifiers whenever the first ends0 and second ends1, which occurs with probability1/256 for valid independent identifiers. Both recorded identifiers are validv4. This is not evidence of an exporter defect, but the failure must remain disclosed and must not be represented as an all-green complete3.11 run. Reviewer notified author; resolution/additional evidence pending. No tests should be weakened or silently retried to hide this failure.

The frozen existing `HTTP_EXPORTER.md` remains unchanged; a proposed prose edit was rejected by its hash guard and restored. New guidance stays in the new quickstart. No frozen fixture, baseline hash or production code was weakened.


## UUID test disposition

A separate isolated test-only correction was independently reviewed in `UUID_TEST_REVIEW.md`: it replaces the invalid suffix heuristic with deterministic supplied valid UUIDv4 values and retains the existing1000-ID uniqueness test. Reviewer targeted19/19 and author separate-branch full1649/1649 passed with no skips (that branch excludes the seven new P28 sample tests). No runtime change, no test-contract weakening, no fixture/hash edits, and no merge occurred. The original3.11 failure remains preserved and disclosed. The readiness report now accurately records both expanded green3.12/3.13 results and the3.11 defect. No remaining review blocker for either separately scoped PR; SDK1.3 release gates remain open.

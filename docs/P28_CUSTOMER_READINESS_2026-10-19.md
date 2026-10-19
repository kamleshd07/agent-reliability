# P28 local customer-workflow readiness — 19 October 2026

Scope: implementation and evidence for the current merged SDK exporter, a runnable synthetic quickstart, release/troubleshooting documentation, and an installed-wheel round trip to merged platform/PostgreSQL. No SDK transport/protocol, authentication or platform ingestion implementation was changed. Already merged P28/P29 work was not recreated. This is not an SDK1.3 release approval.

## Exact baseline and artifacts

SDK remote main `d375fde8b5c42ab255b3e19c159b0e8fb9100b22`; platform remote main `8fb71db3cb116a93234d7a1157b46528b28e6cdd`. Latest respective main workflows39048878073 and39128890439 were successful. Live branch protection is present on both with the documented required checks, no admin enforcement; this resolves the audit's formerly offline protection conflict. No protection setting changed.

Built version remains1.2.1 (unreleased main development contents, not the published1.2.1 contents), includes Experimental judge. The package wheel has SHA256 `fd5985c1e1bce2837ea3d68013300098a793cf943871ca6d46eb74b4ccb4e5d8`; final sdist SHA256 `d6e0405d56c7e19cc0ee1714d543da9d2118d82c2951e449451a3899c7f08262`. Built from final source using the repository backend, installed into a new isolated environment with `[http]`. The verifier separately installed base, HTTP, OTel, sdist and typing environments. No tag/version bump or publication occurred; do not distribute these development artifacts as1.3.

## Implemented customer guidance

`examples/platform_quickstart.py` emits only a synthetic task outcome. Environment-held credentials never appear in arguments/output. Successful exit requires a real run id, healthy run evidence, exactly four committed/duplicate records, empty queue and no unsuccessful dispositions. Seven negative/positive tests exercise complete/mixed/rejected/empty/partial/queued/failure cases using the real SDK's failure isolation. The independent reviewer identified the empty-snapshot false-success risk in an earlier revision; it is fixed and independently rechecked.

`docs/PLATFORM_QUICKSTART.md` explains built-wheel installation, registry/least-privilege machine credential prerequisites, delivery, human read-back/reliability/SLO checks, same-event replay versus a new run, and bounded error/TLS/backpressure behavior. The new quickstart explicitly distinguishes the unreleased source from the published package; the frozen existing exporter guide remains byte-identical. `docs/SDK_1_3_RELEASE_NOTES_DRAFT.md` records proposed scope, limitations and actual release gates. Bootstrap still requires an authorized platform administrator and existing APIs/runbook; this work does not invent a hosted onboarding service.

## Quality evidence

- Initial SDK Python3.11/3.12/3.13 runs:1,655 passed and1 skipped on each interpreter. The skip is the optional Experimental judge/platform-model validation because its environment variables were unset, not a transport/TLS/tenant test. A separate run with explicit local platform variables passed all24 wire tests, including that scenario. Existing deterministic, privacy, queue, retry, timeout, real TLS and adversarial fixtures retained.
- Ruff lint/format and strict source mypy pass. Node reference:76 canonical/digest and74 acknowledgement vectors pass. Four vendored fixture hashes match the pinned platform fixture set.
- Wheel/sdist verifier passes dependency-free core, HTTP-extra mocked delivery, OTel-extra example and installed-wheel downstream strict typing checks. The live round trip imports SDK from site-packages, not source; independent reviewer compared73 installed package files with source and wheel bytes.
- Platform non-integration suite:1,361 passed,559 integration tests deselected,9 existing warnings. Full platform integration/container/frontend/security matrices were not rerun locally for this documentation/example-only scope; their pinned main CI was green. Real PostgreSQL contract behavior was exercised separately below.

## Real local integration

PostgreSQL17.11 initialized in newly owned temporary directories, migrations through0021, loopback networking, real HTTP/Uvicorn and machine credentials. Human read checks use a synthetic injected RS256 key, not real Cognito or hosted proxy/TLS; this does not close D14. No benchmark measurement tests or provider/model calls run.

The first reused E2E run passed77 tests and failed one legacy hard-coded worktree-path assertion;2 measurement cases were deliberately deselected. Original failing log retained. The external harness copy now checks configured platform-root provenance and installed SDK location. Targeted native-entrypoint test passed after that correction. No application validation was weakened, and original harness/evidence were unchanged.

The new installed-example scenario creates2runs/8durable events/2evaluations. Authenticated reliability API reports pass1,fail1,total2,reliability0.5; deployment SLO target0.99 is breached using the same healthy persisted measurement. Foreign tenant SLO read returns404, foreign storage is empty and machine credentials cannot read evidence. Canonical digests/replay/conflicts/authentication/recovery/privacy/concurrency are also checked by the existing integration suite. Each run stops its owned PostgreSQL server and removes only the marker-owned temporary directory, preserving logs/results.

Final clean E2E: **79 passed, 2 measurement tests deselected**, zero failures, in105.45seconds. This includes the corrected native-entrypoint provenance test and final installed-example reliability/SLO scenario. Final cleanup confirms owned PostgreSQL stopped and its directory removed. The reviewer rechecks these final artifacts separately.

## Remaining release gates

1. Owner selects actual SDK1.3 version/commit/content and resolves P28-only artifact versus the Experimental judge already on main; do not silently strip or promote it. Rebuild and reverify selected release contents.
2. Exporter is still INTERNAL under `GA_CONTRACT.md`; any customer-supported stability promise needs explicit owner/API-policy decision.
3. Assign named release, independent review/security and rollback roles; an agent review is not a human approver assignment.
4. Authorize shared TEST/hosted deployment validation separately, with actual environment commit/migration/proxy/auth evidence. No production-readiness/capacity claim follows from this local run.
5. D14 remains OPEN and PhaseB NO-GO. No PhaseA Cognito changes, D14PhaseB execution, PyPI publication, merge or AWS action is authorized here. P29 real-model calibration/safeguards and later operational/P30 slices are separate gated work.

External evidence directory: `gentlity-customer-ready-evidence-2026-10-19` adjacent to the isolated worktrees, containing verified preservation manifest/copies, artifact hashes, commands/scripts, full test logs/JUnit, database cleanup evidence and the independent reviewer-authored report. No credential is needed to inspect sanitized acceptance results.

A later attempted prose edit to the frozen exporter guide correctly failed its documented hash guard. The edit was discarded; no guard, fixture or baseline hash was weakened. New guidance is delivered as a separate document.

## Expanded verification and existing test defect

With optional model-test environment variables configured, final Python3.12 and3.13 runs each pass1,656 tests without skips. Python3.11 passes1,655 and fails one pre-existing UUID test: it rejects independently random valid UUIDs whenever their suffixes are0then1. The failing values are valid v4 and this is unrelated to exporter behavior. The complete failed log is retained. A separate test-only branch/PR replaces that heuristic with deterministic UUID-provider delegation and format checks, preserving the existing1000UUID uniqueness check. It is not folded into this P28 PR or silently retried to declare all gates green. SDK1.3 also requires this quality defect to be resolved. No runtime UUID behavior changed.

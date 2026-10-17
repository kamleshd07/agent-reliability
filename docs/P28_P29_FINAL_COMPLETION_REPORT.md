# P28 / P29 final completion report (2026-10-17)

Final status (after the independent verification in section 12):

| Workstream | Status |
|---|---|
| P28 | **`TECHNICALLY_VERIFIED_WITH_EXTERNAL_GATES`** |
| P29 | **`SDK_V1_TECHNICALLY_VERIFIED_WITH_PILOT_GATES`** |
| Combined | **`P28_P29_FINAL_CANDIDATE_VERIFIED_WITH_EXTERNAL_GATES`** |

Technical completion is not production release and not a customer-pilot authorization. Nothing
was committed, pushed, merged, deployed, published, released or piloted. Subagent reviewers are
technical checks, not the governance approver; no human owner, reviewer or approver is named in
any record and none was assigned or invented.

## 1. Executive summary

* The integrated, frozen candidate lives in two new isolated workspaces: SDK
  `<workspace>/agent-reliability-final` (P28 exporter + P29 judge, copied
  from the reconciled tree) and platform
  `<workspace>/agent-reliability-platform-final` (the verified PC-1 + PC-2
  integration, file-level copy). All original worktrees and the active E2E workspace were left
  unchanged; the P28-only SDK repository was updated only with the three owner decisions.
* The three owner decisions (F-4 INTERNAL, F-9 sdist exclusions, L2 refinements) are recorded and
  implemented. P29 packaging now also excludes internal P29 reports and local-path evidence, and
  the release guard rejects internal files, private keys and local developer paths.
* The synchronous header-trickle limitation stays documented and classified (no transport
  redesign); the idle-polling fix is verified.
* P29 remaining locally actionable work was completed against the real integrated platform
  (P3 summary counts and P4 SLO error-budget values equal hand-computed values), plus platform-
  terminated TLS evidence. SG-1..SG-6 remain NOT SATISFIED; checklists, templates, roles and an
  evidence script were prepared.
* Platform: no behaviour or policy was changed. Policy-neutral work: file-mode/line-ending
  normalization and four characterization tests that pin current behaviour of open policies.
* Everything that is a decision (D14, ADR-0023 A.2, F-2, audit retention, log identity,
  `dev_header`, duplicate headers, release, roles, SG sign-offs, pilot) is in one packet
  (section 16).

## 2. Baselines and provenance (captured before any change; manifests of sha256 per file)

| Tree | Branch / HEAD | Uncommitted entries at start |
|---|---|---|
| P28 SDK `.../agent-reliability` | main @ `7aa6883` | 13 modified, 31 untracked |
| P29 SDK `.../agent-reliability-p29` | p29-sdk-v1-local @ `7aa6883` | 17 modified, 101 untracked (unchanged by this task) |
| Reconciled SDK `.../agent-reliability-p29-reconciled` | p29-sdk-v1-local @ `7aa6883` | 19 modified, 107 untracked (unchanged; source of the final copy) |
| Platform integration `.../agent-reliability-platform-integration` | integration/p28-pc1-pc2 @ `d606293` | 24 modified, 118 untracked (unchanged) |
| Platform (P29 design docs) `.../agent-reliability-platform` | feat/p20b-execution-resource-budgets @ `d606293` | 28 modified, 146 untracked (read only) |
| P28 E2E workspace `.../gentlity-p28-e2e` | not a Git repository (74 files) | unchanged; new E2E tests ran in scratch copies |
| **New** SDK final `.../agent-reliability-final` | copy of reconciled (branch name carried over; no commit) | candidate |
| **New** platform final `.../agent-reliability-platform-final` | file copy (631 files, no `.git`), identical to the integration worktree at creation (file-level diff empty) | candidate |

Provenance for the SDK final workspace: `rsync -a` of the reconciled tree (identical to the
original P29 workspace plus the verified P28 corrections; see its `docs/P29_P28_RECONCILIATION.md`,
section 5 updated). Frozen candidate manifests: `<scratch>`
and `freeze_platform_final.txt` (section 12). Newer verified results were never overridden by older
reports: the 2026-10-16 consolidation and verification reports were read and are superseded only
where this report says so.

## 3. Owner decisions recorded

`docs/P28_SDK_EXPORTER_OWNER_DECISIONS_002.md` (provenance: the owner's explicit statement in the
user's instruction of 2026-10-17; signature none; approver identity and time of day not recorded):
F-4 INTERNAL, no Beta class, documented entry points identified; F-9 sdist excludes `CLAUDE.md`,
`AGENTS.md`, `docs/P28_*`; L2 refinements (sent-attempt rule, proxy CONNECT, per-exporter endpoint
scope; threshold 3, resets and neutrality unchanged). Nothing else was approved.

## 4. P28 platform completion

Work (in `agent-reliability-platform-final`): (a) the seven CRLF files (PC-2 migration 0019 and six
test/support files) were normalized to LF and 89 non-script files lost their executable bit
(review finding R-08); (b) `tests/unit/api/test_p28_policy_characterization.py` (4 tests) pins the
current behaviour of open policies: duplicate Authorization / X-Organization-ID headers (first
value wins), request logs carrying client-asserted rather than verified identity, and production
refusing `dev_header`. No source code behaviour changed; the approved wire contract is untouched.

Reviewed locally actionable areas with no new defect found: machine authentication and tenant
authority, schema-v2 ingestion, digest/replay/conflict (covered by the PC-1/PC-2 suites and the
E2E), request bounds and timestamp validation, transactional persistence and recovery. Left
untouched on purpose: the strict xfail for legacy +/-infinity pagination (L-2) and execution-step
timestamp hardening (M-1) (outside the approved scope); policy-dependent items (rate limiting,
audit retention, verified-identity logging, duplicate headers, `dev_header` policy) are open
decisions (section 16): no change was made under an assumed approval.

Results: ruff/format/mypy clean (138 source files); unit + property **1,164 passed**; PostgreSQL
integration **509 passed, 3 slow deselected, 1 xfailed** on 16.15 and **512 passed, 1 xfailed** on
17.11 (whole directory, slow included).

## 5. P28 exporter completion

The integrated SDK contains: the D-1 classification fix (real-TLS verified), sync and async
exporters, the proxy CONNECT correction, bounded queues/retries, endpoint pause/resume, runtime
generation of disposable TLS certificates (dev-only `cryptography`, nothing stored), the private-key
scanner, the approved exclusions, current documentation and CHANGELOG, Python 3.11-3.13. The
synchronous header-trickle limitation is retained as documented (a body read is bounded to 30 s;
headers trickling can occupy one worker; the async exporter is unaffected) and classified
DEFERRED_WITH_RATIONALE: eliminating it needs a transport-level cancel, i.e. a redesign, which was
not justified. No claim of protection from slow-response attacks is made. The idle-polling
optimization was re-verified (idle cost about 0.4% of a core; regression test).

P28-only artifact (the original SDK repository, no P29 content): 904 tests pass on Python
3.11.17/3.12.15/3.13.16; ruff/format/mypy clean; sdist 199 files, wheel 51, no internal files, no
keys, no judge files; `verify_release_artifacts.py` exit 0.

## 6. P29 SDK completion

Scope unchanged: `agent_reliability.experimental.judge`, customer-supplied providers, raw content
stays customer-side, no new wire fields, no managed judge, no new core dependency, existing
rubric/sampling/budget/result contracts, indicator identity grammar and gate/health semantics.
ADR-0010 is unique, records the owner-approved (2026-10-16, unsigned) G-C amendment of ADR-0007
decision 9 and keeps its provisional number note; G-C was not widened. Completed in this task:
S09 (judge wire bodies validated against the real platform models: 24 tests in
`test_p29_wire_conformance.py`, now passing with the platform environment variables), S11
(local real-platform evidence below), S12 (safeguards record, templates and evidence script;
packaging). Distinctions:

| Level | State |
|---|---|
| Implemented | yes (author-run; independently sampled earlier) |
| Mocked-provider integration | yes (scripted providers, deterministic) |
| Real platform integration | yes, local and disposable: 84 E2E tests on PostgreSQL 16 and 17, including the judge flows below |
| Real-model evaluation | **not performed** (no model or charge authorized) |
| Calibration | **not performed**; no accuracy claim exists |
| Pilot operation | **not started** |
| Release readiness | **no** |

Live judge evidence (scripted providers, canary strings in all judged content, machine auth, OIDC
mode): schema-v2 envelopes only, exactly four payload kinds, 201 acknowledgements, producer
identity and deployment binding correct, PASS/FAIL per indicator, provider failure as
`evaluation_execution_failure` evidence with run health `unavailable`, no canary on the wire or in
the four evidence tables (about 50 other tables not scanned; a positive control plants a canary in
`evaluation_id` and the scan then finds it). P3 summary per judge indicator equals hand-computed:
pass 1, fail 1, unknown 0, execution failures 1, determinate 2, total 3, reliability 0.5,
healthy 2, unavailable 1. P4 SLO (target 0.9) equals hand-computed: breached, reliability delta
-0.4, allowed failures 0.2, observed 1, remaining -0.8, consumed 5, remaining fraction -4, burn
rate 5; `measurement_state` `unavailable` (the documented SG-2 semantic). Not exercised: P6
coverage and a persisted P7 decision (S11-AC03), pilot budgets (S11-AC10), benchmark (S12-AC01,
needs a human-authorised measurement), sampling/budget limits against the platform (covered by
SDK-side tests only).

## 7. P29 safeguards SG-1..SG-6

`docs/P29_PILOT_SAFEGUARDS.md`: requirements quoted or condensed (meaning preserved) from the owner record; SDK enforcement
and evidence per safeguard (reproducible: `python scripts/p29_sg_evidence.py`, all mapped tests
pass); remaining pilot condition; responsible role (described, unassigned); report templates A-F.
**All six are NOT SATISFIED**: each is defined by a pilot configuration, report or customer
wiring that does not exist. SG-2, SG-4 and SG-6 are process gates and are not marked on the basis
of documentation. No customer pilot was initiated.

## 8. Packaging and distribution inspection (scratch builds of the frozen trees)

| Artifact | Result |
|---|---|
| P28-only SDK sdist / wheel | 199 / 51 files; internal files and keys absent; no judge files |
| Final SDK sdist / wheel | 268 / 77 files (26 judge files in the wheel incl. 5 rubrics); `CLAUDE.md`, `AGENTS.md`, `docs/P28_*`, internal P29 reports (acceptance matrix, implementation log, independent review, remediation report, targeted verification, test evidence, workspace baselines, reconciliation) and `docs/evidence/` absent; `docs/P29_PILOT_RUNBOOK.md` and `docs/P29_PILOT_SAFEGUARDS.md` kept |
| Guards (`verify_release_artifacts.py`) | fail on: private-key files and PEM/PGP/OpenSSH key blocks; internal instruction/report files anywhere in the sdist (nested names included), any `docs/P<nn>_*` not on the two-document public allowlist, `docs/evidence/`, `docs/`, `tests/` or agent-instruction files in the wheel; embedded local developer paths (`/Users/`, `/private/tmp/`, `/var/folders/`, `/home/`, Windows user paths plain, JSON-escaped, any case). 34 planted-case tests in `tests/unit/test_release_artifact_guards.py` (both trees) |
| Source-checkout tests | functional; tests that read the excluded implementation log skip when it is absent |

## 9. Python compatibility matrix

| Tree | 3.11.17 | 3.12.15 | 3.13.16 |
|---|---|---|---|
| P28-only SDK | 904 passed | 904 passed | 904 passed |
| Final SDK | 1,598 passed, 1 skipped | 1,598 passed, 1 skipped | 1,598 passed, 1 skipped |

The one skip is the platform-model validation, which is NOT_EXERCISED in a default run and
passes (24 tests in its file) when `P29_PLATFORM_ROOT`/`P29_PLATFORM_PYTHON` are set (run against
the final platform). ruff, format and mypy are clean on both trees (46 and 65 source files).
Fixture-drift: 4 hashes verified, platform comparison True; Node v26.12.0 reference check: 76
canonical + 74 acknowledgement vectors; platform Node conformance was verified earlier on the same
platform code (not re-run after the LF/mode normalization).

## 10. PostgreSQL end-to-end (final SDK + final platform, OIDC mode, disposable local servers)

**84 passed on PostgreSQL 16.15 and 84 on 17.11** (Python 3.11): the 80 SDK-to-platform scenarios
(authentication, scopes, tenants, replay, conflicts, lost acknowledgements, 429, timeouts, queue
saturation, shutdown, concurrency, redirects, real TLS fixture, proxy CONNECT stub, startup through
the platform's own entry point), 2 judge scenarios, 2 platform-terminated TLS scenarios (trusted CA
delivers; untrusted CA pauses the endpoint and writes nothing). The new tests ran from a scratch
copy of the E2E workspace; copies are kept in `docs/evidence/` of the final SDK. Measurements in
earlier reports are development-machine values, not capacity.

## 11. Privacy and security findings

No raw judged content reaches any exporter body, report, diagnostic or the platform tables scanned;
no credential material in logs or snapshots; TLS verification never weakened; redirects refused;
plaintext only to literal loopback. Open, by design or decision: header trickling (synchronous
exporter), duplicate-header handling, unverified identity in request logs, unbounded audit growth,
pre-authentication rate limiting (all in section 16).

## 12. Independent final verification

One fresh read-only reviewer examined the frozen candidate
(`docs/P28_P29_FINAL_INDEPENDENT_REVIEW.md`, authored by the reviewer): **0 BLOCKER, 0 HIGH, 0
MEDIUM, 6 LOW, 6 INFORMATIONAL; verdict NO BLOCKING FINDINGS.** It verified both frozen trees
against their manifests (296 and 632 files), the original trees unchanged, platform-final equal
to the verified integration worktree except the 7 LF-normalized files, 89 mode changes and the
new characterization test, the three exporter modules byte-identical between the P28-only and
final SDKs, and it re-ran the suites (including 84 E2E tests on PostgreSQL 16 and 17, and the
sdists extracted and tested). 18 mutants: all but four were killed by repository tests; three (the
guard mutants) were detected only by its own harness and are now covered by the planted-case
tests, and one survivor is equivalent.

| ID | Finding | Disposition |
|---|---|---|
| L-1 | pre-existing random-UUID test in `tests/unit/adapters/test_adapters.py` fails about 1 in 256 runs | recorded, not changed (outside scope; passes on re-run) |
| L-2 | platform migration safety test timing assertion (`1.5 <= elapsed`) failed once under concurrent load | recorded (timing-sensitive, passes solo and in the quiet full run) |
| L-3 | release guard gaps (PGP block, case/JSON-escaped Windows paths, `/var/folders`, nested instruction files, new `docs/P29_*` names, wheel contents) and no in-repo test | **fixed**: guards extended; 34 planted-case tests in both trees |
| L-4 | vacuous assertion in the characterization test | **fixed** (removed) |
| L-5 | CHANGELOG lacked a P29 entry and understated the guards | **fixed** |
| L-6 | SG requirements described as quoted but partly condensed | **fixed** (wording) |
| I-1..I-6 | README wording about the judge; consolidation doc body still showing F-4/F-9 pending (superseded by its top note and decision record 002); extra sdist exclusions beyond F-9 are an owner decision (packet item 11); machine-auth row lock note; older E2E measurement files; judge accepts a json-fenced reply | I-1 fixed; others recorded; no approval claimed |

After remediation the suites were re-run: final SDK 1,598 passed + 1 skipped and P28-only SDK 904
passed on Python 3.11, 3.12 and 3.13; ruff, format and mypy clean on both; platform 1,164
unit/property passed; both builds pass `verify_release_artifacts.py`. No exporter or platform
runtime code changed after the E2E runs, so the E2E results (84 per PostgreSQL version) were not
repeated. **Environment note:** mid-way through this work another Claude Code process deleted the
scratch area under `<tmp>/claude-501` (virtual environments, scratch copies, manifests). The
repositories were unaffected (checked by status counts). Environments were rebuilt under
`<envs>`, manifests regenerated in
`<workspace>/gentlity-p28-p29-final-evidence/` (`freeze2_*`, `state_*`), and
the post-remediation checks recorded there. The reviewer's integrity checks were made against
the original manifests before that deletion.

**Targeted verification of the remediation** (a separate fresh context;
`docs/P28_P29_FINAL_TARGETED_VERIFICATION.md`, authored by the verifier): **VERIFIED**, no finding of
LOW or higher, four INFO items. It confirmed each fix against the files; 21 planted cases
caught by the real guards in both trees (key blocks incl. PGP/OpenSSH, key file names, Unix,
macOS-temp, `/var/folders`, `/home` and three Windows path forms, nested instruction files,
`docs/evidence/`, new `docs/P<nn>_*` names, wheel `docs/`/`tests/` members; the two allowlisted
documents correctly allowed); the four named guard mutants killed by the new in-repo tests;
exporter modules byte-identical between the two SDK trees; no `src/` file changed since the
review; manifests unchanged except for P28-owned entries. Its INFO items were then fixed: the
mutant-count wording, "quoted" wording in section 7, and two missing planted cases
(`/private/tmp/` and `/home/`; the guard tests went from 30 to 34 and all suites were re-run:
final SDK 1,598 passed + 1 skipped, P28-only 904 passed, on 3.11/3.12/3.13). The PostgreSQL and
E2E results were accepted from the review because no runtime code changed afterwards.



## 13. Unexecuted or unavailable checks

Not run, with the reason: PostgreSQL 18 (not installed); Windows (no environment); GitHub Actions
(nothing committed; the changed workflows never ran); production-equivalent OIDC (no identity
provider or deployment); real forward proxy (no proxy tool installed; only a local CONNECT stub);
connect-timeout scenario (attempted with a full-backlog loopback listener; connect() was not
delayed on this macOS, so it could not be reproduced: NOT_EXERCISED); real-model evaluation and
calibration (no model, charge or content authorization); P6/P7 gate decision with judge
indicators; benchmark and load tests; Go/Java conformance; SDK on other platforms.

## 14. Remaining governance gates

D14 and ADR-0023 Appendix A.2 (approval fields blank; implemented and verified under the owner's
unsigned instruction to implement); F-2, audit retention, verified-identity logging, production
`dev_header`, duplicate headers (open decisions); platform-first release evidence; commit and
merge authorization; CI results; release version and date; named release owner and reviewer; SDK
publication authorization; P29 SG-1..SG-6 and pilot authorization. All unchanged by this work.

## 15. Release and pilot readiness

* P28 platform: technically verified locally as uncommitted working-tree changes; not committed,
  not CI-validated, not deployed.
* P28 SDK exporter: release-candidate quality locally; blocked from release by the governance
  gates above, not by a known technical defect.
* P29: not pilot-ready (SG-1..SG-6), not released, no calibration, no real-model evidence.

## 16. Consolidated owner-decision packet

Recommended option first; security consequence in the last column. None of these is approved.

| # | Decision | Options | Consequence of the recommendation |
|---|---|---|---|
| 1 | D14 / ADR-0023 Appendix A.2 (evidence POST dual-mode authentication) | (a) approve as implemented and verified [recommended]; (b) approve with changes; (c) reject and keep human-only | Records the authority basis for a security-sensitive route; rejecting makes the SDK exporter non-functional in OIDC mode |
| 2 | F-2 pre-authentication rate limiting | (a) layered: bounded IP abuse protection, then machine auth, then per-credential/organization quotas [recommended]; (b) keep today's per-address limiter; (c) limit only at the edge | (a) stops invalid-bearer floods starving valid SDK traffic behind shared addresses but needs quota design; (b) leaves that starvation risk |
| 3 | Audit retention | (a) retention window with partition/archival job and legal hold [recommended]; (b) keep append-only indefinitely; (c) export then truncate | (a) bounds storage (about 3.9 GB/day at 100 events/s) while preserving forensics; (b) unbounded growth |
| 4 | Verified identity in request logs | (a) log verified organization/principal/credential id from the auth context and demote client-asserted headers [recommended]; (b) keep asserted headers | (a) makes audit trails trustworthy and prevents header-spoofed log entries |
| 5 | Production `dev_header` policy | (a) additionally refuse it in every non-local environment (TEST/staging) [recommended]; (b) keep production-only refusal | (a) removes the unauthenticated seam from shared environments |
| 6 | Duplicate Authorization / X-Organization-ID headers | (a) reject with 400 [recommended]; (b) keep first-wins; (c) last-wins | (a) removes proxy-append ambiguity about which credential is evaluated |
| 7 | Platform-first release evidence | accept per-instance build evidence that every instance serves PC-2 and PC-1 before any SDK release [documented requirement] | prevents an SDK sending v2 to a platform that cannot accept it |
| 8 | Commit, merge and CI authorization for both candidates | authorize commits of the two final trees after file-mode/line-ending normalization (done for the platform tree) | enables CI evidence |
| 9 | Release version/date; named release owner and reviewer; SDK publication authorization | owner to name; none exists | required before any publication |
| 10 | P29 SG-1..SG-6 sign-offs and pilot authorization | pilot owner assigns roles, runs the pilot, fills templates A-F | the P29-D09 approval does not cover pilot use until then |
| 11 | P29 sdist contents | keep as implemented (internal reports excluded, runbook and safeguards kept) or ship more | none security-relevant |
| 12 | Optional follow-ups | PostgreSQL 18, Windows, real forward proxy, connect-timeout, hard per-request deadline for the sync exporter | confidence only; header-trickle remains documented |

## 17. Dependency-ordered next steps

1. Owner records decisions 1-6 and 9 (and assigns roles). 2. Platform: commit the final tree (once
authorized), run GitHub Actions including `postgres-slow`, production-equivalent OIDC TEST,
deployment dry run. 3. Platform-first release evidence (decision 7). 4. SDK: commit candidate,
Actions on Python 3.11-3.13, exact-candidate build, E2E against the TEST platform; optional items
of decision 12. 5. Release authorization and publication (decision 9). 6. P29 as a separate track:
role assignment, SG evidence, calibration, pilot (decision 10).

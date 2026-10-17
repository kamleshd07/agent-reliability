# P28 / P29 release-gate consolidation (2026-10-16)

Status: **`P28_P29_CONSOLIDATION_READY_FOR_OWNER_DECISIONS`**

Nothing here is committed, pushed, merged, deployed, published or released, and no approval is
recorded that the repository records do not already contain. Reviewers and verifiers named below
were fresh subagent contexts (technical checks only); no human owner, reviewer or approver is
named in any repository record and none is assigned here.

> **Later update (2026-10-17):** owner decisions F-4 (INTERNAL classification, no Beta class), F-9
> (sdist exclusions) and the three L2 refinements are now recorded as owner-approved in
> `P28_SDK_EXPORTER_OWNER_DECISIONS_002.md` (unsigned; approver identity not recorded). Their rows
> below that say PENDING / READY_FOR_OWNER_DECISION are superseded by that record; everything
> else in this document is unchanged. See `P28_P29_FINAL_COMPLETION_REPORT.md`.

## 1. Repository states (recorded before any change in this task)

| Repository | Branch / HEAD | Uncommitted state |
|---|---|---|
| P28 SDK `<workspace>/agent-reliability` | `main` @ `7aa6883` (`1.2.1`) | 13 modified, 29 untracked |
| P29 SDK workspace `.../agent-reliability-p29` (separate clone) | `p29-sdk-v1-local` @ `7aa6883` | 17 modified, 101 untracked; **unchanged by this task** (sha256 manifest identical) |
| Platform integration `.../agent-reliability-platform-integration` | `integration/p28-pc1-pc2` @ `d606293` | combined PC-1 + PC-2, uncommitted; **unchanged** |
| Platform (P29 design/governance docs) `.../agent-reliability-platform/docs/roadmap/P29` | `feat/p20b-execution-resource-budgets` @ `d606293` | read only |
| New: reconciled P29 tree `.../agent-reliability-p29-reconciled` | copy of the P29 workspace + P28 corrections | created by this task, uncommitted |

Manifests (sha256 of every modified/untracked file) were taken before and after.

## 2. Owner decisions (prepared, not approved by this document)

Existing approval records are the only approvals recognised. "Recorded owner selection" below
means a statement in the repository that the owner decided something through ChatGPT; those
records say *Signature: none* and *approver identity: not recorded*.

### F-4: public API stability of the P28 HTTP exporter

* **Record found:** none.
* **Policy mismatch found:** `docs/GA_CONTRACT.md` has four classes (STABLE, EXTERNAL-EVOLVING,
  INTERNAL, EXPERIMENTAL) and **no "Beta" class**. Its rule that unlisted submodules are INTERNAL
  currently applies to `agent_reliability.adapters.http_event_sink`. "Beta" therefore maps onto the
  existing EXPERIMENTAL class ("explicitly named public functionality that may change in a minor
  release with release notes", `VERSIONING.md`); introducing a distinct "Beta" class would be a
  policy amendment, not a labelling choice.
* **Decision text for the owner (status: PENDING):** "The P28 HTTP evidence exporter
  (`HTTPEventSink`, `AsyncHTTPEventSink`, the delivery types and the optional `HealthEvidenceSink`
  capability) is public but classified EXPERIMENTAL under `GA_CONTRACT.md` (plain-language label:
  beta) for its first release. It may change in a minor release with CHANGELOG notes; the
  published wire contract (schema version 2, the acknowledgement) is governed by the platform
  contract and is not affected. Re-classification to STABLE requires a later explicit decision.
  Choose: (a) EXPERIMENTAL as above [recommended]; (b) amend `GA_CONTRACT.md` to add a Beta
  class; (c) STABLE; (d) leave INTERNAL." Whether `HealthEvidenceSink` is re-exported from
  `agent_reliability.ports` follows the same decision. No version number is proposed or chosen.
* **Done safely now:** `docs/HTTP_EXPORTER.md` has a "Stability status" section stating the
  factual current status (unclassified, hence INTERNAL under the current rules), the
  recommendation, the expectations (pin the SDK version, read the CHANGELOG) and that approval is
  pending. Versioning implication under the existing policy: new exporter API is a MINOR addition
  to 1.x (additive, no stable API changed); an EXPERIMENTAL label allows later minor-release
  changes; STABLE would freeze it for 1.x.

### F-9: source-distribution contents

* **Record found:** none.
* **Prepared and applied in the working tree (reversible, approval PENDING):**
  `[tool.hatch.build.targets.sdist] exclude = ["/CLAUDE.md", "/AGENTS.md", "/docs/P28_*"]`
  in `pyproject.toml`, plus an assertion in `scripts/verify_release_artifacts.py` that fails if
  those paths reappear. Removing the three lines and the assertion restores the previous contents.
* **Decision text (PENDING):** "The source distribution excludes agent-instruction files and
  internal milestone review/execution reports; public documentation, licence, changelog, README,
  security/contributing files and all packaging inputs stay. Choose: (a) as implemented
  [recommended]; (b) ship everything as before; (c) other list."
* **Verified (scratch builds):** sdist 212 -> 198 files (14 excluded); internal files absent; 42 public docs,
  LICENSE, README, CHANGELOG, SECURITY, CONTRIBUTING, pyproject and `HTTP_EXPORTER.md` present;
  wheel unchanged (51 files; no tests, no keys); `verify_release_artifacts.py` exit 0. No
  retained file references an excluded document (checked by grep over the built sdist; an earlier
  version of `HTTP_EXPORTER.md` did and was corrected). The pattern is deliberately limited to
  `docs/P28_*`: other milestones (P29) decide their own sdist contents; widening it to all
  `docs/P<nn>_*` would also remove P29 judge documents that the judge tests read.

### L2: "consecutive" TLS verification failures

* **Record found:** `docs/P28_SDK_EXPORTER_OWNER_DECISIONS_001.md`, "Follow-up owner selections,
  2026-10-16": the owner "separately approved the documented L2 proposal above, including N=3 and
  its TLS reset rule" (relayed through ChatGPT, unsigned). The proposal's item 2 states: N=3
  consecutive TLS **verification** failures close the endpoint gate; a verified TLS exchange resets
  the count; **other network failures neither advance nor reset it**; item 4: `resume_endpoint()`
  resets it.
* **Implementation vs record:** matches, and `docs/HTTP_EXPORTER.md` now states it exactly (endpoint
  scope = one exporter bound to one endpoint; only verification failures count; third pauses;
  any completed HTTP exchange or `resume_endpoint()` resets; ordinary network failures neutral).
* **Residual, not separately confirmed (status READY_FOR_OWNER_DECISION):** three refinements that
  are consistent with, but not literally in, the approved text: (1) a verification failure counts
  only for an attempt that had not sent a request (the owner-decisions record's later
  "Compatibility correction": "a TLS verification failure before any request write does not" set
  the may-have-committed marker); (2) with an explicit proxy the CONNECT request is not "the request"; (3) "endpoint-scoped"
  means per exporter instance. Decision text: "Confirm refinements (1)-(3) as the meaning of the
  approved L2 rule." No new approval is recorded.

## 3. Remaining SDK technical issues

| Issue | Severity / impact | Release-policy status | Disposition |
|---|---|---|---|
| Synchronous exporter: no hard per-request deadline; a peer that trickles response **headers** can hold one of two workers while it keeps sending inside the 30 s read timeout | MEDIUM (availability of one exporter; needs a faulty or hostile endpoint, which is an operator-configured trusted destination) | Not a blocker under the documented policy (documented limit; async exporter cancels expired attempts; body trickling is already bounded to 30 s) | **DEFERRED_WITH_RATIONALE.** Smallest safe correction needs a transport-level cancel (watchdog that closes the connection, or an async-only worker model): a behaviour/design change, not low risk. **This SDK does not claim full protection from slow-response attacks** |
| Idle workers built a status snapshot every 10 ms | LOW (2.7% of a core with 900 history rows) | n/a | **FIXED**: worker reads `lifecycle` directly (idle cost 0.44%); regression test counts snapshot calls; mutant killed |
| Release-artifact findings (key material, sdist internal files) | LOW | key guard VERIFIED; internal-files exclusion pending F-9 | see section 2 (for P29 the sdist contents are a separate decision) |
| Key scan covers PEM blocks and key-like names only (not PGP/JWK/PuTTY) | INFO | n/a | DEFERRED_WITH_RATIONALE |
| Silent module skip of the real-TLS tests if `cryptography` is missing | INFO | CI and release workflows install the dev extra | accepted |

## 4. P29 reconciliation (summary; full record in the reconciled tree's `docs/P29_P28_RECONCILIATION.md`)

The P29 workspace was cloned at `7aa6883` with the then-current P28 overlay and re-synced once
(after D-1). Comparison by sha256 against the re-sync manifest: 30 files identical; 7 copy-forward
(P29 never edited: `release.yml`, `CHANGELOG.md`, `CONTRIBUTING.md`, `HTTP_EXPORTER.md`,
`pyproject.toml`, `http_event_sink.py`, the real-TLS test); 3 new (readiness report, targeted
verification, release-regression tests; the readiness report copy includes its later-update note); 2 P29-edited merged by hand (`README.md` unchanged from
P29; `verify_release_artifacts.py`: P28 sdist-guard delta applied to P29's judge-aware file). No
conflicts. The whole P29 judge implementation, its tests and docs are untouched; both originals
are untouched. Two hash-pinned P29 guards flagged the advanced P28 files and passed after the
manifest was updated by the manifest's own convention. P29 stays out of the P28 candidate.

## 5. Combined validation results

P28 SDK (this repository, final working tree):

| Check | Result |
|---|---|
| Suite, Python 3.11.17 / 3.12.15 / 3.13.16 | **870 passed** each |
| ruff, format, mypy (46 files) | clean |
| Real-TLS regression tests (19, sync + async + proxy) and release-regression tests (10) | included; passed on all three Pythons |
| Fixture drift vs integrated platform vectors | 4 hashes verified, platform comparison True |
| Node reference check (Node v26.12.0) | 76 canonical + 74 acknowledgement vectors |
| Wheel + sdist build, `verify_release_artifacts.py` (scratch copy) | sdist 198, wheel 51; exit 0; no key-like files; internal files absent |

Reconciled P29 tree (`agent-reliability-p29-reconciled`):

| Check | Result |
|---|---|
| Suite, Python 3.11 / 3.12 / 3.13 (editable installs in scratch venvs) | **1,561 passed, 1 skipped** each (the skip is the platform-model validation, NOT_EXERCISED by default) |
| That test with `P29_PLATFORM_ROOT`/`P29_PLATFORM_PYTHON` set to the integrated platform | `test_p29_wire_conformance.py` 24 passed: every judge wire body validates against the platform's `EvidenceEnvelopeV2` model |
| ruff, format, mypy (65 files) | clean |
| Fixture drift, Node reference | verified / 76 + 74 vectors |
| Wheel (77 files incl. 26 judge files, 5 rubrics) + sdist (276 files incl. 11 P29 documents and `docs/evidence/`), `verify_release_artifacts.py` | exit 0; no keys; `CLAUDE.md`, `AGENTS.md` and `docs/P28_*` absent. P29's own sdist contents (internal P29 reports, `docs/evidence/` with local paths) are an open P29 packaging decision, not made here |
| **Live judge -> HTTP exporter -> real platform** (scratch copy of the E2E workspace, reconciled SDK; PostgreSQL 16.15 and 17.11; machine auth, OIDC mode) | **81 passed on each** = the 80 SDK-to-platform scenarios (queues, retries, 429, TLS, redirects, concurrency, shutdown) plus the new judge test |

The judge test (scripted fake providers, canary strings in all judged content) checked: every
envelope schema v2 and acknowledged (201); deployment id and producer identity match the
registered triple; the set of payload kinds is exactly the four typed kinds (`run_lifecycle`,
`evaluation_outcome`, `evaluation_execution_failure`, `measurement_health`); outcomes pass/fail per
indicator as scripted; the stopped provider produced execution-failure evidence for both
indicators; per-run health as **stored by the platform** (read through its API): two runs
`healthy`, one not (the SDK's local run object agrees); **the canaries appear neither on the wire
nor in the four evidence tables the judge's data lands in** (ingestion events, evaluations,
measurement health, runs; about 50 other platform tables were not scanned); a positive control
plants a canary in an opaque member (`evaluation_id`) and shows the same scan then finds it;
stored events equal the acknowledged set; no events in another tenant.

**Not exercised / not claimed:** pilot safeguards SG-1..SG-6 are **NOT SATISFIED** (they need a
configured pilot and platform reads/alerts; none exists); rubric calibration; real model
providers; sampling/overload behaviour against the platform; Windows; PostgreSQL 18; load.
Cross-indicator contamination beyond the documented limitation was not tested beyond the
per-run health check above.

## 6. Governance and release-gate matrix

Mandatory = required by a repository document; optional = confidence building. Statuses:
VERIFIED, READY_FOR_OWNER_DECISION, BLOCKED_EXTERNAL_ENVIRONMENT, NOT_EXERCISED,
DEFERRED_WITH_RATIONALE.

### Platform governance

| Gate | Source | Status | Mandatory? |
|---|---|---|---|
| P28-D14 (evidence POST machine authentication) | Decision register section 9; package 5a | READY_FOR_OWNER_DECISION (approval field blank; implemented and verified under an unsigned relayed instruction to implement) | Yes: Plan P28-PC01 prerequisite |
| ADR-0023 Appendix A.2 | package Appendix A.2 | READY_FOR_OWNER_DECISION (draft, approval blank) | Yes |
| Pre-authentication rate limiting (F-2) | PC-1 review | READY_FOR_OWNER_DECISION (layered design recommended, not approved; current behaviour pinned by a characterization test) | Owner decision before production reliance by shared-address SDK traffic |
| Audit retention | PC-1 review F-4 | READY_FOR_OWNER_DECISION (append-only, no pruning) | Capacity/retention decision |
| Verified machine principal and organization in logs | review O-1 | READY_FOR_OWNER_DECISION | Owner decision |
| `dev_header` restrictions | config | production already refuses `dev_header` (verified in code); stricter policy for TEST is READY_FOR_OWNER_DECISION | Owner decision |
| Duplicate Authorization / X-Organization-ID headers | review | READY_FOR_OWNER_DECISION (first-wins, no bypass found) | Owner decision |

### Platform release

| Gate | Status | Mandatory? |
|---|---|---|
| PC-1/PC-2 integration | VERIFIED locally (independent review + targeted verification; 1,160 unit/property; PostgreSQL 16/17; Node conformance) as uncommitted working-tree changes | Yes |
| Commit and CI evidence | NOT_EXERCISED: nothing committed; GitHub Actions never ran the combined tree or `postgres-slow`; main has no classic branch protection | Yes (release order and CI documents) |
| Deployment readiness | NOT_EXERCISED | Yes |
| Production-equivalent OIDC configuration | BLOCKED_EXTERNAL_ENVIRONMENT (only an injected-key verifier was used) | Yes (Plan P28-PC01 evidence) |
| Platform-first release (migration -> PC-2 -> PC-1 -> SDK, per-instance build evidence) | NOT_EXERCISED | Yes (ADR-0028 item 10, decision G1) |

### SDK release

| Gate | Status | Mandatory? |
|---|---|---|
| Public API stability decision (F-4) | READY_FOR_OWNER_DECISION | Yes |
| Distribution contents (F-9) | READY_FOR_OWNER_DECISION (recommended exclusion applied and verified) | Yes (release content) |
| L2 semantics | VERIFIED against the recorded owner selection; refinements READY_FOR_OWNER_DECISION | Confirmation only |
| Changelog | VERIFIED (`[Unreleased]`, no date/version) | Yes |
| Version number and date | READY_FOR_OWNER_DECISION (none chosen) | Yes |
| GitHub Actions execution of the changed workflows | NOT_EXERCISED | Yes for the tag-triggered gates |
| Final artifact build from the exact candidate | NOT_EXERCISED (builds so far are scratch builds of an uncommitted tree) | Yes |
| Named release owner and reviewer | READY_FOR_OWNER_DECISION (none assigned) | Yes |
| Explicit commit and publication authorization | READY_FOR_OWNER_DECISION (none exists) | Yes |
| Windows compatibility | BLOCKED_EXTERNAL_ENVIRONMENT: documented CI matrix is Linux, Python 3.11-3.13, so optional by policy, but the Windows CA-store code path is unexercised | Optional (recommended) |
| PostgreSQL 18 | BLOCKED_EXTERNAL_ENVIRONMENT (not installed); CI uses 17 | Optional |
| Platform-terminated TLS | NOT_EXERCISED (feasible locally: uvicorn with TLS in the E2E workspace) | Optional (confidence) |
| Real forward proxy | NOT_EXERCISED (CONNECT stub only; needs a proxy tool) | Optional |
| Connect-timeout scenarios | NOT_EXERCISED (refusal tested) | Optional |
| Hard per-request deadline for the sync exporter | DEFERRED_WITH_RATIONALE | Not a blocker by the documented limit |

### P29 (separate track)

Judge is EXPERIMENTAL under ADR-0010 (owner decisions P29-D01..D13, option A, recorded 2026-10-16,
unsigned; D09 conditional on SG-1..SG-6). Implemented and author-run; independently sampled with
required corrections; **not pilot-ready, not released**. Integration with the verified P28 exporter
and platform is now VERIFIED locally (section 5). SG-1..SG-6: NOT SATISFIED.

## 7. Release sequence (dependency-aware)

| # | Step | Evidence needed | Depends on | Role | Completion criteria | Owner authorization? |
|---|---|---|---|---|---|---|
| 1 | Owner and governance decisions: D14, ADR-0023 A.2, F-2, audit retention, log identity, header handling, F-4, F-9, L2 refinements, version/date, role assignment | decision records in the repository (approver identity and date as the owner chooses to record) | none | Product/security owner; governance approver | each row in section 6 marked decided | **Yes** |
| 2 | Platform PC-1/PC-2 commit readiness | normalized file modes/line endings of the transferred files; commit plan; exact diff review | 1 (D14/A.2) | Platform implementation owner | clean commits of the integrated tree on a branch | **Yes** (commit authorization) |
| 3 | Platform CI and deployment validation | GitHub Actions runs incl. `postgres` and `postgres-slow`; production-equivalent OIDC TEST; deployment dry run in TEST | 2 | Platform release engineer | all required checks green; OIDC/session TEST passes; branch-protection/required checks configured by the repository owner | **Yes** (TEST/CI use) |
| 4 | Platform-first release evidence | per-instance build evidence that every platform instance serves PC-2 and PC-1 | 3 | Platform release owner | recorded evidence per ADR-0028 item 10 | **Yes** (release) |
| 5 | SDK final compatibility verification | commit of the candidate; exact-candidate artifact build; Actions on 3.11-3.13; E2E against the released-to-TEST platform; optional: Windows, PostgreSQL 18, platform TLS, forward proxy, connect timeout | 1 (F-4/F-9/version), 4 | SDK release owner | green workflows; artifacts inspected; verify script passes on the exact build | **Yes** (commit) |
| 6 | SDK release authorization and publication | named release owner/reviewer; written authorization; publication to the package index | 5 | Release owner | published package matches verified artifacts | **Yes** |
| 7 | P29 integration and pilot readiness (separate) | SG-1..SG-6 evidence, calibration, pilot configuration, platform reads/alerts | independent of 2-6 for the SDK; P29 pilot needs a released platform build from 4 | P29 owner | pilot report; separate decision | **Yes** |

Avoid repeated reviews: no further comprehensive review is needed before step 1; steps 2-6 each
need their own evidence, not a re-review of already verified code.

## 8. Exact next actions

1. Owner: record decisions for F-4, F-9, the L2 refinements and the version/date policy using the
   texts in section 2; record the platform decisions listed in section 6 (D14, A.2, F-2, audit
   retention, log identity, `dev_header`, duplicate headers); assign release owner and reviewer.
2. Platform team: prepare the PC-1/PC-2 commit (normalize modes/line endings), once authorized.
3. SDK team: after the decisions, commit plan for the P28 SDK change set (excluding P29), tag
   workflow run on a branch, exact-candidate build.
4. Optional confidence work that can be done locally without any decision: platform-terminated
   TLS scenario, connect-timeout scenario (full-backlog listener), a real forward proxy, async
   header-trickle test.

## 9. Independent verification of the changes introduced in this task

One focused verification by a fresh subagent context (technical check, not a governance
approval): `docs/P28_P29_CONSOLIDATION_TARGETED_VERIFICATION.md` (authored by the verifier).
Verdict **VERIFIED**; 0 BLOCKER, 0 HIGH, 2 MEDIUM, 7 LOW, 3 INFO. It reproduced: the sdist
exclusion and its guard (fails on a doctored sdist); the idle-worker equivalence and cost
(3.0-3.3% before, 0.4% after); 870 tests on 3.11/3.12/3.13; the reconciled tree byte-identical to
the original P29 workspace except the documented files (judge tree, tests, fixtures, examples,
P29 docs and ADR-0010 identical); both hash-pinned guards still fail on tampering; the original
P29 workspace unchanged; 81 live E2E tests on PostgreSQL 16 and 17; four mutants of the
judge/exporter path killed.

Findings and what was done:

| ID | Finding | Action |
|---|---|---|
| M-1 | "only typed kinds" over-stated (the wire also carries `run_lifecycle`; test asserted presence only) | Test now asserts the exact four-kind set; wording fixed |
| M-2 | the `docs/P[0-9][0-9]_*` exclusion would also drop P29 documents the judge tests read (reconciled sdist tests would fail) | Exclusion narrowed to `docs/P28_*` in both trees and in the guard; P29 sdist contents left as a separate P29 decision |
| L-1 | shipped `HTTP_EXPORTER.md` named an excluded document | reference removed; sdist grep shows no retained reference |
| L-2/L-3 | "any platform table" over-stated; weak positive control; health read from the SDK object | wording scoped to the four tables (about 50 others not scanned); control now plants a canary in `evaluation_id` and the same scan finds it; health is read from the platform's API |
| L-4 | manifest entry of the hand-merged verify script described inaccurately | reconciliation record corrected |
| L-5 | wrong source for refinement (1) | corrected to the owner-decisions "Compatibility correction" |
| L-6 | `docs/evidence/` ships in the reconciled sdist with local paths; count | disclosed with the open P29 packaging decision; counts corrected |
| L-7 | reconciled readiness report lacked the later-update note | copied forward |
| INFO | file counts; the exporter is under `adapters`, not an experimental namespace (VERSIONING.md expects a labelled experimental namespace for experimental APIs); placeholder | counts corrected; the namespace point is part of the F-4 decision text above; placeholder replaced |

After these corrections the checks in section 5 were re-run and pass (870 SDK tests on three
Pythons, 1,561 + 1 skipped in the reconciled tree, platform-model validation 24 passed, 81 live
E2E tests on PostgreSQL 16 and 17). The corrections themselves were not re-reviewed (the task
allowed one focused verification); they are mechanical and covered by the re-run tests.

# P28 / P29 governance closure, Git integration, CI and pilot readiness report

Date: 2026-10-17. Author: the implementation agent (Claude Code). The independent review and the
targeted verification are separate documents written by their own reviewers (section 17).

**Final status: `P28_P29_GOVERNANCE_AND_CI_READY_FOR_OWNER_APPROVAL`.**
The target milestone `P28_P29_RELEASE_GOVERNANCE_APPROVED_AND_CI_VERIFIED` is **not** reached: no
governance approval was given in this milestone and no hosted CI job has run. The earlier statuses
remain valid (P28 `TECHNICALLY_VERIFIED_WITH_EXTERNAL_GATES`, P29
`SDK_V1_TECHNICALLY_VERIFIED_WITH_PILOT_GATES`, combined
`P28_P29_FINAL_CANDIDATE_VERIFIED_WITH_EXTERNAL_GATES`); no regression was found.

## 1. Executive summary

* **Changed (all uncommitted, in the two final candidates):** draft decision records for the six
  open P28 security items; policy-neutral characterization tests; judge-indicator coverage (P6),
  gate (P7) and P3/P4 regression tests against real PostgreSQL; a pilot report template with a
  checker that refuses unevidenced "SATISFIED" claims; hardened SDK workflows (time limits, an
  independent Node reference job, release only from `main`) with a static workflow-policy test; a Git
  integration plan whose commit groups were rehearsed stage by stage; calibration, release-management
  and owner-decision documents; mode and line-ending hygiene.
* **Tested:** SDK 1,648 passed + 1 skipped on Python 3.11, 3.12 and 3.13; platform 1,168
  unit/property, PostgreSQL 16 and 17 integration (529 passed each), slow tier, clean
  `alembic upgrade head`; packaging verified (section 10). Results are from the end state after the
  review remediation in section 17.
* **Not done and not claimed:** no commit, push, pull request, merge, tag, deployment, publication or
  pilot; no hosted CI; no approval recorded; no external model call.
* **New findings worth the owner's attention:** (1) behind a load balancer the whole fleet shares one
  rate-limit key unless forwarded headers are trusted explicitly; (2) an unavailable run health does not
  affect any P7 gate decision (OD-10); (3) the earlier suggestion to refuse `dev_header` in every
  non-local environment would break CI and the shared TEST smoke path; (4) the rehearsal exposed two
  grouping defects that would have broken intermediate commits (fixed).

## 2. Source baseline and provenance

| Item | Value |
|---|---|
| SDK candidate | `<workspace>/agent-reliability-final`, branch `p29-sdk-v1-local`, `HEAD 7aa6883` (= `main`), 149 changed files, no commits |
| Platform candidate | `<workspace>/agent-reliability-platform-final`, plain file tree (not a git repository), base `d606293` = `main`, 145 changed files |
| Start-of-milestone check | both trees matched the recovered freeze manifests (SDK 299 files, platform 632 files): 0 changed, 0 missing, 0 extra |
| Other writers | none detected; originals (`agent-reliability`, `agent-reliability-platform`, `-p29`, `-p29-reconciled`, `-platform-integration`, `-platform-pc1`, E2E workspace) were not modified |
| Remote refs | not fetched in this milestone; `origin/main` equals the recorded base in the local clones |
| Evidence | `<workspace>/gentlity-p28-p29-governance-evidence/` (outputs, rehearsal logs, tools, commit groups, end-state manifests `freeze4_*.txt`) |
| Rollback | nothing was committed; the candidates are restorable from the freeze3 manifests plus the listed edits; originals untouched |

## 3. Release scope (frozen, unchanged)

P28: PC-1 machine authentication, PC-2 schema-v2 ingestion, the Python SDK HTTP exporter, verified TLS
and proxy handling, packaging and artifact security guards. P29: the experimental native LLM-judge SDK
V1 (customer-provided providers, existing rubric and result contracts, local execution, existing wire).
No product feature, contract or architecture changed in this milestone. P29 stays explicitly
experimental and separable: the P28-only tree/commit group builds the P28-only artifact (199 sdist /
51 wheel files, no judge) and the combined artifact has 272 sdist / 77 wheel files (26 judge files).

## 4. Governance decisions already approved

Unsigned relays, no approver identity recorded: F-4, F-9, L2 (`P28_SDK_EXPORTER_OWNER_DECISIONS_002.md`);
the earlier SDK decisions in `..._001.md`; P28 platform relays of 2026-10-11 (general architecture
approval, PC-2 scope, C, D, K2, M1, G1 platform-first release, D07, E5 `2s`, X1-X3, M-b, I-1, ADR-0028)
and 2026-10-16 (D1-D4, `postgres-slow` required); P29-D09 and P29-D10. These cover the exact behaviour
they name and nothing else: **technical completion of PC-1 is not approval of D14**.

## 5. Governance decisions still pending

D14 / ADR-0023 Appendix A.2 (approval field "UNASSIGNED - pending", no approver named), F-2, audit
retention, verified identity in logs, `dev_header` policy, duplicate headers, Decision F role
assignments, release version and date, Git/CI authorization, publication, SG-1..SG-6 sign-offs, pilot
authorization, measurement health in the gate. All are collected, once, in
`P28_P29_OWNER_DECISION_PACKET.md` (OD-1..OD-11); the full draft records are in
`docs/roadmap/P28/P28_GOVERNANCE_DECISION_RECORDS.md` of the platform tree. No approval was recorded
or inferred.

## 6. P28 security policy recommendations (summary of DR-1..DR-6)

| Item | Current behaviour (verified) | Recommendation | Pinned by |
|---|---|---|---|
| D14 / A.2 | machine bearer wins, no fallback; implemented, not approved; real-IdP OIDC matrix not run | approve conditional on the OIDC matrix | PC-1 unit and PostgreSQL suites |
| F-2 | limiter before authentication, key = peer address + path, 30/min security, 6,000/min ingestion per process, 10,000-key LRU; invalid-bearer flood starves a valid caller; forwarded headers not trusted by default so a balancer collapses the key | layered: edge, trusted address, failure counting, post-authentication per-credential/organization quotas | `test_shared_address_invalid_bearer_flood...`, `test_forwarded_for_header_neither_evades_nor_resets_the_limiter`, `test_each_ingestion_path_has_its_own_limiter_budget` |
| Retention | audit append-only by trigger, no retention, about 450 B per accepted POST; evidence rows carry idempotency claims | structure only; periods are PROPOSED; idempotency claims outlive the retry horizon | documentation |
| Identity in logs | asserted headers logged as organization/actor | log verified identity; rename asserted values | `test_request_log_uses_client_asserted_headers...` |
| `dev_header` | default mode; accepted in `local` and `test`; production refuses | explicit acknowledgement outside `local` | `test_dev_header_is_the_default...`, `test_production_refuses_dev_header_authentication` |
| Duplicate headers | first value wins; comma-joined folded values rejected (401/422) | reject duplicates with 422 (not 400, to stay inside the documented status set) | duplicate-header and `test_comma_joined_headers...` tests |

## 7. Git integration plan

See `P28_P29_GIT_INTEGRATION_PLAN.md`. SDK: four groups (P28 exporter, CI hardening, P29 judge,
internal reports); platform: five (PC-1, PC-2 with migration, integration/regression tests, CI,
reports/draft governance). Both final trees are reproduced byte-for-byte by the staged groups (SDK 310
files, platform 634 files). Secret scan clean; modes and line endings corrected as described there.

## 8. Proposed commit groups and PR sequence

Merge order P-A, P-B, P-C, P-D, P-E (platform) then S-A, S-B, S-C (SDK); release order is migration,
PC-2, PC-1, then the SDK. Rehearsed per-stage results are in the plan: SDK 904 / 912 / 1,643 + 6 skipped /
1,648 + 1 skipped passed; platform unit/property 793 / 1,157 / 1,165 / 1,168 / 1,168 and PostgreSQL PC-1
17 and PC-2 491 (+1 expected failure). The rehearsal found and fixed two real defects in an earlier
grouping (test input vectors and the `slow` marker had been placed after the code that needs them).

## 9. CI workflow readiness

| Aspect | SDK `ci.yml` / `release.yml` | Platform `ci.yml` |
|---|---|---|
| Permissions | `contents: read`; release: `id-token: write` only on `publish`, `contents: write` only on `github-release` | `contents: read` |
| Secrets | none in CI; release uses `GITHUB_TOKEN` and Trusted Publishing (no stored PyPI token) | none; a fixed CI-only password for the throwaway service database |
| Action pinning | all by full commit SHA (enforced by `tests/unit/test_workflow_policy.py`) | all by full commit SHA |
| Dependencies / extras | `.[dev,http]`, `.[dev,otel-test,http]`; core stays dependency-free | `.[dev]` |
| Python | 3.11, 3.12, 3.13 (test matrix) | 3.11 only |
| Gates | ruff, format, mypy, fixture manifest, full pytest with branch coverage, build, artifact verification, **new:** independent Node reference vectors | frontend, quality, unit/property with coverage, `postgres` (integration, not slow), `postgres-slow` (D3 required), artifact security (`pip-audit`, build), container |
| Caching | pip via `setup-python` | pip and npm |
| Artifact retention | CI uploads nothing; release uploads `dist/` with the default retention | none uploaded |
| Failure reporting | default job status; no annotations | default |
| Release trigger | tag `v*.*.*` only; tag must equal `__version__`; **new:** commit must be reachable from `origin/main` | n/a |

**Corrections made (SDK, small and scoped):** `timeout-minutes` on every job; a new
`reference-vectors` job running `node scripts/verify_p28_reference.mjs` (no dependencies; `setup-node`
pinned to the same SHA the platform workflow already uses); the main-branch ancestry check in the release
workflow (shell logic tested against a throwaway repository: allowed for a commit on `main`, blocked for a
feature-branch commit); `docs/RELEASING.md` sentence; `tests/unit/test_workflow_policy.py` (8 tests).
The release guard also flagged the new `docs/P29_PILOT_REPORT_TEMPLATE.json` as an internal file, so it
was added to the explicit public allowlist with its test.

**Not changed, reported:** the platform's Node conformance tool (`tests/contracts/node`) is not run by
CI and has no lockfile (running it would need `npm install`); a PostgreSQL 16 job is not in CI although
16 was verified locally and the README says 15+; the SDK/platform cross-repository conformance and
end-to-end suites need both repositories and are not CI jobs; the platform pins action versions that
differ from the SDK's; `CONTRIBUTING.md` still says `1.1.1` is released (pre-existing). `postgres-slow` is
documented as required, but the required-check setting is GitHub configuration that was not verified.

## 10. Actual local and hosted CI results

Hosted GitHub Actions: **NOT RUN.** Nothing was pushed, so no workflow could execute; no run result is
claimed. Local equivalents (outputs in the evidence directory):

| Check | Result |
|---|---|
| SDK ruff, format check, mypy `src` (65 files), fixture-manifest verification (4 hashes) | clean on Python 3.11, 3.12, 3.13 |
| SDK full pytest | 1,648 passed + 1 skipped on 3.11, 3.12 and 3.13 |
| SDK Node reference vectors | 76 canonical byte/digest vectors, 74 acknowledgement vectors passed |
| SDK cross-repository (platform tree): fixture drift, `tests/contract` with the platform environment | 4 hashes match the platform copy; 480 passed (includes the 24 wire-conformance tests) |
| SDK build and `scripts/verify_release_artifacts.py` | exit 0; wheel 77 files (26 judge), sdist 272 files; no internal reports, `CLAUDE.md`, `AGENTS.md`, key material or local paths in the artifacts |
| Platform ruff, format check (553 files), mypy `src` (138 files) | clean |
| Platform `pytest -m "not integration"` | 1,168 passed |
| Platform PostgreSQL 16, `alembic upgrade head` (head `0019`), `integration and not slow` | 529 passed, 1 expected failure (strict) |
| Platform PostgreSQL 17, same | 529 passed, 1 expected failure |
| Platform `postgres-slow` tier, PostgreSQL 16 and 17 | 3 passed each |
| Not run locally | `pip-audit` (needs network), `docker build` and the container job, frontend jobs (unchanged), Python 3.12/3.13 for the platform |

All numbers above are from one final pass on the end state, after the review remediation; the
verify script run is in `verify_release_artifacts_output.txt` (exit 0).

## 11. P29 platform tests: P6 coverage, P7 gate, P3/P4

`tests/integration/test_postgres_judge_indicator_coverage_gate.py` in the platform tree: 20 tests,
real PostgreSQL 16 and 17, expected values hand-calculated before the run (formulas in the module
docstring). The platform treats judge indicators exactly like any other indicator; nothing was changed
in platform source or policy. Mutation check (author, two manual mutants): raising the policy
threshold, and adding determinate evidence to the unknown-only scenario, each make the relevant tests
fail. The independent reviewer found that a mutant firing the policy on EITHER window survived the first
19 tests; the 20th test (short window breaches, long window does not) was added and asserts the burn
rates 5 and 0.5 and an ALLOW decision.

| Scenario | Expected (hand-computed) | Result |
|---|---|---|
| 9 pass + 1 fail, target 0.9 | reliability 0.9, `met`, journey governed and evidenced, no gap, traffic ratio 10/10 = 1, burn 1 < 2, gate ALLOW | as expected |
| 6 unknown + 3 execution failures | determinate 0, SLO `no_data`; governance FULL but not evidenced; traffic ratio still 1 | as expected |
| no evidence (skipped evaluations) | `no_data`, measurement `no_data` | as expected |
| required judge indicator without SLO | governance NONE, critical gap, ratio 0/10, gate BLOCK | as expected |
| 5 pass + 5 fail | burn 5 >= 2 both windows, policy firing; BLOCK (WARN when severity is warn) | as expected |
| unknown-only with `on_no_data` warn / block | policy and evidence conditions `no_data`; WARN / BLOCK | as expected |
| mixed deterministic + judge | either policy firing blocks; both healthy allows; judge unknown-only with deterministic met gives WARN | as expected |
| run health: judge failure + unavailable run | deterministic indicator `measurement_state` becomes `unavailable` (cross-indicator, run scoped) while compliance stays `met` | as expected |
| unavailable measurement health vs the gate | SLO `unavailable`, but gate ALLOW: health is not a gate input | pinned as current semantic (OD-10) |
| invalid evidence (reason code without provenance) | rejected, nothing stored | as expected |
| P3/P4 regression (Q1 pass, Q2 fail, Q3 failure) | counts 1/1/0, failures 1, determinate 2, total 3, reliability 0.5, healthy 2, unavailable 1; allowed failures 0.2, remaining -0.8, consumed 5, remaining fraction -4, burn 5, delta -0.4, breached, unavailable | matches the end-to-end values |

Platform fail-open / fail-closed behaviour is therefore configured per gate condition (`severity`,
`on_no_data`), not built in; no policy was changed.

## 12. SG-1 through SG-6

All six remain **NOT SATISFIED**; no pilot exists, and none was started. What changed: the exact
acceptance text is preserved in `docs/P29_PILOT_SAFEGUARDS.md`, which gained operational checklists, the
platform behaviours above, and a machine-readable report template
(`docs/P29_PILOT_REPORT_TEMPLATE.json`) with `scripts/p29_pilot_report_check.py`. The checker refuses a
SATISFIED safeguard unless every field is present, correctly typed and non-blank, there is an evidence
reference of at least six characters and the sign-off has role, name and an ISO date from 2020 on;
it rejects duplicate JSON keys and NaN, refuses `pilot_authorized: true` unless all six are satisfied, and never sets a status (40 tests,
including the bypass inputs the reviewer found). It checks completeness and plausibility of form, not
truth. Responsible roles are
unassigned. Cannot be completed before a pilot: budget sizing from real traffic (SG-1), the restated note
in a real report (SG-2), P3 figures from a real window (SG-3), the isolation decision (SG-4), customer alert
wiring and a firing test (SG-5), the gate setting on a real gate (SG-6).

## 13. Real-model calibration preparation

`P28_P29_CALIBRATION_PREPARATION.md`: authorization gate, dataset specification with strata and minimums,
rubric and template versioning rules, human-review method, the harness's agreement metrics, false-negative
and false-positive definitions as the harness uses them, cost/latency/failure measurement, privacy
controls, and **PROPOSED** thresholds (labelled; P29-D10 makes calibration customer-local and the harness
enforces no threshold). Nothing was executed: no model, charge, download or customer content.

## 14. Release ownership gaps

Every role is unassigned (`P28_P29_RELEASE_MANAGEMENT_RECORD.md`): platform release owner, SDK release
owner, independent reviewer, security/governance approver, pilot owner, rollback owner, OIDC TEST
environment owner. No person or signature was invented.

## 15. Version recommendations

SDK: a minor release for the P28-only artifact (for example `1.3.0` from `1.2.1`) and a later minor for the
experimental judge (for example `1.4.0`); platform: no package version bump, identify by git SHA and image
digest. Nothing is assigned, tagged or published. Distinguishing method and the platform-first evidence
table are in the release management record.

## 16. Remaining environment gaps

Not executed: hosted GitHub Actions; PostgreSQL 18; Windows; platform-terminated TLS beyond the earlier
scratch run; production-equivalent OIDC with a real identity provider; a real forward proxy; the
connect-timeout scenario (not reproducible on macOS loopback); real-model evaluation and calibration;
benchmarking; `pip-audit`; container build; the platform on Python 3.12/3.13. The synchronous exporter's
header-trickling limitation remains documented, not fixed.

## 17. Independent verification

**Review** (`P28_P29_GOVERNANCE_INDEPENDENT_REVIEW.md`, written by the reviewer, not edited): verdict
`APPROVE_WITH_REQUIRED_CORRECTIONS`; 0 BLOCKER, 0 HIGH, 4 MEDIUM, 8 LOW, 3 INFO (renumbered by the
reviewer as F-01..F-16). The reviewer confirmed: no platform or SDK source change since freeze3; original
worktrees unchanged; no fabricated approval, signature or person; all P6/P7 expectations recomputed
independently; characterization tests not vacuous; workflow ancestry check behaves as intended.

| Finding | Disposition |
|---|---|
| F-01 SDK groups/rehearsal stale (MEDIUM) | fixed: groups regenerated (SDK 149 files in four groups), `tests/unit/test_release_artifact_guards.py` re-staged with the P29 allowlist change; rehearsal rerun, 0 differing files (SDK 310, platform 634) |
| F-02 checker accepted junk (MEDIUM) | fixed: type and blank checks per field, positive counts, real booleans, evidence length, sign-off name/role/date plausibility, duplicate keys and NaN rejected; 22 new tests; documentation reworded to "completeness and plausibility of form, not truth" |
| F-03 calibration document misdescribed the harness (MEDIUM) | fixed: ambiguous cases are in the harness headline slice; kappa is human-versus-judge; labeler-versus-labeler agreement is computed outside the harness |
| F-04 audit facts imprecise (MEDIUM) | fixed in DR-3 and `evidence-ingest-machine-auth.md`: any successful authenticated mutating request is audited, best-effort, built from the verified context |
| F-05 workflow test could pass with a neutralised guard | fixed: regex on the exact failing guard, `|| true` and `continue-on-error` forbidden, `timeout-minutes` on every release job; mutant `exit 1 \|\| true` now fails the test |
| F-06 plan branch name already exists; fetch note | fixed: new branches use the `final/` prefix; the `git fetch` side effect on the originals' refs is stated |
| F-07 artifact counts (268 vs 272) | fixed |
| F-08 dangling references | fixed: `freeze4_*.txt` created; section references corrected; the verify-script output is stored |
| F-09 local-path counts | fixed (24 SDK and 8 platform developer-path documents, all in the internal-report groups; 4 older platform documents on `main` carry server paths) |
| F-10 DR-6 omitted 409; DR-2 per-process wording; DR-4 log wording | fixed |
| F-11 checker robustness | fixed with F-02 |
| F-12 AND of both P5 windows untested | fixed: new test (20th) |
| F-13 generated caches left in the trees | removed before the end-state manifests |
| F-14 P29-D09/D10 source documents not in the trees | stated as a limitation: those decisions rest on the project record cited by `docs/P29_PILOT_SAFEGUARDS.md` ("P29 Owner Decisions 001") which is not in either repository tree |
| F-15, F-16 (INFO) | no change needed |

**Targeted verification:** `P28_P29_GOVERNANCE_TARGETED_VERIFICATION.md` (separate verifier). Its outcome is
in section 19.

## 18. Exact next actions (dependency order)

1. Owner answers OD-1..OD-11 (or defers some) with approver and date.
2. Assign the Decision F and release roles (OD-9).
3. Authorize local commits (OD-7), then pushing draft pull requests (OD-8); run hosted CI; record URLs
   and results here.
4. Implement the approved policy items as separate changes replacing the characterization tests.
5. Run the production-equivalent OIDC matrix; verify the target stack's forwarded-header behaviour.
6. Platform release in order (migration, PC-2, PC-1), then the SDK release per the version decision.
7. Assign pilot roles; calibration run 1 on synthetic data only after authorization (OD-11).

## 19. Targeted verification outcome

`P28_P29_GOVERNANCE_TARGETED_VERIFICATION.md` (separate verifier): verdict `VERIFIED_WITH_NOTES`, 0 BLOCKER,
0 HIGH, 0 MEDIUM, 5 LOW. Nine findings FIXED, four PARTIALLY FIXED (F-03, F-09, F-10, F-11), plus new LOW items
N-01..N-05, all dispositioned after the verification: N-01 (checker crash inputs, non-boolean
`pilot_authorized`) fixed with two more tests (checker now 42 tests); N-02 this section; N-03 counts
corrected; N-04 adversarial criterion reworded; N-05 DR-5 wording corrected. Accepted limits the verifier
noted and I did not change: the checker still accepts short plausible-looking evidence strings (it checks
form, not truth); a mutant weakening only the long P5 window is not caught by the new test; platform CI
has a timeout only on `postgres-slow`. These post-verification edits are small and covered by the checker
tests, the unchanged full suites below, and were not given a further independent review.

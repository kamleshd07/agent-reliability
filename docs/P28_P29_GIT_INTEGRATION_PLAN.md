# P28 / P29 Git integration plan (prepared, NOT executed)

Status: **PLAN ONLY.** Nothing was committed, pushed, tagged, merged or opened as a pull request.
The commands in section 7 are for a later, explicitly authorized step. Every number below was
produced by the read-only tools in `gentlity-p28-p29-governance-evidence/tools/`
(`classify_groups.py`, `stage_groups.py`, `with_pg.sh`).

## 1. Baseline, provenance and rollback

| Item | SDK | Platform |
|---|---|---|
| Final candidate | `agent-reliability-final` (git repo, branch `p29-sdk-v1-local`, `HEAD 7aa6883`, no remote, 149 changed files) | `agent-reliability-platform-final` (plain file tree, **not** a git repository, 145 changed files after excluding generated caches) |
| Integration base | `7aa6883` = `main` = last-fetched `origin/main` ("chore(release): prepare 1.2.1") | `d606293` = last-fetched `origin/main` (merge of PR #47) |
| Remote | `origin https://github.com/kamleshd07/agent-reliability.git` (configured in `agent-reliability`, not in the final copy) | `origin https://github.com/kamleshd07/agent-reliability-platform.git` (configured in `agent-reliability-platform`) |
| Freeze manifest | `freeze3_sdk_final.txt` (299 files) | `freeze3_platform_final.txt` (632 files) |

* The remote refs were **not fetched** during this milestone; "last-fetched `origin/main`" is the
  state in the local clone. Step 1 of the execution plan is a fetch and a comparison; if `origin/main`
  moved, rebuild the groups against the new base and rerun the rehearsal before committing.
* The final candidates matched their freeze manifests at the start of this milestone. The changes made
  since are the governance work listed in the readiness report; the end-state manifests are
  `freeze4_sdk_final.txt` and `freeze4_platform_final.txt` in the evidence directory.
* **Rollback:** the original worktrees (`agent-reliability`, `agent-reliability-platform`,
  `-p29`, `-p29-reconciled`, `-platform-integration`, `-platform-pc1`, `-platform-p12-local-prep`,
  the E2E workspace) were not modified by this milestone and remain the fallback. Integration is done
  in a **new worktree and new branches**; abandoning it means deleting that worktree and those local
  branches. No history is rewritten and nothing is force-pushed.
* **Reproducibility:** `stage_groups.py` rebuilds every cumulative tree from the sources and checks that
  the last tree is byte-identical to the final candidate. Rehearsed result for both repositories:
  0 differing files (SDK 310 files, platform 634 files).

## 2. Safety checks performed on the changeset

| Check | Result |
|---|---|
| Secrets, private keys, tokens (patterns for PEM, cloud and VCS tokens, JWT-like strings) | none in either tree; the two textual hits are reviewer sentences describing the marker |
| Key/certificate/`.env`/database files | none (TLS test certificates are generated at run time) |
| File modes | 13 tracked SDK files had gained mode `100755` and `CLAUDE.md`/`AGENTS.md` were executable; all set back to `644` in this milestone (content unchanged). Platform: no executable files outside scripts |
| Line endings | all SDK files are LF. The original SDK working tree (`agent-reliability`) holds CRLF copies that `core.autocrlf=input` hides from `git status`; the plan therefore stages the LF versions. Platform: two reviewer-authored documents (`P28_DESIGN_002_INDEPENDENT_REVIEW.md`, `P28_PC2_IMPLEMENTATION_REPORT.md`) still contain CRLF; normalizing them is mechanical but edits reviewer text, so it is left to the commit step (owner decision OD-7) |
| Local machine paths | 24 SDK documents (all in group 4) and 8 platform documents (all in group 5) quote absolute paths of the developer's machine (home directory, scratch directories). No code, test, workflow or shipped-package file in groups 1-3 does (the sdist guard also rejects them). Pre-existing platform documents already on `main` contain a few similar paths. Whether to sanitize the new reports before publication is owner decision OD-7 |
| Generated artifacts | `.hypothesis/`, `.mypy_cache/`, `.ruff_cache/` exist in the platform tree from local runs; excluded from the groups and removed before the end-state manifest |
| Internal-only files | `CLAUDE.md`, `AGENTS.md`, `docs/P28_*`, internal `docs/P29_*` reports and `docs/evidence/` are excluded from the sdist (F-9) and are kept in a separate commit group so they can be dropped without affecting code |
| Parallel sessions | the freeze comparison at the start of the milestone showed no drift; no other writer was detected |

## 3. SDK commit groups (stacked on `7aa6883`)

Rehearsal: each cumulative tree was built without Git and passed ruff, format check, mypy and the
full suite on Python 3.11 (`rehearsal_sdk.txt`).

| # | Commit (draft message) | Files | Rehearsal result of the cumulative tree |
|---|---|---|---|
| 1 | `feat(p28): add HTTP evidence exporter` - sink, protocol and delivery modules, event-sink and context changes, `http` extra, sdist exclusions and release-artifact guards, fixtures and reference verification scripts, contract/unit/compat tests, `HTTP_EXPORTER.md`, GA contract, README and CHANGELOG entries | 29 (the P28-only tree, LF) | 904 passed |
| 2 | `ci: harden workflows` - time limits, independent Node reference job, release must come from `main`, workflow policy test, `RELEASING.md` sentence | 4 (`ci.yml`, `release.yml`, `tests/unit/test_workflow_policy.py`, `docs/RELEASING.md`) | 912 passed |
| 3 | `feat(p29): add experimental LLM-judge adapter` - `agent_reliability.experimental.judge`, ADR-0010, examples, pilot runbook, safeguards, pilot report template and checker, tests and fixtures, plus the P29 delta in the 11 shared files | 77 new, plus the P29 delta of the 11 shared files | 1,643 passed, 6 skipped |
| 4 | `docs: record P28/P29 reviews and release readiness` - internal reports, baseline manifests, evidence, `CLAUDE.md`, `AGENTS.md` | 39 | 1,648 passed, 1 skipped |

The 11 files modified by both group 1 and group 3 are `CHANGELOG.md`, `README.md`,
`docs/EVALUATE.md`, `docs/GA_CONTRACT.md`, `docs/ROADMAP.md`, `docs/VERSIONING.md`,
`docs/adr/0007-evaluator-architecture-and-provenance-semantics.md`, `docs/adr/README.md`,
`pyproject.toml`, `scripts/verify_release_artifacts.py` and `tests/unit/test_release_artifact_guards.py`. Group 1 stages the P28-only version;
group 3 stages the final version. (The two workflow files belong to groups 1 and 2 only.) The P28-only
and P28 + P29 artifacts are distinguishable by construction (see the release management record).

## 4. Platform commit groups (stacked on `d606293`)

Rehearsal results are in `rehearsal_platform.txt` and `rehearsal_platform_integration.txt`.

| # | Commit (draft message) | Files | Rehearsal |
|---|---|---|---|
| 1 | `feat(p28): machine-credential authentication for evidence ingestion (PC-1)` - dependency and route wiring, PC-1 unit and PostgreSQL tests, auth documentation | 5 | ruff, mypy clean; 793 unit/property passed; 17 PostgreSQL PC-1 tests passed |
| 2 | `feat(p28): schema-v2 evidence ingestion with deployment binding (PC-2)` - domain, schemas, service, repository, migration `0019`, ADR-0028, reference vectors (test inputs), contract and unit tests, `slow` marker, API documentation | 43 | ruff, mypy clean; 1,157 unit/property passed; 491 PostgreSQL passed (+1 expected failure) |
| 3 | `test(p28): integration, policy-characterization and judge-indicator coverage/gate tests` | 5 | 1,165 unit/property passed |
| 4 | `ci: add the required postgres-slow job and document required checks` | 3 | 1,168 unit/property passed |
| 5 | `docs(p28): add PC-1/PC-2 reports and draft governance decision records`, `CLAUDE.md`, `AGENTS.md` | 89 | 1,168 unit/property passed |

Two grouping defects were found by this rehearsal and corrected before this plan was written:
the reference vectors under `docs/roadmap/P28/reference-vectors/` are test inputs (not reports) and
the `slow` marker in `pyproject.toml` is needed by the migration safety tests; both now travel with
group 2. Shared files re-touched by group 2 (`api/dependencies.py`, `api/evidence_routes.py`,
`docs/security/evidence-ingest-machine-auth.md`) take the final version in group 2.

## 5. Pull-request sequence, merge order and dependencies

| PR | Repository | Contains | Depends on |
|---|---|---|---|
| P-A | platform | group 1 (PC-1) | base |
| P-B | platform | group 2 (PC-2 + migration) | P-A |
| P-C | platform | group 3 (tests) | P-B |
| P-D | platform | group 4 (CI, required check `postgres-slow`) | P-B (the slow tests it selects) |
| P-E | platform | group 5 (reports, draft decision records) | none technically; merge last |
| S-A | SDK | groups 1 + 2 (P28 exporter + CI hardening) | none |
| S-B | SDK | group 3 (P29 experimental judge) | S-A |
| S-C | SDK | group 4 (internal reports) | S-B (optional) |

* Merge order is `P-A -> P-B -> P-C -> P-D -> P-E`, then `S-A -> S-B -> S-C`. Merging is not
  deploying: the platform never auto-deploys on merge, and the recorded **release** order is
  migration `0019` -> PC-2 code -> PC-1 -> SDK release (platform-first, decision G1/D07).
* The SDK pull requests may be reviewed in parallel with the platform ones, but the SDK **release**
  waits for the platform evidence in the release management record.
* S-A alone is the P28-only release candidate; S-B must not be released until the P29 pilot-gate
  decision is made.
* P-D's required-check setting (`postgres-slow`, and for the SDK `reference-vectors`) is GitHub
  repository configuration and is not changed by committing the workflow.

## 6. Pull-request description drafts

Each description follows `.github/pull_request_template.md`; the trailing line is the attribution
required by the session configuration. Draft summaries:

* **P-A:** adds `evidence:ingest` machine-credential authentication on `POST /api/v1/evidence/runs`;
  no change to reads or other routes; tests: unit matrix and real-PostgreSQL matrix. Decision status:
  D14 / ADR-0023 Appendix A.2 **not approved** (see `P28_GOVERNANCE_DECISION_RECORDS.md`).
* **P-B:** schema-v2 ingestion, producer identity, deployment-identity binding, migration `0019`
  (guarded, idempotent downgrade that refuses while v2 evidence exists). Approvals referenced: ADR-0028
  and the recorded 2026-10-11 and 2026-10-16 owner relays.
* **P-C:** policy-characterization tests (duplicate headers, asserted-vs-verified identity in logs,
  `dev_header`, rate-limit behaviour) and judge-indicator coverage/gate tests; no behaviour change.
* **P-D:** `postgres-slow` job and narrowed `postgres` selection (owner decision D3); docs.
* **S-A:** optional `http` extra, HTTP evidence exporter (internal submodules, no new stable API),
  packaging and release-artifact guards, workflow hardening.
* **S-B:** experimental judge adapter (ADR-0010); scripted-provider tests only; no calibration or
  accuracy claim; pilot safeguards SG-1..SG-6 **not satisfied**.

Each description must state: nothing is released or published by merging, hosted CI results (none
yet), unexecuted checks (PostgreSQL 18, Windows, production-equivalent OIDC, real forward proxy).

## 7. Controlled execution plan (run ONLY after explicit authorization)

Variables: `D=<workspace>`, `E=$D/gentlity-p28-p29-governance-evidence`,
`R=<tmp>`.

```bash
# 0. Re-establish the base and the rehearsal trees (stop if the base moved).
#    NOTE: `git fetch` updates remote-tracking refs inside the original repositories' .git (no
#    working-tree change); use a fresh clone instead if even that must be avoided.
git -C $D/agent-reliability fetch origin
test "$(git -C $D/agent-reliability rev-parse origin/main)" = "$(git -C $D/agent-reliability rev-parse 7aa6883)" || echo "BASE MOVED"
git -C $D/agent-reliability-platform fetch origin
test "$(git -C $D/agent-reliability-platform rev-parse origin/main)" = "$(git -C $D/agent-reliability-platform rev-parse d606293)" || echo "BASE MOVED"
python3 $E/tools/classify_groups.py
python3 $E/tools/stage_groups.py sdk $R/sdk && python3 $E/tools/stage_groups.py platform $R/platform

# 1. SDK: new worktree and branch (the original working tree is untouched)
git -C $D/agent-reliability worktree add $D/agent-reliability-integration -b final/p28-sdk-http-exporter origin/main
for stage in S1-p28-exporter S2-ci-hardening; do
  rsync -a --delete --exclude='.git' "$R/sdk/$stage/" "$D/agent-reliability-integration/"
  git -C $D/agent-reliability-integration add -A
  git -C $D/agent-reliability-integration diff --cached --stat   # review before each commit
  git -C $D/agent-reliability-integration commit -F "$E/commit_messages/sdk_$stage.txt"
done
#    then, on a second branch from this one: final/p29-experimental-judge  <- stage S3-p29-judge,
#    and optionally final/p28-p29-reports <- stage S4-internal-reports

# 2. Platform: same pattern on a new worktree, stages S1-pc1 ... S5-reports, one branch per PR
git -C $D/agent-reliability-platform worktree add $D/agent-reliability-platform-integration-pr -b final/p28-pc1-machine-auth origin/main
#    (the name feat/p28-pc1-machine-auth already exists locally, so new names use the prefix final/)
#    stage S1 -> commit; branch final/p28-pc2-ingestion-v2 -> S2; final/p28-integration-regressions -> S3;
#    final/p28-required-checks -> S4; final/p28-reports -> S5

# 3. Verify before pushing (per branch)
#    SDK: ruff check . ; ruff format --check . ; mypy src ; pytest ; python -m build ; python scripts/verify_release_artifacts.py
#    Platform: ruff, mypy src, pytest -m "not integration", $E/tools/with_pg.sh 17 -- pytest -m "integration and not slow"

# 4. Publish (separate authorization): git push -u origin <branch> ; gh pr create --base <base> --title ... --body-file ...
#    Wait for hosted CI; record the run URLs and results in the readiness report.
```

Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`; pull-request
descriptions end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. The
`commit_messages/` files are written at execution time; they are not committed anywhere.

Not part of this plan and not authorized: tags, releases, PyPI publication, deployment, changing
GitHub settings (required checks, environments, trusted publishing).

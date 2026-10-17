# P28 / P29 GitHub CI execution report

Date: 2026-10-17.

**Status: `P28_P29_RELEASE_GOVERNANCE_APPROVED_AND_CI_VERIFIED` is NOT reached.** Local work is complete and
verified; the `git push` of the integration branches was **denied by the Claude Code permission classifier**
("Out-of-Place Publication") despite the owner's written authorization to push. I did not retry or work around
the denial. Consequently: no branch exists on GitHub, no draft PR was opened, **no hosted CI job ran**, and no
required-check configuration could be inspected. Nothing was merged, tagged, released, published or deployed.

## 1. Recorded owner decisions

The owner's reply was: "Approved. I have authorized: recording the approved governance decisions and implementing
the permitted security changes; creating local branches and commits following the verified Git integration plan;
pushing the approved integration branches to GitHub; opening draft pull requests and running hosted GitHub
Actions; fixing scoped CI failures and independently verifying the resulting changes." It names no approver, no
decision numbers and supplies none of the values the packet left blank. It is recorded (unsigned) in
`docs/P28_P29_OWNER_DECISIONS_003.md` as approval of the packet's recommended options, limited to what the packet
proposed. The independent reviewer rightly noted that OD-1..OD-10 all rest on this blanket reading; OD-10 is
recorded as "accepted under the blanket reading; owner to confirm before any pilot".

| Item | Recorded status |
|---|---|
| OD-1 D14 / A.2 | approved, **conditional** on the production-equivalent OIDC matrix (not run) |
| OD-2 F-2 | layered design direction approved; **numeric quotas not approved**; quota layer implemented but inactive |
| OD-3 retention | structure approved; **periods and owners not supplied**; read-only report only |
| OD-4 / OD-5 / OD-6 | approved; implemented (verified log identity; `ARE_ALLOW_DEV_HEADER`; duplicate headers -> 422) |
| OD-7 Git | local commits per the plan; internal reports committed with local paths replaced by placeholders |
| OD-8 CI | push and **draft** PRs authorized (blocked by the permission system); no GitHub setting changes authorized |
| OD-9 roles/versions | **not supplied**; nothing assigned |
| OD-10 | accepted under the blanket reading; owner to confirm before the pilot |
| OD-11 pilot/calibration | **not supplied**; SG-1..SG-6 remain NOT SATISFIED; no pilot, no model, no spend |

## 2. Deferred decisions
Numeric quotas and the authentication-failure counter / trusted-proxy range (OD-2); retention periods, class
owners and any deletion mechanism (OD-3); release roles, versions, platform identification (OD-9); pilot owner,
calibration provider/model/spend, pilot authorization (OD-11); required-check changes in GitHub (OD-8);
production-equivalent OIDC matrix (OD-1 condition).

## 3. Local commits and branches (not pushed)
Base: SDK `7aa6883` (`origin/main`), platform `88d0e58` (`origin/main` moved from `d606293` by a docs-only merge;
the plan was rebased onto it). Created in new worktrees; the original working trees are unchanged (SDK 43,
platform 53 status entries).

SDK worktree `agent-reliability-integration`: `final/p28-sdk-http-exporter` = `20cdafb` feat(p28) HTTP exporter,
`a388202` ci hardening; `final/p29-experimental-judge` = those two plus `7cb2586` feat(p29) judge and `6d32bb5`
docs/reports (sanitized).
Platform worktree `agent-reliability-platform-integration-pr`: `7b5aa81` PC-1 (`final/p28-pc1-machine-auth`),
`75a0451` PC-2 (`final/p28-pc2-ingestion-v2`), then `317e0e6` tests, `cd68872` CI, `954a061` governance policies,
`f0aa3cc` reports/decision records (`final/p28-integration-tip`).
Verification of committed trees: each cumulative stage passes ruff, mypy and the unit suites (SDK 904 / 912 /
1,643 + 6 skipped / 1,648 + 1 skipped; platform 793 / 1,157 / 1,158 / 1,161 / 1,187 / 1,187); the tip trees equal the
final candidates except the sanitized internal documents (SDK 26, platform 12) and the rehashed baseline
manifest, plus 11 `docs/audits` files from the newer platform base. No secrets, executable-bit additions, CRLF,
caches or local paths were found in committed files (bare marker descriptions excepted).

Planned pull requests (not opened) - the workflows only run for pull requests whose base is `main`, so each PR
is cumulative against `main`: platform P-1 `final/p28-pc2-ingestion-v2` (PC-1 + PC-2) and P-2
`final/p28-integration-tip` (all six commits); SDK S-1 `final/p28-sdk-http-exporter` and S-2
`final/p29-experimental-judge`. Stacked PRs against non-`main` bases would not trigger CI.

## 4. Draft PR URLs, Actions runs, required checks
None. **Hosted CI: NOT RUN.** Required-check configuration: not inspected (no remote access granted for it);
administrator action still needed for `postgres-slow` (decision D3) and, for the SDK, `reference-vectors`.

## 5. Security-policy implementation evidence
* DR-4 `api/logging.py`: verified organization, principal, actor type and credential id from the authentication
  context (none in `dev_header` mode), asserted headers renamed `asserted_*` and JSON-quoted (message forging
  fixed after review), request ids restricted to `[A-Za-z0-9._-]{1,128}`.
* DR-5 `config.py`: `ARE_ALLOW_DEV_HEADER`; outside `local` or on a non-loopback `ARE_HOST` it is required;
  production still requires OIDC even when set; startup warning in `create_app`; CI sets the flag; the TEST
  compose passes it through (default false) and `.env.example` ships it commented out.
* DR-6 `reject_duplicate_credential_headers` (app-level dependency, 422 before authentication on every route
  except `/health/*`).
* DR-2 `api/quota.py`: per-credential / per-organization fixed-window quota after authentication; defaults 0 =
  inactive; the pre-authentication limiter is unchanged (its failure-counter layer needs numbers).
* DR-3 `retention_report.py`: SELECT-only report; test asserts nothing is deleted and the source holds no removal
  statements.
* Phase 3: tests show a pilot-shaped gate never returns ALLOW when the judge measurement is unavailable
  (unknown-only, execution-failures-only, no evidence, failure with unavailable health) and that `on_no_data`
  has no default and cannot be `allow` (SG-6 in the contract). P7 semantics unchanged.

## 6. Regression results (local, end state)
SDK Python 3.11: ruff clean, 1,648 passed + 1 skipped (3.12/3.13 and build/artifact checks last run on the
previous end state, 1,646 + 1, exit 0; only documentation and the checker changed since in the SDK tree).
Platform: ruff, format, mypy clean; `pytest -m "not integration"` 1,187 passed; PostgreSQL 16 and 17
`integration and not slow` 534 passed + 1 expected failure each; `integration and slow` 3 passed each; clean
`alembic upgrade head` (head `0019`). Own mutants of the new policy code (verified fields from headers,
dev_header reported as verified, production accepting dev_header, quota off-by-one, duplicate check limited to
one header): all killed by the final tests.

## 7. Independent review of the new work
`P28_P29_GOVERNANCE_EXECUTION_REVIEW.md` (separate reviewer): APPROVE_WITH_REQUIRED_CORRECTIONS, 0 BLOCKER, 0 HIGH,
3 MEDIUM, 6 LOW, 2 INFO. Remediated: weak/vacuous tests (rewritten; mutants now killed), log-message forging
(values JSON-quoted), OD-10 over-reading (re-labelled), sanitizer altering marker descriptions and leaving Windows
paths (fixed), missing startup warning and the pre-set acknowledgement (fixed), `/health/*` rejection (exempted),
quota/retention scope notes (stated), commit-message omission (added). The remediation was verified by tests and
mutants by me; it was **not** re-checked by a second independent verifier. Reviewer INFO items (500 responses leave
no request log line; `ARE_HOST` is not seen when only `uvicorn --host` is used) are pre-existing/documented.

## 8. Remaining production gates
Production-equivalent OIDC matrix (D14 condition); owner values for quotas and retention; trusted-proxy range on
the target stack; platform-first release evidence; release roles and versions; hosted CI green incl.
`postgres-slow`; required-check configuration; PostgreSQL 18, Windows, real forward proxy, connect-timeout,
`pip-audit`, container build.

## 9. Remaining P29 pilot gates
SG-1..SG-6 NOT SATISFIED (no pilot, no owner, no evidence); calibration not authorized; OD-10/OD-11 owner
confirmation.

## 10. Exact next authorized action
Allow the push, or run it yourself:

```bash
git -C <workspace>/agent-reliability-integration push -u origin final/p28-sdk-http-exporter final/p29-experimental-judge
git -C <workspace>/agent-reliability-platform-integration-pr push -u origin final/p28-pc2-ingestion-v2 final/p28-integration-tip
```

then open draft PRs against `main` (SDK: `final/p28-sdk-http-exporter`, `final/p29-experimental-judge`;
platform: `final/p28-pc2-ingestion-v2`, `final/p28-integration-tip`), read the Actions results, and fix scoped
failures. The permission rule that blocked the push must be added by the user in Claude Code settings; I will not
change it.

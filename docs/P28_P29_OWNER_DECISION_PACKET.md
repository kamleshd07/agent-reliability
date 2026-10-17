# P28 / P29 owner decision packet

**Update 2026-10-17: the owner replied "Approved"; the recorded outcome per item is in `P28_P29_OWNER_DECISIONS_003.md`. The text below is the packet as originally issued.**

Only genuine unresolved decisions are listed. Nothing here is approved; every "Approval wording"
is a proposal for the owner to adopt, edit or reject, and the approver identity and date are left
blank on purpose. Where an earlier decision already covers a point, it is noted and not asked again.

**Already decided (not asked again):** F-4 (exporter submodules INTERNAL, no Beta class), F-9 (sdist
exclusions), L2 (TLS-failure streak); the 2026-10-11 relays (PC-2 scope, C, D, K2, M1, G1 platform-first
release, D07, E5 `lock_timeout 2s`, X1-X3, M-b, I-1, ADR-0028); the 2026-10-16 relays (D1-D4,
including the required `postgres-slow` check); P29-D09 (experimental judge, with safeguards before
pilot use) and P29-D10 (customer-local calibration, no enforced threshold). Details and the draft
decision records are in `P28_GOVERNANCE_DECISION_RECORDS.md` (platform tree, `docs/roadmap/P28/`).

Recommended answer for every item is the first option. A single reply such as "approve OD-1 to OD-9
as recommended; OD-10 and OD-11 deferred" is sufficient if the approver and date are stated.

| # | Decision | Needed before |
|---|---|---|
| OD-1 | D14 / ADR-0023 Appendix A.2 | platform release |
| OD-2 | F-2 layered rate limiting | platform release (design direction); implementation after |
| OD-3 | Retention structure and periods | production use at volume |
| OD-4 | Verified identity in logs | platform release |
| OD-5 | `dev_header` outside production | platform release |
| OD-6 | Duplicate headers | platform release |
| OD-7 | Git integration authorization | any commit |
| OD-8 | Hosted CI authorization and required checks | merge |
| OD-9 | Release roles and versions | any release |
| OD-10 | Measurement health and the P7 gate | pilot |
| OD-11 | Pilot roles, calibration and pilot authorization | pilot |

---

## OD-1 D14 / ADR-0023 Appendix A.2 (evidence POST dual-mode authentication)

* **Recommended:** approve as implemented, conditional on the mixed-credential matrix passing on a
  production-equivalent OIDC deployment before the first production release.
* **Alternatives:** approve with changes; reject and keep the route human-only (the SDK exporter then
  cannot authenticate in OIDC mode).
* **Consequences:** records the authority basis for an authentication change on the primary ingestion
  route; a machine bearer wins over a session cookie. The condition is not yet met (no real identity
  provider was used).
* **Approval wording:** "I approve ADR-0023 Appendix A.2 (D14) as implemented in the integrated PC-1 +
  PC-2 tree, on the condition that the mixed-credential matrix described in the draft passes on a
  production-equivalent OIDC deployment before the first production release. Approver: ____ Date: ____"

## OD-2 F-2 pre-authentication rate limiting

* **Recommended:** adopt the layered design (edge protection; trusted client address through an
  explicit proxy allow-list; authentication-failure counting per address; post-authentication
  per-credential and per-organization token buckets), with quotas tuned from measured traffic. Today's
  limiter lets an invalid-bearer flood starve valid callers behind the same address, and behind a load
  balancer the whole fleet appears to share one address unless forwarded headers are trusted explicitly.
* **Alternatives:** keep the per-address limiter; rely on the edge only.
* **Consequences:** removes the tenant-wide denial of service; adds state, configuration and an
  accounting path; the documented `429`/`Retry-After` shape is unchanged.
* **Approval wording:** "I approve the layered rate-limiting design in DR-2 as the target. Numeric
  quotas are to be proposed from measured traffic and approved separately. Approver: ____ Date: ____"

## OD-3 Retention

* **Recommended:** approve the structure in DR-3 (export first, partitioned removal, legal hold;
  evidence idempotency claims kept at least as long as the client retry horizon) and name the owner of
  each class. The periods in DR-3 (audit 13 months online, application logs 30 days, diagnostics 7 days)
  are **proposals**, not requirements; legal or compliance input, if any, is the owner's to supply.
* **Alternatives:** keep everything indefinitely; export and truncate ad hoc.
* **Consequences:** bounds storage (about 3.9 GB/day of audit rows at 100 events/s) and retained
  identifiers; needs a partitioning migration and an archive.
* **Approval wording:** "I approve the retention structure in DR-3. The periods are set as follows:
  audit ____, evidence ____, application logs ____, diagnostics ____. Class owners: ____. Approver: ____
  Date: ____"

## OD-4 Verified identity in request logs

* **Recommended:** log the identity verified by authentication (organization, principal, credential id)
  and rename or drop the client-asserted headers in logs; accept a client request id only if it matches
  a safe pattern.
* **Alternative:** keep logging the asserted headers.
* **Consequences:** attributable logs and audit rows; dashboards using the old field names must change.
* **Approval wording:** "I approve DR-4 option (a). Approver: ____ Date: ____"

## OD-5 `dev_header` outside production

* **Recommended:** option (c) of DR-5: allowed in `local`; in `test` only with an explicit
  acknowledgement setting; a non-loopback bind with `dev_header` also needs it; production unchanged.
  The earlier "refuse in every non-local environment" would break CI and the shared TEST smoke path
  (`test` is both) until those move to OIDC.
* **Alternatives:** refuse outside `local` (requires migrating CI and shared TEST first); keep
  production-only refusal.
* **Consequences:** removes accidental unauthenticated deployment of non-production environments.
* **Approval wording:** "I approve DR-5 option (c). Approver: ____ Date: ____"

## OD-6 Duplicate `Authorization` / `X-Organization-ID` headers

* **Recommended:** reject with `422` and the existing validation error shape before authentication
  (refines the earlier "400": every other malformed-header case is already `422`, so no new status code
  or SDK classification is needed).
* **Alternatives:** keep first-wins; last-wins.
* **Consequences:** a proxy that appends a second header fails visibly instead of silently changing
  which credential is evaluated.
* **Approval wording:** "I approve DR-6 option (a) using status 422. Approver: ____ Date: ____"

## OD-7 Git integration authorization

* **Recommended:** authorize creating **local** worktrees, branches and commits following
  `P28_P29_GIT_INTEGRATION_PLAN.md` (platform groups 1-5, SDK groups 1-4), without pushing. Decide at
  the same time: (a) whether the internal reports are committed (they are excluded from the sdist) and
  whether their absolute local paths are replaced by placeholders first (recommended: yes, mechanical
  substitution recorded in the commit message; reviewer verdict text unchanged); (b) whether two
  CRLF reviewer documents are normalized to LF (recommended: yes).
* **Alternatives:** commit only the code groups and keep the reports out of Git; or authorize pushing
  and pull requests in the same step.
* **Consequences:** produces reviewable history; nothing leaves the machine.
* **Approval wording:** "I authorize local commits for the groups in the Git integration plan, with
  decisions (a) ____ and (b) ____. No push, pull request or merge is authorized by this. Approver: ____
  Date: ____"

## OD-8 Hosted CI authorization and required checks

* **Recommended:** after OD-7, authorize pushing the branches and opening **draft** pull requests so
  GitHub Actions can run; afterwards set the required checks (platform: the existing jobs plus
  `postgres-slow`, already decided; SDK: `quality`, `test` (three Pythons), `artifacts`,
  `reference-vectors`). Optionally add a PostgreSQL 16 job (the platform documentation says PostgreSQL
  15+ but CI runs 17 only; 16 was verified locally).
* **Alternatives:** run CI only on a fork; defer.
* **Consequences:** produces the hosted evidence the target milestone requires; branch protection is
  GitHub configuration changed by a repository administrator, not by this repository.
* **Approval wording:** "I authorize pushing branches ____ and opening draft pull requests so CI can
  run. Required-check changes are ____. Approver: ____ Date: ____"

## OD-9 Release roles and versions

* **Recommended:** name the people for the roles in `P28_P29_RELEASE_MANAGEMENT_RECORD.md` (platform
  release owner, SDK release owner, independent reviewer, security/governance approver, rollback owner,
  OIDC TEST environment owner); release the SDK in two steps (P28-only minor first, the experimental
  judge in a later minor after the pilot-gate decision); identify the platform release by git SHA and
  image digest without a package version bump.
* **Alternatives:** one combined SDK release; introduce platform SemVer and tags.
* **Consequences:** a reviewer or approver may not be a design or implementation author; reviewer
  subagents are not these roles.
* **Approval wording:** "Role assignments: ____. SDK versions: ____ then ____. Platform identification:
  ____. Approver: ____ Date: ____"

## OD-10 Measurement health and the P7 gate

* **Finding (tested against the real platform):** an `unavailable` run health changes an indicator's
  `measurement_state`, but the P7 gate reads only coverage and burn-rate policy facts, so a judge
  failure does not by itself block or warn; only the condition's `on_no_data` setting reacts to the
  absence of determinate results.
* **Recommended:** keep the current semantics for the pilot, state them in the pilot report (SG-2/SG-4),
  and set `on_no_data` explicitly (SG-6). Do not add a new gate condition type without a design cycle.
* **Alternative:** commission a gate condition on measurement health.
* **Approval wording:** "I accept that measurement health is not a gate input for the pilot. Approver:
  ____ Date: ____"

## OD-11 Pilot roles, calibration and pilot authorization

* **Recommended:** assign the pilot owner and the SG roles; approve the **proposed** calibration
  dataset specification and thresholds in `P28_P29_CALIBRATION_PREPARATION.md` (or amend them);
  authorize the first calibration run on a synthetic dataset only, naming provider, model label, call
  and spend limits; do **not** authorize a customer pilot until SG-1..SG-6 are evidenced with
  `scripts/p29_pilot_report_check.py`.
* **Alternatives:** local-model calibration only; defer the pilot.
* **Consequences:** no external model, charge or customer content is used without this authorization.
* **Approval wording:** "Pilot owner: ____. Calibration run 1 authorized with provider ____, model label
  ____, at most ____ calls and ____ spend, on the synthetic dataset only. Customer pilot: not authorized.
  Approver: ____ Date: ____"

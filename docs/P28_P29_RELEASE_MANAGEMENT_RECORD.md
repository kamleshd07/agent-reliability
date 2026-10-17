# P28 / P29 release management record (draft; nothing is released or assigned)

Status: **DRAFT.** No person holds any role below, no version is assigned, no tag exists, nothing
is published or deployed. Role names come from the P28 approval package (Decision F, all
`PENDING_ASSIGNMENT`) and from the P29 safeguards document; nobody is named here because nobody has
been named by the owner.

## 1. Roles

| Role | Holder | Needed for | Source of the role |
|---|---|---|---|
| Platform release owner | **UNASSIGNED** | approving the platform build list, migration, deploy | P28 Decision F ("P28 milestone owner", "PC-1/PC-2 platform implementation owner") |
| SDK release owner | **UNASSIGNED** | version, tag, PyPI publication | P28 Decision F ("SDK implementation owner"); `docs/RELEASING.md` |
| Independent reviewer | **UNASSIGNED** | release review; must not be a design or implementation author. A reviewer subagent is a review mechanism, not this role | P28 Decision F |
| Security / governance approver | **UNASSIGNED** | DR-1..DR-6 and the security-sensitive release gates. A reviewer subagent must not be treated as this approver | P28 Decision F ("Engineering-governance approver") |
| Pilot owner | **UNASSIGNED** | SG-1..SG-6 sign-offs, calibration authorization, pilot authorization | `docs/P29_PILOT_SAFEGUARDS.md` |
| Rollback owner | **UNASSIGNED** | deciding application rollback or roll-forward after PC-2 | `docs/runbooks/rollback.md` (role not named there); P28 Decision G |
| OIDC TEST environment owner | **UNASSIGNED** | the production-equivalent OIDC matrix for D14 | P28 Decision F |
| Application operations owner (customer) | customer-side | SG-5 alert wiring | `docs/P29_PILOT_SAFEGUARDS.md` |

Evidence that a role is assigned: a written designation by the project owner stating the role, the
person and the date, stored with the approval record. Until then every sign-off field stays blank.

## 2. Existing versioning conventions

* **SDK** (`agent-reliability`): Semantic Versioning per `docs/VERSIONING.md`; the single source is
  `agent_reliability.__version__` (currently `1.2.1`); tags `v1.0.1`, `v1.1.0`, `v1.1.1`, `v1.2.0`,
  `v1.2.1` exist; the release workflow requires the tag to equal `__version__` and, after this
  milestone's workflow hardening, the tagged commit to be on `main`. `docs/RELEASING.md` is the
  maintainer procedure. Experimental APIs "may evolve in a minor release with prominent notes".
* **Platform** (`agent-reliability-platform`): package version `0.1.0.dev0`, no tags, no changelog.
  Deployments are identified by git SHA (`ARE_GIT_SHA` build argument, returned by `/health/live` and
  `/health/ready`) and the image digest; `docs/runbooks/production-deploy.md` records release as git
  SHA, image digest, migration head, time, operator and smoke result.

## 3. Version recommendations (RECOMMENDED, not assigned)

| Artifact | Recommendation | Reason |
|---|---|---|
| SDK, P28 exporter only | next **minor**, e.g. `1.3.0`, built from the P28-only commit group | additive optional extra and new internal modules; existing stable contracts unchanged (`docs/VERSIONING.md`) |
| SDK, P28 + experimental judge | the following **minor**, e.g. `1.4.0`, only after the pilot-gate decision | the judge is a new experimental namespace that the package cannot un-ship once published; keeping it out of the first release lets P28 proceed without P29's pilot gates |
| Platform | **no package version bump** for this milestone; identify the release by git SHA and image digest | no platform version convention exists and the release record already uses SHA and digest; the CI container job asserts `0.1.0.dev0`. Introducing platform tags or SemVer is an owner decision |

If the owner prefers one combined release, the combined artifact must still be distinguishable (see
section 4); the cost is that P28 then waits for the P29 decision. The exact numbers above are
placeholders until the SDK release owner assigns them; the date is assigned only when cutting the
release (`docs/RELEASING.md`).

## 4. Keeping P28-only and P28 + P29 artifacts distinguishable

1. Different version numbers (section 3).
2. Different content, verified mechanically: the P28-only wheel and sdist contain no
   `agent_reliability/experimental/` files; the combined artifacts contain 26 judge files.
   `scripts/verify_release_artifacts.py` checks the contents of whichever tree it runs in
   (P28-only 199 sdist / 51 wheel files; combined 272 / 77 at the time of this milestone).
3. Different documentation: `CHANGELOG.md` lists the judge under its own "(P29, experimental)"
   heading; `docs/GA_CONTRACT.md` lists the exporter as INTERNAL and the judge as EXPERIMENTAL;
   `docs/VERSIONING.md` names the experimental namespace.
4. Different build tree: PR 1 / the first release is built from the commit group "P28 exporter" and
   "CI hardening" only (`docs/P28_P29_GIT_INTEGRATION_PLAN.md`); the judge arrives in a later,
   separately identifiable commit group.
5. After publication, verify in a clean environment: `pip download agent-reliability==<v>` then
   list the wheel; `python -c "import agent_reliability.experimental.judge"` must fail for the
   P28-only version and succeed for the combined one.

## 5. Platform-first release requirement (decision G1 / D07, recorded 2026-10-11)

The SDK must not be released until every platform instance serves PC-2 and PC-1. Order (from the
approval package, section 1): (1) guarded expand migration `0019`; (2) PC-2 platform code; (3) PC-1
dual-mode `POST /api/v1/evidence/runs` authentication; (4) SDK exporter release, only after steps
1-3 are verified in production-equivalent OIDC mode (`dev_header` is not evidence).

| Step | Evidence required | How it is proven |
|---|---|---|
| Migration | every target database is at head `0019`; backup verified recent; `alembic heads` is single and `alembic check` clean | `alembic current` output per database; `docs/runbooks/production-deploy.md` migration step |
| PC-2 and PC-1 code | every running instance reports an approved `git_sha`; `unknown` fails | `/health/live` and `/health/ready` per instance compared with the approved build list |
| Production-equivalent OIDC | the mixed-credential matrix of DR-1 passes against the real identity configuration | recorded test run (not executed in this milestone) |
| Required CI | `postgres-slow` and the other required checks green on the release commit | hosted CI run (not yet run) and branch-protection setting |
| Rollback acknowledgement | the rollback owner has read: PC-2 is not rollbackable once a v2 SDK is released (migration downgrade refuses while v2 rows exist); application rollback below PC-2 pauses every released v2 SDK until the application calls `resume_schema()` | written acknowledgement; `docs/roadmap/P28/P28_APPROVAL_001_DECISION_PACKAGE.md` Decision G |

## 6. Release checklist skeleton (to be completed by the assigned owners)

Platform: roles assigned; DR-1..DR-6 decided; commit groups reviewed and merged in order; CI green
including `postgres-slow`; image built once and recorded by digest; migration rehearsed on a
production-like copy (lock timeout `2s` is an unvalidated starting value); deploy through the
protected environment; smoke; record the release. SDK: platform step complete; `__version__`,
changelog and date set in the release commit; CI green on Python 3.11, 3.12, 3.13; tag created from
the exact commit on `main`; release workflow builds once and publishes through the protected `pypi`
environment; post-publication verification as in `docs/RELEASING.md`.

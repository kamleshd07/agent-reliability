# Session 4 owner decisions (P29 judge calibration and evidence admission)

Recorded 2026-10-22. Provenance: the project owner's message in the working session ("Session 4: P29 Owner Decisions and Final Merge Readiness"), which
names each decision below and its constraints. The message is unsigned and names no approver; no approver identity or timestamp is invented. These
decisions authorise **documentation and merge-readiness assessment only**. None of them authorises production readiness, customer readiness, a release,
spending, or any change outside this documentation update.

## Relationship to P29-D10

P29-D10 ("customer-local calibration, no enforced threshold") is quoted in `P28_P29_CALIBRATION_PREPARATION.md` and other P29 documents, but its **primary record is
missing from the repository** (`P28_P29_GOVERNANCE_INDEPENDENT_REVIEW.md` F-14). This record does not reconstruct or reinterpret that original. OD-S4-1 is a **new**
owner decision that relates to the *referenced requirement* as follows: the SDK still does not impose a threshold of its own (the policy has no implicit
defaults; every threshold is supplied by the caller), and calibration remains customer-local; what is new is that a caller may express its thresholds as an explicit,
versioned, auditable policy object whose result is a status.

## Decisions

| ID | Decision | Status |
|---|---|---|
| OD-S4-1 | Caller-supplied calibration policy | **APPROVED** |
| OD-S4-2 | Model-backed evaluator admission | **APPROVED DIRECTION** (explicit choice in a future minor release); **this PR unchanged** |
| OD-S4-3 | Calibration status in Gentlity (platform) | **APPROVED FOR DESIGN ONLY** (Option 1, machine-readable provenance metadata) |
| OD-S4-4 | Provider-observed model version | **APPROVED FOR DESIGN; IMPLEMENTATION DEFERRED** |
| OD-S4-5 | Real-world calibration | **DEFERRED** |
| OD-S4-6 | Release and publication | **NOT AUTHORISED** |

### OD-S4-1: caller-supplied calibration policy (APPROVED)

* **Decision.** A calibration policy is supplied by the caller with explicit, versioned and auditable thresholds.
* **Rationale.** Safe thresholds depend on the customer's risk, the SLO the evidence feeds and the rubric; the library cannot know them. An explicit object makes the
  assumptions reviewable and the resulting status reproducible.
* **Constraints and how the current PR satisfies them.**
  * *Preserve the existing policy implementation:* unchanged by this update (`policy.py` is byte-identical to the independently validated version).
  * *Optional starting-point thresholds are not safety guarantees:* `CalibrationPolicy.starting_point()` is an explicit, caller-invoked preset; every decision carries
    `below_starting_point`; the documents state it makes no safety claim.
  * *Record policy identity and configuration in calibration evidence:* every `AdmissionDecision` carries the full policy configuration, its SHA-256 `policy_digest` and
    `below_starting_point` (`AdmissionDecision.as_dict()["policy"]`, `explain()`); the assessment itself is deliberately **policy-independent** (one measurement can be
    judged by several policies) and carries the dataset, fingerprint and measured counts. A test (`test_the_decision_records_the_policy_identity_and_configuration`) pins this.
  * *Preserve the requirement for verified, signed assessments:* a policy that is not `demonstration_only` cannot be constructed without `require_verified_integrity`; an
    unsigned or unverifiable assessment ends `uncalibrated`.
  * *Do not invent P29-D10:* see above.
* **Follow-up.** Policy versioning beyond the digest (named policy versions, a registry of approved policies) is a future design item; nothing is implemented for it here.

### OD-S4-2: model-backed evaluator admission (APPROVED DIRECTION; this PR unchanged)

* **Decision.** For this PR: keep backward compatibility, keep existing default behaviour, keep calibration gating **opt-in**, identify ungated model-backed evaluations as
  uncalibrated unless independently established otherwise, and never silently treat ungated results as trusted calibration evidence. For a future, separately reviewed change:
  require an explicit choice between calibrated admission and acknowledged `UNGATED` evaluation.
* **Rationale.** Making the choice mandatory is a breaking change to an Experimental API that should have its own review, deprecation path and release note.
* **Current state.** `IndicatorBinding(admission=None)` behaves exactly as before; bindings with `admission=UNGATED` are counted separately from unset ones
  (`explicitly_ungated` vs `ungated_model_backed`); the documentation states plainly that ungated judge outcomes are uncalibrated.
* **Follow-up (future minor release, separate review).** Require `admission` to be a gate or `UNGATED` for model-backed evaluators; provide a deprecation warning period; keep
  `UNGATED` visible in coverage and observer reports. **Not implemented here and no breaking change is made.**

### OD-S4-3: calibration status in Gentlity (APPROVED FOR DESIGN ONLY: Option 1)

* **Decision.** Prepare a design for carrying calibration status, assessment identity and judge behaviour identity to the platform as bounded, versioned,
  machine-readable provenance metadata.
* **Constraints.** The HTTP wire contract stays unchanged in this PR; the platform repository is not modified; `MeasurementHealth` is not overloaded; evaluator provenance and
  methodology comparability are preserved; explicit reasons for uncalibrated, expired, incompatible, insufficient and skipped evaluations; missing evidence is never PASS;
  historical SLO results are never silently rewritten; the design must serve multiple SDK languages and be vendor-neutral.
* **Deliverable.** `PLATFORM_PROPOSAL.md` is updated as a **design document only**. It is approval to prepare a future design-reviewed platform proposal, **not** to implement or deploy it.

### OD-S4-4: provider-observed model version (DESIGN APPROVED; IMPLEMENTATION DEFERRED)

* **Decision.** Explore an optional provider-observed model identifier/version in a separate reviewed change.
* **Constraints.** Distinguish provider-observed from customer-declared identity; never invent an observed version; preserve *unknown* when the provider returns none; evaluate
  backward compatibility before changing `ProviderReply`; do not modify the judge API in this PR.
* **Deliverable.** Design notes in `PLATFORM_PROPOSAL.md` section 6. No code change.

### OD-S4-5: real-world calibration (DEFERRED)

* **Decision.** Do not initiate real human-labelling campaigns, paid model calls, external provider-backed benchmarking, customer data ingestion, or promotion of P29 beyond
  Experimental. First prepare a plan.
* **Deliverable.** `FUTURE_CALIBRATION_PLAN.md` (a plan only: nothing in it has been executed or authorised). **No spending or external data transfer is authorised.**

### OD-S4-6: release and publication (NOT AUTHORISED)

* **Decision.** Do not merge the PR, create a tag, bump the SDK version for release, publish to PyPI, deploy hosted services, or modify AWS, IAM, EC2 or Cognito resources. Release
  ownership, versioning and publication require separate approval.
* **State.** PR #10 is a draft and unmerged; the package version is unchanged (1.3.0); no tag or publication exists.

D14 remains OPEN. Phase B remains NO-GO.

## What these decisions do not do

They do not make any judge calibrated, accurate or trustworthy; they do not authorise customer or hosted use; they do not change a stable API, wire contract, evaluator identity or
measurement-health meaning; and they do not authorise the platform, ingestion or SDK-language work that the design documents describe.

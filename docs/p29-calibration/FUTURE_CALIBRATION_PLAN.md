# Future real-world calibration: plan (NOT executed, NOT authorised)

Status: **a plan only.** Owner decision OD-S4-5 defers all real-world calibration ([OWNER_DECISIONS_S4.md](OWNER_DECISIONS_S4.md)). Nothing here has been run; it is not approval to start a
human-labelling campaign, to make a paid model call, to benchmark against an external provider, to ingest customer data, or to promote P29 beyond Experimental. **No spending or external
data transfer is authorised.** Existing preparation material: `docs/P28_P29_CALIBRATION_PREPARATION.md` (authorisation gate, dataset composition, labelling method, cost and privacy controls).

## 0. Gate: what must exist before anything starts

1. A named pilot owner and a named data owner; written authorisation naming the provider, model label, dataset, maximum spend and maximum number of calls.
2. For customer content: the data owner's written permission and a privacy review. Without it only synthetic data may be used (and synthetic data cannot calibrate under a human-provenance policy).
3. A cost estimate produced **before** any call, from the dataset size x repetitions x tokens at the provider's published price, recorded with its source and date, and approved.
4. A decision on the OD-S4-2 gating default and the OD-S4-3 platform design if the results are meant to feed SLO evidence.

## 1. Dataset ownership and governance

* One owner per dataset (an accountable role, not a person's name in the artefacts); a dataset id, version, licence and creation date in the manifest; the held-out split fixed and hash-pinned
  before any judge runs; never edited under the same version.
* Storage on the owner's side, access-controlled; not copied into this repository, tickets or the platform; retention and deletion decided by the data owner at the start.
* One example per source (conversation or document) to respect the independence assumption of the intervals; opaque case ids.

## 2. Genuine human labelling

* Rubric text and version fixed first; written guidance with examples that are not in the dataset.
* At least two independent labelers per case, role identifiers only, no sight of any judge output; labelers work on the same sanitised text the judge sees.
* Inter-labeler agreement measured first (the package reports mean pairwise agreement); if low, fix the rubric or guidance before looking at the judge.
* Cases the labelers cannot decide stay `unknown`/`unresolved`; they are reported as the indeterminate set, never forced.

## 3. Reviewer disagreement resolution

* Pre-registered rule per dataset: `majority` for odd panels, `third_reviewer` otherwise; every individual label kept; the adjudicator is a role independent of the first two.
* Disagreement statistics reported with the results (fraction adjudicated, fraction unresolved); a high unresolved fraction is a finding about the rubric, not a reason to widen thresholds.

## 4. Evaluation methodology

* Policy chosen and versioned **before** looking at results (starting point: `CalibrationPolicy.starting_point()`, adjusted only with a written rationale); sample sizes planned so that
  the policy's bounds are reachable (the policy coherence check enforces this at construction).
* Held-out split used once per configuration; every attempt counted (`heldout_attempt`); no tuning on it. Prompt or rubric tuning uses the train and calibration splits only.
* At least three independent repetitions per case; adversarial, borderline and ambiguous strata included and reported separately.
* Compare configurations with the disagreement taxonomy, not agreement alone; report shared errors.
* Results signed with a customer-held key; the record names the dataset manifest digest, the fingerprint and the policy digest.
* Re-calibration triggers: model change, rubric change, template/engine change (the fingerprint and drift indicators), expiry, or dataset staleness. Silent provider-side updates are a
  known blind spot until a provider-observed version exists (OD-S4-4).

## 5. Privacy controls

* Only the provider the data owner approved receives content, and only through the judge's own opt-in provider object; disable provider-side retention/training where offered and record the setting.
* Reports are content-free by construction; reviewers read misjudged cases locally.
* Run from a clean environment; credentials injected at run time, never stored in the repository or the artefacts.
* No raw prompts or responses in telemetry; no content in logs, tickets or the platform.

## 6. Bounded experiment budgets

* Hard limits set in the judge before the run: `JudgeBudget` (tokens/cost per window), `JudgeLimits` (timeouts, attempts), `max_concurrency` and `max_pending`; a dry run with a scripted provider first
  to confirm counts and the budget guard.
* Stop conditions: spend or call limit reached; provider failure rate above the owner's limit; any sign content left the approved boundary. A failed call is an execution failure, never a verdict.
* A written post-run record: spend vs estimate, calls, failures by class, and the assessment digest.

## 7. Exit criteria for any future promotion beyond Experimental (not a commitment)

Owner decision on promotion; an independent review of the real-data results; the OD-S4-2 explicit-choice change shipped; the OD-S4-3 platform design reviewed and (if adopted) implemented; the
OD-S4-4 observed-version design resolved; a documented support and deprecation policy.

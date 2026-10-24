# GO / NO-GO: P29 judge calibration and evidence admission (Session 4)

Nothing here is a production-readiness or customer-readiness claim. Every result is local: offline, scripted providers, SYNTHETIC data. No real model was
called, no spend occurred, no customer data was used, and nothing outside this repository was changed. D14 stays OPEN. Phase B stays NO-GO.

## Decision

| Question | Decision |
|---|---|
| Is the PR **ready for owner review**? | **GO.** All BLOCKER/HIGH findings of the four independent reviewers are closed; the validator's verdict is GO. |
| Merge-readiness of the **Experimental SDK slice** | **GO, subject to explicit owner merge approval** (not given, not inferred) **and green required CI on the exact final head.** The owner decisions are recorded; nothing outstanding blocks merging an Experimental, opt-in, default-unchanged slice. |
| Is the capability **customer-ready or hosted-ready**? | **NO-GO.** Not claimed (see limitations). |
| Real provider-backed calibration, real human labelling, spend, customer data? | **Not authorised and not performed.** |
| Publication, tag, release, deployment, infrastructure | **Not done and not authorised.** |

## Independent review record (reports unedited in [reviews/](reviews/))

| Review | Result |
|---|---|
| Architecture review of the design, three rounds, then conformance review of the built code | design: APPROVE_WITH_CHANGES -> confirmed (8 HIGH + 10 MEDIUM + 5 HIGH + 5 MEDIUM closed in the design); built code: no BLOCKER/HIGH, may go to owner review ([report](reviews/S4_ARCHITECTURE_REVIEW.md)) |
| Implementation review, re-check and confirmation | no BLOCKER/HIGH; mutation testing 107 + 44 mutants, every materially important survivor now killed, remaining survivors equivalent or platform-unreachable; final verdict APPROVE ([report](reviews/S4_IMPLEMENTATION_REVIEW.md)) |
| Adversarial security review and re-check | no BLOCKER/HIGH; 4 MEDIUM + LOW findings fixed or documented; re-check verdict APPROVE ([report](reviews/S4_SECURITY_REVIEW.md)) |
| Independent validation run (executed the tests itself) and re-validation | GO for owner review (not merge); one HIGH (a red lint check) found in round one and fixed (report (relocated; see docs/DESIGN_RECORDS.md)) |

Findings that mattered (all fixed unless stated): the health-style guard was fine, but the first design could not enforce "uncalibrated must not silently become
trusted evidence" by default (disclosed, owner decision OD-S4-2); a quadratic lookup made metrics take seconds (indexed); a tampered fingerprint crashed a decision
instead of yielding a status (validated at parse); a calibrating policy that did not require a signed record could be forged by editing the file (now refused);
dataset reads were unbounded before checking size and followed swapped paths (descriptor-based bounded read); leakage detection was evaded by zero-width
characters and punctuation (hardened; homoglyphs/paraphrase remain undetectable and are documented); an empty or missing other split made the leakage check vacuous
(now `insufficient_reference_evidence`).

## Evidence (validated independently at `58e4507`; later changes are listed under "Validation delta")

* SDK suite: **2056 passed, 1 skipped on each of Python 3.11, 3.12, 3.13** (validator, at `58e4507`); the author's final head runs **2061 / 1 skipped** on all three (five tests added since). Baseline before any change: 1802 / 1 skipped.
   ruff, ruff format, mypy: clean.
* Build, `verify_release_artifacts.py` (sdist + wheel install, HTTP/LangChain/OTel extras, strict downstream mypy), Node reference (76 + 74 vectors): pass.
  The sdist excludes the internal reports. A clean no-extras wheel install shows only extra-conditional requirements; the calibration package, schemas and a
  minimal end-to-end run work from the wheel alone. `dependencies = []`.
* Unchanged-behaviour suites (contract, compat, judge): 768 passed, 1 skipped; HTTP exporter: 469 passed; no stable module, wire, fixture or dependency changed.
* Platform `origin/main` (805b9c7) with this SDK installed: fixture parity true; SDK-facing platform tests 130 passed, 1 xfailed (validator, own PostgreSQL); the author's wider run
  (adding Session 2 operational suites) 140 passed, 1 xfailed.
* Offline walkthrough: deterministic, byte-identical across runs, no network. Benchmark: 12 000 cases x 3 runs: load 0.8 s, metrics 0.05 s, assessment 0.06 s, gate decision 0.8 ms, about 70 MiB.
* Required CI on the final head: see the PR checks and the final report (re-check before any merge).

## What exists now vs before

Existing (unchanged): judge adapter, coordinator, rubrics, prompt `jp1`, the local calibration harness and report/1. New: the `experimental.calibration` package (datasets, splits,
leakage and provenance checks, metrics with explicit undefined values and exact intervals, repeatability, judge-vs-judge analysis, fingerprint, caller-supplied policy and status,
drift indicators, HMAC-protected assessment, three published JSON Schemas), an additive opt-in admission hook in the judge package, an offline walkthrough, 255 new tests, and docs.

## Known limitations and remaining customer-readiness gaps

* **Gating is opt-in.** An ungated judge still records outcomes exactly as before and they are uncalibrated unless proven otherwise; they are only counted (`ungated_model_backed`). (OD-S4-2)
* **A skipped judge leaves run health healthy** (OD-10) and the platform sees only missing evidence, never why. Expiry or drift silently removes judge evidence unless the application alerts on `admission_skipped`. (OD-S4-3)
* **Model identity is a declaration.** A silent provider-side update is undetectable unless the model version is encoded in `model_label`. (OD-S4-4)
* **Provenance is an attestation; a signature proves integrity since signing, not that a real run produced the numbers.** No proof that labels are human; no authorisation model (upload vs approve is a platform or process control).
* **Leakage detection is exact/normalised only**; homoglyphs, paraphrase and rubric/few-shot copying are not detected; the leakage-scope criterion is satisfied by the presence of another non-empty split.
* **Statistics assume independent examples**; the held-out set is reused on every attempt (`heldout_attempt` only makes that visible). The `starting_point()` thresholds are an explicit starting point, not a safety claim.
* **Drift** covers fingerprint change, expiry and dataset age only; live decision-mix/failure-rate/error-rate statistics, a CLI and approval attestation are not built.
* **No real data.** The only dataset is synthetic; no real human labelling or provider-backed calibration was run. Hosted workflows, review UI and dataset collection are out of scope.
* The `ENGINE_REVISION` constant is manual (source pins make a forgotten bump fail CI but cannot prove a bump is sufficient).

## Owner decisions (recorded 2026-10-22: see [OWNER_DECISIONS_S4.md](OWNER_DECISIONS_S4.md))

| ID | Decision | Effect on this PR |
|---|---|---|
| OD-S4-1 | caller-supplied calibration policy: **APPROVED** (new decision; the missing P29-D10 record is not reconstructed) | none beyond documentation: the policy implementation is unchanged; decisions record the policy configuration and digest |
| OD-S4-2 | explicit choice (calibrated admission or acknowledged `UNGATED`) in a **future** minor release: **APPROVED DIRECTION** | none: default behaviour unchanged, gating stays opt-in, ungated judge evidence stays documented as uncalibrated |
| OD-S4-3 | machine-readable calibration provenance for the platform: **APPROVED FOR DESIGN ONLY** (Option 1) | [PLATFORM_PROPOSAL.md](PLATFORM_PROPOSAL.md) updated as a design document; no wire, platform or `MeasurementHealth` change |
| OD-S4-4 | provider-observed model version: **DESIGN APPROVED, IMPLEMENTATION DEFERRED** | design notes only; the judge API is unchanged |
| OD-S4-5 | real-world calibration: **DEFERRED** | [FUTURE_CALIBRATION_PLAN.md](FUTURE_CALIBRATION_PLAN.md) (plan only); no labelling, spend, provider run or customer data |
| OD-S4-6 | merge, tag, version bump, PyPI, hosted deployment, AWS/IAM/EC2/Cognito: **NOT AUTHORISED** | PR stays a draft; version stays 1.3.0 |

These decisions authorise documentation and merge-readiness assessment only. They do not authorise production, customer or hosted use.

## Focused safety recheck (after the owner decisions)

Each invariant is pinned by tests that run in the suite (35 selected by name passed together; the whole suite passes on 3.11, 3.12 and 3.13):

| Invariant | Evidence |
|---|---|
| Calibration does not establish correctness | status wording and `explain()` ("not a statement about production accuracy"); `test_the_admissible_claim_is_stated_conservatively`; `test_agreement_is_reported_beside_correctness_not_instead_of_it`; docs test against readiness/accuracy claims |
| Only eligible held-out evidence | `test_only_the_held_out_split_may_be_assessed`; `test_a_forged_non_heldout_split_never_calibrates_even_when_signed` |
| Synthetic data never represented as human | `test_synthetic_labels_never_calibrate_under_a_human_policy`; `test_a_demonstration_policy_can_only_demonstrate`; `test_synthetic_provenance_is_accepted_only_by_demonstration_policies`; `test_declared_provenance_must_equal_the_weakest_case` |
| Inconclusive never becomes admission | `test_upper/lower_bound_criterion_operators`; `test_not_provably_good_is_insufficient_evidence_not_failing`; `test_an_undefined_rate_is_inconclusive` (only status `calibrated` is admissible) |
| Unsigned or unverifiable assessment cannot satisfy a signed-evidence policy | `test_verified_integrity_policy_requires_the_hmac`; `test_forging_an_unsigned_record_cannot_calibrate...`; `test_a_calibrating_policy_must_require_verified_integrity`; `test_a_verified_integrity_policy_refuses_a_gate_without_a_key` |
| Tampered fingerprints rejected safely | `test_hostile_mutations_of_an_assessment_never_crash_the_parser_or_the_decision`; `test_a_fingerprint_whose_digest_does_not_match_its_components_is_refused` |
| Expired and incompatible assessments not admitted | `test_expiry_and_stale_datasets`; `test_a_different_model_declaration_or_behaviour_is_incompatible`; `test_a_calibrated_gate_lets_evidence_through_and_an_expired_one_stops_it`; `test_a_judge_with_other_behaviour_is_skipped_as_incompatible_not_admitted` |
| Ungated behaviour backward-compatible and documented | all pre-existing judge suites unchanged (547 passed); `test_an_allowed_call_behaves_exactly_like_an_unset_admission`; `test_ungated_counters_separate_unset_from_explicit_choice`; `test_an_uncalibrated_judge_is_skipped_when_gated_and_counted_when_not` |
| Skipped evaluations fabricate neither failure nor success | `test_a_skip_makes_no_provider_call_records_nothing_and_keeps_run_health` (no evidence, no failure record, run health HEALTHY) |
| Deterministic evaluators unchanged | no file under `evaluation/`, `domain/`, `sdk/` or any stable module differs from `origin/main`; evaluation/domain/sdk suites 276 passed |
| Stable SDK and platform wire contracts unchanged | no P28 fixture, wire schema, HTTP exporter or dependency change (`git diff origin/main..HEAD`: only `experimental/` source, scripts and the sdist exclude list); fixture parity with platform `main` true; HTTP/exporter/wire-selected tests 499 passed; contract suite 479 passed; Node reference 76 + 74 vectors |
| Policy identity recorded | `test_the_decision_records_the_policy_identity_and_configuration` |

**The three concepts stay separate** (and the documents say so): *agent outcome correctness* is what the evaluator said (PASS/FAIL/UNKNOWN, unchanged); *measurement health* is whether evidence collection was complete (unchanged; a skip changes nothing in it, and an inadmissible judge is not an
evaluation failure); *judge calibration status* is whether that evaluator's verdicts are trusted for a stated purpose (new, separate, SDK-local, never fed into the other two).

## Validation delta since the independent validator

The validator reviewed `58e4507`. Verified by `git diff 58e4507 <head>`: the commit after it changed only documentation, the four copied reviewer reports (byte-identical to the originals) and **one added test** (the `lstat` fallback test); no `src/`, `scripts/`, `examples/`, `.github/` or fixture file.
The final update adds documentation, three tests and **two lines to the sdist `exclude` list in `pyproject.toml`** (the new internal documents); that is a package-configuration change, so a **targeted independent recheck** was requested and is recorded in `reviews/S4_INDEPENDENT_VALIDATION.md`.

## Conditions on the GO for owner review

* Required CI must be green on the final head (check the PR); the validator observed the py3.11 job queued for over eleven minutes.
* The PR stays a draft until decisions 1 to 3 are made. Merge only with explicit owner approval.
* Do not describe any judge as calibrated, accurate or trustworthy on the basis of this work; the status is a statement relative to a stated policy and dataset.

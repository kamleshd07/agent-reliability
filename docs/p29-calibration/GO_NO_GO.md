# GO / NO-GO: P29 judge calibration and evidence admission (Session 4)

Nothing here is a production-readiness or customer-readiness claim. Every result is local: offline, scripted providers, SYNTHETIC data. No real model was
called, no spend occurred, no customer data was used, and nothing outside this repository was changed. D14 stays OPEN. Phase B stays NO-GO.

## Decision

| Question | Decision |
|---|---|
| Is the PR **ready for owner review**? | **GO** (conditions below). All BLOCKER/HIGH findings of the four independent reviewers are closed; the validator's verdict is GO. |
| May it be **merged**? | **Not decided here.** Merge needs explicit owner approval, the required CI on the final head, and the owner decisions below. |
| Is the capability **customer-ready or hosted-ready**? | **NO-GO.** Not claimed (see limitations). |
| Real provider-backed calibration, real human labelling, spend, customer data? | **Not authorised and not performed.** |
| Publication, tag, release, deployment, infrastructure | **Not done and not authorised.** |

## Independent review record (reports unedited in [reviews/](reviews/))

| Review | Result |
|---|---|
| Architecture review of the design, three rounds, then conformance review of the built code | design: APPROVE_WITH_CHANGES -> confirmed (8 HIGH + 10 MEDIUM + 5 HIGH + 5 MEDIUM closed in the design); built code: no BLOCKER/HIGH, may go to owner review ([report](reviews/S4_ARCHITECTURE_REVIEW.md)) |
| Implementation review, re-check and confirmation | no BLOCKER/HIGH; mutation testing 107 + 44 mutants, every materially important survivor now killed, remaining survivors equivalent or platform-unreachable; final verdict APPROVE ([report](reviews/S4_IMPLEMENTATION_REVIEW.md)) |
| Adversarial security review and re-check | no BLOCKER/HIGH; 4 MEDIUM + LOW findings fixed or documented; re-check verdict APPROVE ([report](reviews/S4_SECURITY_REVIEW.md)) |
| Independent validation run (executed the tests itself) and re-validation | GO for owner review (not merge); one HIGH (a red lint check) found in round one and fixed ([report](reviews/S4_INDEPENDENT_VALIDATION.md)) |

Findings that mattered (all fixed unless stated): the health-style guard was fine, but the first design could not enforce "uncalibrated must not silently become
trusted evidence" by default (disclosed, owner decision OD-S4-2); a quadratic lookup made metrics take seconds (indexed); a tampered fingerprint crashed a decision
instead of yielding a status (validated at parse); a calibrating policy that did not require a signed record could be forged by editing the file (now refused);
dataset reads were unbounded before checking size and followed swapped paths (descriptor-based bounded read); leakage detection was evaded by zero-width
characters and punctuation (hardened; homoglyphs/paraphrase remain undetectable and are documented); an empty or missing other split made the leakage check vacuous
(now `insufficient_reference_evidence`).

## Evidence (head 58e4507 validated independently; later commits add one test, documentation and the copied reviews)

* SDK suite: **2056 passed, 1 skipped on each of Python 3.11, 3.12, 3.13** (validator); the author's final head runs **2057 / 1 skipped** on all three (one test added).
  Baseline before any change: 1802 / 1 skipped. ruff, ruff format, mypy: clean.
* Build, `verify_release_artifacts.py` (sdist + wheel install, HTTP/LangChain/OTel extras, strict downstream mypy), Node reference (76 + 74 vectors): pass.
  The sdist excludes the internal reports. A clean no-extras wheel install shows only extra-conditional requirements; the calibration package, schemas and a
  minimal end-to-end run work from the wheel alone. `dependencies = []`.
* Unchanged-behaviour suites (contract, compat, judge): 768 passed, 1 skipped; HTTP exporter: 469 passed; no stable module, wire, fixture or dependency changed.
* Platform `origin/main` (805b9c7) with this SDK installed: fixture parity true; SDK-facing platform tests 130 passed, 1 xfailed (validator, own PostgreSQL); the author's wider run
  (adding Session 2 operational suites) 140 passed, 1 xfailed.
* Offline walkthrough: deterministic, byte-identical across runs, no network. Benchmark: 12 000 cases x 3 runs: load 0.8 s, metrics 0.05 s, assessment 0.06 s, gate decision 0.8 ms, about 70 MiB.
* Required CI on the final head: see the PR (the py3.11 job queued for a long time on the validated head; re-check before merge).

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

## Owner decisions required

1. **OD-S4-1** - amend P29-D10: a caller-supplied calibration policy (every threshold explicit; `starting_point()` is an optional preset, not a claim). The primary record of D10 is missing from the repository.
2. **OD-S4-2** - default gating: keep `admission=None`, or make an explicit gate/`UNGATED` choice mandatory for model-backed evaluators in the next minor release.
3. **OD-S4-3** - how calibration status reaches the platform ([PLATFORM_PROPOSAL.md](PLATFORM_PROPOSAL.md)); measurement health must not be used (OD-10).
4. **OD-S4-4** - additive `ProviderReply.model_version_observed` (touches the judge API).
5. Whether to authorise real human labelling, a real-provider calibration run (provider, model, dataset, data owner, budget and call limits), and promotion beyond Experimental.
6. Release roles/versions, tag and publication (none assigned or authorised).

## Conditions on the GO for owner review

* Required CI must be green on the final head (check the PR); the validator observed the py3.11 job queued for over eleven minutes.
* The PR stays a draft until decisions 1 to 3 are made. Merge only with explicit owner approval.
* Do not describe any judge as calibrated, accurate or trustworthy on the basis of this work; the status is a statement relative to a stated policy and dataset.

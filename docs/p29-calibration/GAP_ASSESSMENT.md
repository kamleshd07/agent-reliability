# P29 Session 4: gap assessment

Baseline: SDK `origin/main` at `b887999` (Merge of PR #9, P30 LangChain instrumentation; v1.3.0 is published and tagged);
platform `origin/main` at `805b9c7` (Merge of PR #64, Session 2 operational loop). Both repositories were fetched and
inspected on 2026-10-22. SDK baseline test run (Python 3.11, CI extras installed): **1802 passed, 1 skipped** (run by the author; the independent validator re-runs it).

P29 is **substantially implemented** as an Experimental namespace (`agent_reliability.experimental.judge`, ADR-0010,
`docs/P29_*.md`). This assessment lists what exists so that nothing is duplicated, and what is missing.

## Constraints that shape the work

| Source | Constraint | Consequence for Session 4 |
|---|---|---|
| ADR-0010, `docs/VERSIONING.md` | The judge namespace is Experimental: it may change in a minor release with notes; its compat snapshot (`tests/compat/test_experimental_judge_api.py`) and fixture manifest are guarded. | New code goes in a **new** Experimental namespace so the guarded judge `__all__`, rubrics, schemas and fixtures stay as they are (a small, listed set of additive names is added to the judge package, see ARCHITECTURE section 2). |
| P29-D10 (option A) | Calibration is customer-local; the harness enforces **no threshold** and never says "good", "ready" or "accurate". | The brief asks for a configurable policy with conservative defaults. This is a **tension with D10**; see owner decision OD-S4-1. The design keeps thresholds the customer's: a policy object whose every threshold is explicit, plus a clearly-labelled starting-point preset. |
| OD-10 (owner, 2026-10-17) | Measurement health is **not** a gate input; changing it needs a design cycle. | Calibration admission is a **separate layer**. It never edits `MeasurementHealth`, outcome meaning, or P28 wire members. |
| Stable HTTP contract rule (`CLAUDE.md`) | No wire change without an explicit version decision. | No wire, API or migration change is made. Platform integration is a separate proposal (section 8 of the architecture document). |
| SDK core | Zero runtime dependencies. | Stdlib only; no numpy/scipy. |

## Capability table

| Capability | Existing | Missing | Proposed action |
|---|---|---|---|
| **Judge evaluation** | `LLMJudge` / `SyncLLMJudge` (async and sync), prompt template `jp1` with untrusted-content framing and nonce, strict output parser, repair, retries, budgets (`JudgeBudget`), limits, five reference rubrics (uncalibrated examples), `JudgeCoordinator` / `EvaluationScope` (concurrency, sampling, recording gate), `StructuredOutputEvaluator`. Any fault becomes `EvaluationExecutionFailure`, never a result. | Nothing needed for the slice. | **Reuse unchanged.** |
| **Human-labeled reference data** | `gentlity.calibration-case/1` (case id, dimension, role-tagged parts, `human_label` pass/fail/unknown, `difficulty`, optional per-labeler `labels`, `source`); `load_cases` (JSONL, sha-256 of file, unique case ids); a synthetic known-confusion fixture. Preparation doc proposes dataset composition and human-review method. | Dataset **identity and version**; **splits** (train / calibration / held-out) and leakage checks; **label provenance** (synthetic vs human vs adjudicated); adjudication metadata; license/provenance statement; rubric binding; inter-labeler agreement (the preparation doc says "computed outside the harness"). | **Add** a versioned dataset manifest (`gentlity.reference-dataset/1`) and `reference-case/1` (superset of case/1, converts to `CalibrationCase`), loader with size bounds and strict parsing, split-leakage detector, inter-labeler agreement. |
| **Calibration metrics** | `run_calibration` (+async): content-free `CalibrationReport` (`gentlity.calibration-report/1`): confusion matrix (human x PASS/FAIL/UNKNOWN/FAILURE), false-negative/false-positive counts, over-confidence, abstention (overall and by human label), accuracy on answered, precision and recall per class, raw agreement and Cohen's kappa (judge vs human), accuracy by declared confidence level, Wilson 95% intervals, `insufficient_for_rates` flag below 12 cases, slices (clear+ambiguous / borderline / adversarial). | **F1**; **overall accuracy** with an explicit abstention rule; explicit **FPR / FNR** (and abstention-inclusive variants); **per-class support**; **coverage** of eligible examples; **explicit "undefined" markers with reasons** (today undefined rates are `null` with no reason); per-metric abstention treatment documented; metrics computed from a **neutral judgment table** (not only from a live judge run) so they are reproducible offline. | **Add** a pure metrics engine over `(human label, judgment)` tuples with an `Undefined(reason)` result type; reuse `wilson_interval` and kappa. Do not change report/1. |
| **Judge repeatability** | `repetitions=1..10`; `repeatability.changed_rate` (share of cases whose decision changed) by human label. | Per-example run records; pairwise run agreement; separation of **instability** from **failures** (a failed repetition is not a flip); stability **by fingerprint**. | **Add** `repeatability` over per-run judgments. |
| **Judge disagreement** | `compare_reports`: flipped cases, net FN/FP/UNKNOWN/FAILURE change, raw agreement and kappa between two reports; missing cases listed. | The brief's **taxonomy**: judgment disagreement vs evaluation failure vs missing evidence vs ground-truth ambiguity as separate, never-collapsed measures; **agreement is not correctness** (shared errors). | **Add** `compare_judges` with mutually exclusive, ordered categories; report shared errors. |
| **Uncertainty handling** | `UNKNOWN` outcome and the confidence floor (`min_confidence`); `judge_disagreement` reason when repeats disagree; Wilson intervals; small-dataset flag. | Policy use of abstention (coverage / abstention caps); distinguishing abstention on determinate vs human-unknown examples in the decision; **no** invented confidence scores. | **Add** abstention/coverage criteria to the policy. Confidence is only summarised by the *declared* categorical level that already exists; no ECE or probability is manufactured. |
| **Versioned provenance** | `EvaluatorIdentity(name = rubric_id, version = rubric_version, configuration_id = "<model_label>.jp1.mc-..")`; rubric content fingerprint; `template_id`; report records rubric id/version/fingerprint, model label, template id, configuration id, dataset id and sha-256. The identity grammar is the SDK/wire intersection. | A structured **judge fingerprint** separating provider, model id, model version, implementation (SDK) version, rubric id/version/fingerprint, template id and a template digest, configuration, and linking dataset version and calibration-report version; a rule that **display names never imply equivalence**. `model_label` is today a single caller-declared label. | **Add** `JudgeFingerprint` (canonical JSON + sha-256 digest, component-wise diff). It is **additive**; `EvaluatorIdentity` and the wire are untouched. |
| **Drift detection** | Only manual `compare_reports` between two runs. | Fingerprint/version invalidation; calibration expiry; dataset age. (Live decision-mix, failure-rate and error-rate shift indicators were evaluated and **deferred**: they need a statistical and product design and cannot be validated offline.) | **Add** deterministic offline drift **indicators** (never "significant"). No retraining, no provider switching. |
| **SLO integration** | Judge evidence is recorded through the normal evaluator path with `deterministic=False` and the judge identity; failures set run health `UNAVAILABLE` (SG-2); the Session 2 platform guard separates evaluator identities and refuses mixed methodology above its dominant-share limit. **Nothing consults a calibration status.** An uncalibrated judge's PASS/FAIL is recorded and counted like any other. | An **admission layer** that says whether a judge's evidence may feed SLO windows under a policy, and a way to apply it. | **Add** `assess_admission` (pure) and a generic, **opt-in** admission hook with a calibration gate; default behaviour unchanged and ungated judge evidence is counted. Platform use is a separate proposal (`PLATFORM_PROPOSAL.md`). See architecture section 8 and OD-S4-2. |
| **Privacy / security** | `CalibrationCase` refuses pickle/copy and redacts `repr`; reports are content-free; rubric roles only reach the provider; nonce/untrusted-content prompt framing; strict JSON loading; no network in the harness; `tests/security/test_experimental_judge_privacy.py` planted-canary tests; budgets and limits. | Dataset **poisoning** controls (hash pinning, provenance requirement, split discipline); manifest bounds; assessment/record **integrity digest**; approval attestation separated from execution; documented limits of LLM-judging-LLM; retention guidance; guarantee that new artefacts are content-free. | **Add** with tests (canary scan of every new artefact), and a threat model in the security document. |

## What this slice deliberately does not do

Hosted workflows, a human-review UI, automatic dataset collection, provider-backed benchmarking, any paid model call, platform
schema/API/migration changes, changes to `EvaluatorIdentity`, to the P28 wire, or to measurement-health semantics, and automatic
retraining or provider switching.

## Notes

* The primary record of owner decision P29-D10 is not in the repository (`P28_P29_GOVERNANCE_INDEPENDENT_REVIEW.md` F-14); its content is taken from the documents that quote it.
* The independent architecture review of the first draft is `S4_ARCHITECTURE_REVIEW.md` (kept outside the repository by the reviewer, copied unedited into `reviews/` at the end).

## Owner decisions raised by this assessment

* **OD-S4-1 (amends P29-D10).** D10 says the harness enforces no threshold. A calibration *policy* is requested. Proposal: thresholds
  are **always supplied by the caller** (no implicit defaults on the policy type); a named preset is provided only as a documented
  starting point; the word "calibrated" is defined as "meets the caller's policy on the named dataset" and never as an accuracy claim.
* **OD-S4-2.** Applying admission by default would change recording behaviour of existing users. Proposal: opt-in only in this slice.
* **OD-S4-4.** An additive `ProviderReply.model_version_observed` (judge API) would let fingerprints compare the model that actually answered.
* **OD-S4-3.** Conveying calibration status to the platform needs a wire/API design cycle (OD-10 also forbids feeding it into measurement health).

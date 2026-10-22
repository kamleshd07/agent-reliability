# Independent architecture review: P29 Session 4 (judge calibration and evaluation trustworthiness)

Reviewer: fresh-context independent reviewer. Read-only: no repo change, commit, push or external/paid call.
Subject: `docs/p29-calibration/GAP_ASSESSMENT.md`, `docs/p29-calibration/ARCHITECTURE.md` at SDK commit 5501b1f (base b887999);
platform reference 805b9c7.

## 0. What I read, ran, assumed

Read (whole or the cited ranges): both Session 4 documents; `experimental/judge/calibration.py` (1-596: CalibrationCase, load_cases, wilson_interval,
`_rate`, `_kappa`, `_slice`, `_build_report`, run_calibration/_async, compare_reports); `identity.py`; `judge.py`; `coordinator.py` (ReportKind,
EvaluationDisposition, IndicatorBinding, IndicatorCoverage, `_Counters`, `_prepare`, JudgeCoordinator); `core.py` (jp1 template, reason codes);
`_engine.py` (REQUESTED_TEMPERATURE); `values.py` (JudgePolicy, JudgeLimits); `rubric.py` fingerprint; `provider.py`; `schemas/calibration-case|report`;
`sdk/context.py` (health, record_evaluation_failure); `domain/measurement_health.py`; `tests/compat/test_experimental_judge_api.py`;
`tests/fixtures/p29/manifest.json`; `docs/P28_P29_OWNER_DECISIONS_003.md` (OD-10), `P28_P29_CALIBRATION_PREPARATION.md` (sections 2, 10),
`P29_PILOT_SAFEGUARDS.md`, `P28_P29_GOVERNANCE_INDEPENDENT_REVIEW.md` (F-03, F-14), `MEASUREMENT_HEALTH.md`, `SLO_SEMANTICS.md` (UNKNOWN policy), `VERSIONING.md`;
platform `domain/operations.py::decide_guard`, `docs/design/OPERATIONAL_RELIABILITY_LOOP.md` section 5, platform `on_no_data` model constraint.

Ran: only a stdlib Wilson-interval calculation (scratchpad script) to check the starting-point preset numbers. I did NOT run the SDK test suite, so
"1802 passed, 1 skipped" is unverified. I did not open `EVALUATE.md`, `P29_PILOT_RUNBOOK.md`, `ADR-0010` body, or platform ingestion code beyond grep of
`configuration_id` and the guard text, so provenance-ingestion claims rest on the design doc plus the guard source.

## 1. Verdict

**APPROVE_WITH_CHANGES.** The layering (new Experimental package, pure eligibility function, no wire/DB change, content-free artefacts) is sound and
the scope direction is right. But four design defects (a false partition claim, a wrong F1 rule, an incoherent preset, an unsound/unspecified fingerprint
and gate-fingerprint binding) and the gate's failure to meet the brief's headline requirement by default must be fixed in the documents before
implementation starts. Required changes are listed in section 6.

## 2. Findings (BLOCKER/HIGH first)

No BLOCKER. Eight HIGH.

### H-1 HIGH: the headline requirement is not met by default
Evidence: ARCHITECTURE 8 ("Unchanged by default", `eligibility=None` = today's behaviour); `coordinator.py:103-108` (IndicatorBinding has only indicator/evaluator/sampling);
`coordinator.py:158-175` and `_Counters.count` (`coordinator.py:272-299`) count an ungated judge PASS/FAIL like any other.
Why: the brief says an uncalibrated judge "must not silently produce trusted semantic SLO evidence". With the default, every existing and every new
user silently does exactly that, and the platform (which sees only name/version/configuration_id) can never tell. OD-S4-2 defers this to the owner,
but the design offers no interim mitigation, so the requirement is only met for customers who read the docs and opt in. Also the gate covers only
`JudgeCoordinator`; `LLMJudge` is documented to run "unchanged through `EvaluatorRunner.evaluate_async`" (`judge.py:3-4`) and `run.record_evaluation`,
which bypasses the gate entirely.
Change: (a) state plainly in the architecture that the requirement is satisfied only for gated bindings and list the bypass paths; (b) decide as a
labelled owner decision between "explicit choice required": `eligibility=` must be either a gate or an explicit `UNGATED` sentinel for model-backed
evaluators (acceptable on an Experimental API, changelog entry), and "default stays None" plus mandatory loud signals; (c) at minimum add an
`ungated_model_backed` indicator to `CoverageReport` and a documented SG checklist line, so ungated judge evidence is visible locally.

### H-2 HIGH: gate "current fingerprint" can be decoupled from the evaluator actually running
Evidence: ARCHITECTURE 8: `assess_eligibility(record, current_fingerprint, policy, now)` and `CalibrationGate(record, policy, clock)`; judge exposes no provider, model id or
version (`judge.py:140-141` keeps `_provider` private; `provider.py:93` only `provider_label`; `ProviderReply` has no model metadata, `provider.py:69-85`).
Why: if the fingerprint is a caller-supplied object, a gate can approve evidence from judge Y under judge X's calibration. If it is derived from the
evaluator, provider/model_id/model_version are still only caller declarations, so "digest equal => equivalent" proves consistency of declarations, not
of the model. The document claims the fingerprint "addresses the gap" of silent provider updates (section 8 last sentence); it does not.
Change: the gate must derive the fingerprint from the bound evaluator (rubric fingerprint, template digest, SDK version, configuration_id computed from the
evaluator) and take only the declared model fields as an explicit `ModelDeclaration` that is part of the gate and shown in every decision. Say in
the document that silent provider-side changes are detectable only by (i) expiry, (ii) re-calibration, (iii) optionally an additive
`ProviderReply.model_version_observed` that the judgment table records and the fingerprint compares (propose as OD, it touches judge API). Recommend
that callers put the model version in `model_label` because that reaches `configuration_id` and therefore Session 2's methodology check.

### H-3 HIGH: F1 undefined rule is wrong (hides the worst result)
Evidence: ARCHITECTURE 4.4 ("any F1 with undefined or zero-sum P+R ... Undefined").
Why: with TP=0, FP>0, FN>0, precision=0 and recall=0 are both defined and F1 = 2TP/(2TP+FP+FN) = 0. Reporting "undefined" for a judge that is
always wrong is the opposite of the brief's "no manufactured/silent" rule and flatters the judge.
Change: define F1 = 2TP/(2TP+FP+FN); undefined (`zero_denominator`) only when that denominator is 0. State that F1 ignores TN, carries no interval, and
is not a policy input.

### H-4 HIGH: the "partition" claim in 4.2 is false as written, and "coverage" contradicts the SDK's existing term
Evidence: ARCHITECTURE 4.2 ("These four plus `answered` partition |E|") with five listed rates and mixed denominators (`coverage`, `failure_rate`, `missing_rate` over |E|; `answer_rate`, `abstention_rate` over `judged`).
Only the counts partition: answered+abstained+failed+missing = |E|. The rates do not (answer_rate+abstention_rate = 1 over `judged`; coverage+failure_rate+missing_rate = 1 over |E|).
Also `coverage = judged/|E|` counts UNKNOWN as covered, whereas the SDK's `IndicatorCoverage.determinate_rate = determinate/attempted` with determinate = PASS+FAIL (`coordinator.py:176-190`) treats UNKNOWN as not determinate. An always-UNKNOWN judge has coverage 1.0.
Why: policy `min_coverage` (Wilson lower bound of that quantity) cannot catch abstention; customers will read it like the existing coverage figure.
Change: state the identity on counts only, and give each rate its denominator in a table. Rename: `verdict_rate = judged/|E|` (or `availability`) and add `committed_coverage = answered/|E|` (the selective-classification meaning) and use the latter in policy. Add explicit policy fields `max_failure_rate`, `max_missing_rate` (currently only implied through coverage).

### H-5 HIGH: `accuracy_end_to_end` and the abstention-inclusive pair exclude the very evidence the document says must not be hidden
Evidence: ARCHITECTURE 4.3: `accuracy_end_to_end = (TP+TN)/judged`; `miss_rate_fail = (FN+fail_abstained)/support_fail_judged`; `false_alarm_rate = FP/(pass judged)`. "judged" excludes FAILURE and MISSING.
Why: (1) "end to end" omits failed/missing evaluations, contradicting 4.2's own principle; failures are not random (refusals, input-limit, output-too-large concentrate on hard/adversarial inputs: `FAILURE_CLASS_NAMES`), so every conditional rate has selection bias that only a coverage criterion partly exposes. (2) `fpr`/`false_alarm_rate` and `fnr`/`miss_rate` are near-synonyms with different denominators and no naming rule; a policy author will confuse them. (3) `false_alarm_rate` is labelled abstention-inclusive but is just FP over a larger denominator.
Also the SLO-relevant error is abstention-inclusive: reliability = passed/determinate (`coordinator.py:180`) drops UNKNOWN, so an abstained defect inflates reliability exactly like a false PASS. Under `SLO_SEMANTICS.md` "UNKNOWN policy" the SLI may even count UNKNOWN as bad, so the judge's `rate_basis` must be consistent with the SLI's UNKNOWN policy, which the document never mentions. The starting preset does not set `rate_basis` at all.
Change: one naming scheme (`*_conditional` over answered; `*_effective` with explicit denominator over |E| incl. failures/missing as "no verdict"); make `accuracy_end_to_end` use |E|; default `rate_basis` for FNR to the abstention-inclusive variant; require the policy to declare which SLI UNKNOWN policy it assumes.

### H-6 HIGH: starting-point preset contradicts its own justification and is incoherent at its minimum sizes
Evidence: ARCHITECTURE 6: preset FNR upper <= 0.10, FPR upper <= 0.15, unstable upper <= 0.10, "restates ... CALIBRATION_PREPARATION section 10 more conservatively". Preparation section 10: FN <= 5%, FP <= 10%, repeatability <= 5%, precision(pass) lower >= 0.90, over-confident <= 20%, failure rate <= 2%, adversarial zero.
Why: (1) the preset is looser, not more conservative, on FN, FP and repeatability; the claim is false (verified by reading both). (2) Wilson upper bound for 1 error in 50 is 0.105 and 0 errors in 50 is 0.071 (my calculation): at `min_per_class = 50` and FNR upper <= 0.10, a judge passes only with zero false negatives; with 1 error the result is "uncalibrated (failing)" even though the data cannot distinguish a 2% judge from a 10% one. (3) The preparation criteria for over-confidence, provider failure rate and adversarial zero-defect are absent from the policy field list, although section 10 of the architecture says "a policy may require a zero-defect-pass criterion". 
Change: either adopt the preparation numbers (FN 5% requires n >= ~73 fail cases with zero errors, so raise min_per_class accordingly) or delete the "more conservatively" sentence and justify. Add policy fields for adversarial (zero FN/pass on `adversarial` slice), ambiguous commit rate, failure rate. Add a coherence check: construction warns/rejects when `min_per_class` cannot satisfy a bound even at zero errors.

### H-7 HIGH: status logic cannot tell "measurably bad" from "not provably good"; misclassifies the latter as failing
Evidence: ARCHITECTURE 6 items 3-4: "insufficient" is only size/provenance/leakage/kappa; any upper bound over the limit is `uncalibrated (metrics measured and failing)`.
Why: an upper bound above the threshold with a lower bound below it is inconclusive, not failing. Reporting it as "uncalibrated: failing" misleads the customer (the stated purpose) and will cause pointless re-labelling of a good judge or, worse, ratcheting thresholds up to make it pass.
Change: three-way test per criterion: `met` (bound inside), `violated` (the opposite bound is outside: e.g. Wilson lower bound of FNR already > limit), `inconclusive` (straddles). Any `violated` => `uncalibrated`; else any `inconclusive` => `insufficient_reference_evidence`. List per-criterion verdicts in reasons.

### H-8 HIGH: dataset provenance (the "synthetic is never human ground truth" rule) is a self-declaration and mixed datasets are undefined
Evidence: ARCHITECTURE 3: dataset-level `label_provenance` plus optional per-case `label_provenance`; 6: `accepted_label_provenance`.
Why: anyone can write `human_adjudicated` on a synthetic file; no rule says the dataset value is the weakest of the case values, no per-provenance counts, no minimum fraction. A 5% human / 95% synthetic dataset can be declared `human_single`. Nothing in the report shows how many cases carry multiple labeler entries. (The honesty rule is unenforceable by code; it can only be made visible and checkable for consistency.)
Change: dataset provenance is derived (weakest of case values), declared value must equal it or loading fails; report counts per provenance, number of cases with >= 2 labeler entries, and number adjudicated; add policy `min_human_fraction` and `min_multi_labeled_fraction`; document explicitly that provenance is an attestation, not proof, and print it ("attested") next to every status.

### M-1 MEDIUM: metrics may be computed from a caller-chosen run (cherry-picking)
Evidence: ARCHITECTURE 4 notation: outcome `o` is "first run, or the run named by the caller".
Why: choosing the run is a degree of freedom that can only inflate. Also `run_calibration` discards per-run detail (`calibration.py:481-503`; report keeps only `per[0]`, `calibration.py:~340`), so the "judgment table from that run" in the diagram (section 2) is not produced by existing code; the new package needs its own runner or private `_Call` access (`calibration.py:188`), which is not acknowledged. The doc also says the existing report "remains the way to run a judge" which is inconsistent with needing per-run rows, confidence level and failure class.
Change: fix run 0 as the evaluation run by default and record `run_index_used`, `runs_available` in the assessment; alternatively evaluate every run and use the worst. Specify the runner (new public function in the new package returning the judgment table) and its dependency on private judge internals (`_strict_loads`, `_jsonschema.validate`, `_NoCopy` are underscore-private, ARCHITECTURE 2 lists them as dependencies). Prefer promoting what is needed rather than reaching in.

### M-2 MEDIUM: inter-labeler kappa is invalid when the labeler pair varies
Evidence: ARCHITECTURE 4.7 ("between the first two labelers").
Why: Cohen's kappa assumes the same two raters across all items; "first two entries" per example mixes pairs when raters rotate (typical). Categories (pass/fail/unknown), prevalence sensitivity ("kappa paradox") and the interplay with adjudication (kappa is pre-adjudication) are unstated. `human_multi` without adjudication has no defined `human_label` rule (majority? unresolved?).
Change: require stable labeler ids and compute pairwise kappa only on a declared pair, or use a multi-rater statistic (Fleiss or Krippendorff alpha; both stdlib-able) or percent agreement only; report which pairs; define how `human_label` derives from `labels` and that labeler disagreement without adjudication is `unresolved`.

### M-3 MEDIUM: ground-truth ambiguity handling biases metrics and the eligible set is inconsistently defined
Evidence: ARCHITECTURE 4 notation (E = h in {pass,fail}) vs 4.5 (also adjudication `unresolved`); `ambiguous_decisive_rate` denominator not stated; policy has no ambiguity criterion.
Why: excluding every hard-to-label example from accuracy inflates it; a dataset whose hardest 30% is "unknown" yields rosy FNR. If an `unresolved` case still has a `human_label` of pass/fail it enters E under 4.1. "Over-confidence" calls a commit on an ambiguous case an error, which is not established (human indecision is not truth).
Change: define E as excluding `unresolved` explicitly; report `ambiguous_fraction` and give the policy `max_ambiguous_fraction`; rename to `commit_rate_on_ambiguous` with denominator; keep it informational unless the policy asks.

### M-4 MEDIUM: repeatability definition drops information and may be trivially stable
Evidence: ARCHITECTURE 4.8 ("run_failed if any run is FAILURE ... excluded from the stability numerator and denominator").
Why: a case with one failed run and two disagreeing others is excluded, hiding instability; failures correlate with hard cases. Identical calls at temperature 0 (`_engine.py:60`) to a caching provider are trivially stable; nothing records whether repetitions were independent. Mean-of-pairs weights differently when non-failed run counts differ.
Change: compute on non-failed runs when >= 2 remain, report `excluded_for_failures` count and a worst-case bound that treats them as unstable; record `repetitions` and the declared temperature/caching caveat; define the unit (cases) for the Wilson interval and state independence assumption.

### M-5 MEDIUM: Wilson usage assumptions and rounded comparison
Evidence: ARCHITECTURE 4.4, 5 ("canonical float rendering by rounding to 6 digits"), 6 ("compare the Wilson bound"); `wilson_interval` hard-codes z=1.96 (`calibration.py:65,146`); `_rate` rounds (`calibration.py:160-169`).
Why: (1) 1.96 two-sided is a 97.5% one-sided bound; fine, but must be documented as such. (2) Wilson assumes independent trials; clustered cases (same conversation/source, repeated runs) violate it, and the document never says so. (3) Wilson dips below nominal coverage near 0/1 at small n; for an acceptance bound, Clopper-Pearson is the conservative choice and is implementable with stdlib. (4) If policy compares rounded values, 0.1000004 rounds to 0.1 and passes a "<= 0.10" test it should fail. 
Multiplicity (risk 2): because `calibrated` requires the conjunction of all criteria, simultaneous testing does not inflate the false-acceptance probability (it can only raise false rejection), so no correction is needed for the status, but the drift indicators (each separately "indicated") do accumulate false alarms; non-overlap of two 95% intervals is a much stricter test (~0.5% level) than it looks. Document both. Held-out reuse (many fingerprints tried against one held-out set) is an uncontrolled multiplicity that is not addressed.
Change: compare unrounded values or exact integer arithmetic with a documented tie rule; state independence assumption and recommend one case per source cluster; evaluate Clopper-Pearson for policy bounds (or justify Wilson); record `heldout_assessment_count`-style attempt number in the assessment.

### M-6 MEDIUM: fingerprint design gaps
Evidence: ARCHITECTURE 3 `JudgeFingerprint`; `identity.py:66-87` (configuration_id = model_label, template, min_confidence, repeats, citations only); `values.py:242-253` (JudgeLimits: max_input_chars, max_output_tokens, max_attempts, repair_attempts); `tests/fixtures/p29/prompt_golden_jp1.json` (a test fixture).
Why: (1) Digest equivalence is sound for what it hashes, but it omits limits (input truncation/rejection and `max_output_tokens` change failure and abstention behaviour), `capture_reason`, retry/repair policy, temperature constant (covered only by implementation version). (2) "Template digest from a golden fixture": test fixtures are not shipped in the wheel (`pyproject` / compat test comment about artefacts not being distributed), so a runtime digest cannot read them; and a fixture digest does not prove the code renders it unless a test pins code to fixture (the architecture does not say it does). The golden text also depends on the rubric (`core.py:_system_message`). (3) A silent provider update is invisible (see H-2). (4) `sha256` over `implementation_version` makes every SDK patch release an `incompatible` event even when nothing relevant changed, causing needless re-calibration; or conversely the version string can be stale in editable installs.
Answer to risk 5: a digest of a rendered probe is a good proxy for the prompt text; a digest of a test fixture is not unless pinned by test.
Change: compute `template_digest` at runtime as sha256 of `build_prompt` rendered over a fixed internal rubric and fixed nonce plus the parser/engine constants (temperature, repair prompt), with a unit test asserting it equals the golden-fixture-derived value; add `limits_digest` and `capture_reason`; document the silent-update limitation; consider a separate `behaviour_digest` (template, parser, limits, config) versus `implementation_version` so a patch release does not force re-calibration.

### M-7 MEDIUM: status loopholes and policy binding
Evidence: ARCHITECTURE 6 (ordered status list, approval record {role, approved_at, assessment_digest}).
Why: (1) An assessment with `created_at` in the future (clock skew or forged) has negative age and never expires; no rule rejects it. (2) Nothing requires the dataset's `rubric` {id, version} to equal the assessed fingerprint's rubric or the dimension; assessing a judge on a dataset built for another rubric version is not in the `incompatible` or `insufficient` criteria. (3) Approval binds only the assessment digest, not the policy; loosening the policy afterwards keeps the approval valid. (4) Because every threshold is caller-supplied (OD-S4-1), `min_examples=1`, `max_fnr_upper=1.0` yields `calibrated`; the status word then launders a vacuous check. (5) Drift indicators `decision_mix_shift`, `failure_rate_shift`, `error_rate_change` never change status (section 7 last sentence), so a judge whose live failure rate explodes stays eligible although the coordinator already holds the counters. (6) `now` is injected; the gate's `clock` can be frozen. (7) Eligibility ignores which `dimension`/indicator the gate is bound to.
Change: reject `created_at > now + skew`; add rubric/dimension binding to `incompatible`; approval binds (assessment digest, policy digest); every `EligibilityDecision` and CLI output carries a policy summary and a `policy_below_starting_point` flag (not a block, so D10 is respected); document that drift is advisory and decide explicitly whether live failure-rate evidence may demote eligibility; require aware-UTC datetimes.

### M-8 MEDIUM: gate mechanics inside the coordinator are under-specified and the document contradicts itself on compatibility
Evidence: ARCHITECTURE 2 ("existing judge package, its `__all__`, schemas and fixtures are unchanged") vs 8/11 (new `IndicatorBinding.eligibility`, new `EvaluationDisposition` member, new report kind); `coordinator.py:61-70` (Literal and Enum), `272-299` (`count` has no `else`: an unknown kind is silently not counted), `675-724` (`_prepare` holds the scope lock while deciding skips); compat test only asserts `__all__` and listed enums/dataclasses (`test_experimental_judge_api.py` snapshots, no `EvaluationDisposition`/`IndicatorBinding` field snapshot found), so "snapshot entries updated deliberately" refers to snapshots that do not exist for these types. GAP_ASSESSMENT states new code goes in a new namespace "so the guarded judge `__all__` and fixtures stay byte-identical"; the judge source does change.
Why: ordering with sampling is unspecified: if sampling runs first, ineligible runs that were sampled out are counted as "unsampled", hiding the magnitude; the gate callback runs under the lock (must be non-blocking); the per-call fingerprint/digest must be cached; `attempted`/`reliability` must not include skips; `IndicatorCoverage.describe()` and a new counter are needed; adding an Enum member breaks exhaustive `match`. The judge package would import the calibration package (cycle) unless the hook is a protocol.
Answer to risk 4: changing Experimental types is allowed (VERSIONING, ADR-0010), but a wrapper evaluator cannot work: a wrapper that raises is recorded as an execution failure and sets run health UNAVAILABLE (`context.py:164-179`), and one that returns UNKNOWN records evidence. Better: a generic, calibration-agnostic hook in the judge package, e.g. `IndicatorBinding.admission: Admission | None` (protocol returning `allow` or `skip(reason_code)`), one generic disposition `SKIPPED_BY_ADMISSION` and report kind `skipped_admission` with a bounded reason string, implemented by `CalibrationGate` in the new package. This keeps calibration vocabulary out of the guarded enum and removes the import cycle. Specify: gate evaluated before sampling; counted in a separate `admission_skipped` counter; excluded from `attempted`; no provider call; add compat snapshots for the new fields in the same change.

### M-9 MEDIUM: missing-evidence semantics and customer visibility after a skip
Evidence: ARCHITECTURE 8; `decide_guard` (`operations.py:348-359`, comment "absence ... is never recovery"); OPERATIONAL_RELIABILITY_LOOP section 5; platform `on_no_data IN ('warn','block')` (`models.py:2141`); `MEASUREMENT_HEALTH.md` (HEALTHY = no SDK-observed failure).
Findings: recording nothing is consistent with the guard (no determinate evidence => `no_data`/`insufficient_data`; skipped runs contribute no outcome evaluations so they do not enter the run-health denominator; an active alert is not resolved by absence). Residual hazards: (1) a calibration expiry silently turns a monitored indicator into a blind spot; platform shows only absence, indistinguishable from no traffic, sampling or an outage, so the brief's "how customers see why a measurement is degraded" is unmet until OD-S4-3; (2) with `on_no_data=warn` the P7 gate is permissive; (3) run health stays HEALTHY while the semantic evidence is absent (same as unsampled; app `MeasurementPolicy` consumers will read HEALTHY); (4) a window straddling re-calibration mixes configuration ids and can trip `INCOMPARABLE_METHODOLOGY` (existing behaviour, but should be documented); (5) partial-window gating biases a window toward whichever period was calibrated.
Answer to risk 3: acceptable, provided (a) the SDK emits observer reports and a distinct counter for `skipped_admission` and SG-5 is amended to alert on it, (b) docs state explicitly that gating moves failure from "wrong evidence" to "no evidence" and SG-6 must set `on_no_data=block` where required, (c) a local `explain()` of the decision (status, reasons, policy summary, assessment digest) is provided so the application can display it.

### M-10 MEDIUM: privacy/security gaps
Evidence: ARCHITECTURE 5 (leakage findings with `content_digest`/`normalized_digest`), 3 (limits), 10.
Gaps: (1) digests of short/low-entropy case content are dictionary-reversible; including them in an artefact weakens "content-free"; report only counts and `case_id`s, or keyed digests. (2) Limits "100 000 cases per split, 1 MiB per case" allow ~100 GiB; no per-file byte cap, and existing `load_cases` uses `read_bytes()` unbounded (`calibration.py:128`); add a hard per-file byte cap checked before reading, line-length cap, depth cap. (3) "Held-out must be fixed (hash-pinned) before running" has no mechanism: the manifest is self-describing, so an attacker who can edit data edits manifest and split together; add `expected_manifest_sha256` as a required argument to `assess`. (4) Integrity digest is unkeyed so the status can be forged; the CLI `status` printing "calibrated" from an arbitrary file is a misuse vector; label as `unverified provenance` unless an optional HMAC (stdlib `hmac`, caller key) verifies. (5) rubric text or few-shot content copied from held-out cases is undetected leakage. (6) `case_id` pattern allows PII-ish strings; recommend opaque ids. (7) The "approval" is an attestation with free-text `role`; do not name the field `approved` or print "approved by" without "attested". Threat model also should cover: calibration set contaminated by the judge's own outputs (LLM-labelled "human" data), and training-data contamination of the provider model by public fixtures (public synthetic fixtures are likely in future model training; synthetic demo data must never be used to gauge a real model).

### L-1 LOW: naming collision "eligible"
`SLO_SEMANTICS.md:24` already uses "eligible run" for SLO events; "eligibility", "eligible set E" and `EligibilityDecision` collide. Use `evidence_admissible`/`admission` for the gate and keep E as "labelled evaluation set".

### L-2 LOW: `compare_judges` details
Precedence order (missing > failure > ambiguous > disagreement > abstention_mismatch > agreement) is internally consistent and the stated `judgment_disagreement_rate` denominator equals agreement-with-both-decisive plus disagreement; mutual exclusivity holds. Weaknesses: abstention_mismatch (one commits, one abstains) is a disagreement that matters for SLO (one includes the example, the other drops it) but gets no rate; "agreement" lumps both-UNKNOWN with both-PASS; allowing "run indices must differ" for the same fingerprint blurs repeatability and judge disagreement. `_kappa` there (existing) also uses a fixed 3-label set; new kappa must specify the category set and `n=0`/degenerate reasons (existing returns bare `None`, `calibration.py:172-184`).

### L-3 LOW: scope and docs hygiene
`PLATFORM_PROPOSAL.md` is referenced in section 8 but does not exist in `docs/p29-calibration/` (verified by listing). Preparation doc F-03/F-14 (independent governance review) notes the primary record of P29-D10 is not in the repo (`P28_P29_GOVERNANCE_INDEPENDENT_REVIEW.md:32`); the gap assessment builds its main constraint on D10 without flagging that provenance weakness.

### INFO
* ARCHITECTURE 4.1 count identity `answered = TP+FN+FP+TN`, `fnr = 1 - recall_fail` (including the Wilson interval, which is symmetric under complement), `precision`/`recall` formulas and the coverage identity on counts are correct.
* 4.10 (no ECE/Brier for categorical judgments) is correct and well justified.
* Precision/accuracy depend on class prevalence in the dataset; production prevalence differs. Policy should use FPR/FNR (prevalence-free) and report precision/accuracy as descriptive with a prevalence caveat; also report metrics per `difficulty` stratum (existing report has headline/borderline/adversarial slices; the new design pools them unspecified).
* Positive class = `fail` (risk 1) is the right call for SLO because defects are what the SLO must not lose; document the symmetric pass-side metrics as available.

## 3. Direct answers to the six numbered risks

1. Positive class = fail and conditional vs abstention-inclusive pair: positive = fail is right. Exposing both is right only if (a) naming and denominators are fixed (H-5), (b) end-to-end variants include failures/missing, and (c) the default `rate_basis` for the SLO-relevant FN side is abstention-inclusive, matching the SLI's UNKNOWN policy.
2. Wilson with small n and multiple criteria: multiplicity does not inflate false acceptance for a conjunction of criteria (it raises false rejection), so no correction is needed there; document it. Real issues are inconclusive-vs-failing (H-7), independence assumptions, rounded comparison, Wilson's small-n under-coverage vs Clopper-Pearson, and uncontrolled reuse of the held-out set (M-5). Drift indicators do have multiplicity.
3. Recording nothing on ineligibility: acceptable and consistent with the Session 2 guard (no determinate evidence => no_data/insufficient_data, absence never recovers an alert, skipped runs outside the health denominator, on_no_data is warn|block only), provided SDK-side visibility (counter, observer, explain, SG-5/SG-6 text) and an honest statement that customers cannot see the reason on the platform until OD-S4-3 (M-9).
4. Changing IndicatorBinding/EvaluationDisposition: permitted for Experimental, but a wrapper evaluator cannot work (failure sets health UNAVAILABLE; UNKNOWN records evidence). Use a calibration-agnostic admission hook (M-8) rather than calibration-specific enum members; add real compat snapshots; fix the document's contradiction about the guarded judge package being unchanged.
5. Template digest from a golden fixture: not sound as specified (fixtures are not shipped; fixture digest is not tied to code). Use a runtime rendered-probe digest pinned to the fixture by a test (M-6). It still cannot detect provider-side model changes.
6. `starting_point()` vs D10: a preset that is a labelled, optional, caller-invoked constructor does not enforce a threshold and is compatible with D10 if (a) it is never an implicit default, (b) results always print the policy and a `below_starting_point` flag, (c) "calibrated" is defined only relative to the stated policy. However D10's own source record is missing (L-3), and the preset as written is looser than its cited basis (H-6). Also note a `calibrated` status that gates evidence is an enforcement of the caller's threshold, which is fine under D10 as long as the caller chooses it.

## 4. Scope (focused slice or too much)

Too broad for one slice. Keep: dataset identity/splits/leakage (counts only), metrics engine with explicit Undefined, repeatability, fingerprint, assessment, policy/status as pure functions, `compare_judges`, offline example, the generic admission hook plus gate, tests/threat model.
Defer or cut: CLI (three subcommands; the library plus example suffice and the CLI creates the "status from an unverified file" misuse), drift indicators 4-6 (decision mix, failure-rate shift, error-rate change; they need a statistical and product design and cannot be validated offline without data), approval attestation (non-authenticating; keep only if cheap and bound to policy digest), generalised inter-labeler agreement beyond a simple documented pair or percent agreement. Keep fingerprint-change and expiry only for drift in this slice.

## 5. Gap assessment claim verification

Verified (file:line): P29 implemented as Experimental, `LLMJudge`/`SyncLLMJudge`, jp1 template, coordinator/EvaluationScope (`judge.py:97`, `core.py:135-205`, `coordinator.py:483,937`); five reference rubrics (`rubrics/` directory listing); case schema fields and `human_label` pass/fail/unknown (`calibration-case.schema.json`; `calibration.py:87-115`); `load_cases` JSONL, file sha-256, unique ids (`calibration.py:126-140`); `CalibrationCase` no-copy and redacted repr (`calibration.py:87,120`); report content: matrix, FN/FP, over-confidence, abstention by human, accuracy on answered, precision/recall per class, agreement and kappa, confidence accuracy, Wilson 95%, `insufficient_for_rates` below 12 (`calibration.py:64,195-258`); slices headline/borderline/adversarial (`calibration.py:~300`); repeatability.changed_rate (`calibration.py:~336`); `compare_reports` content (`calibration.py:~553-596`); `judge_disagreement` and `low_confidence` (`core.py:390-412`); `EvaluatorIdentity` composition and grammar (`identity.py`); rubric fingerprint (`rubric.py:308`); failures set run health UNAVAILABLE (`context.py:164-179`, `measurement_health.py:36-43`); "nothing consults calibration status" (grep of coordinator: no such reference); `tests/security/test_experimental_judge_privacy.py` exists; ADR-0010 exists; Session 2 guard separates evaluator identities (design doc section 5 methodology row, `operations.py:361-375`); OD-10 text (`P28_P29_OWNER_DECISIONS_003.md:23`); "inter-labeler agreement computed outside the harness" (`CALIBRATION_PREPARATION.md:65`); `labels` parsed but unused in metrics (`calibration.py:96,111`; no metric reads it).
Verified but characterisation differs: "undefined rates are null with no reason" true (`_rate`, `_kappa`). "D10 enforces no threshold" is quoted in several docs but its primary record is absent (L-3).
Could not verify: "SDK baseline 1802 passed, 1 skipped" (I did not run the suite); "synthetic known-confusion fixture is hand-computable" (listed, not recomputed); that platform ingestion accepts only name/version/configuration_id and no other provenance (confirmed only that `evaluator.configuration_id` is validated in `domain/evidence.py:145-154`; I did not read the ingestion service); "v1.3.0 is published and tagged" and the PR #9 / #64 merge facts (git log shows the merge commit, tag not checked); "Python 3.11 CI extras" environment.

## 6. Changes required before implementation starts

Must change in the documents (all HIGH, plus M-1, M-7, M-8):
1. H-1: state the default-behaviour gap and the bypass paths; owner decision on "explicit choice required" vs default None; add local visibility counter and SG checklist text.
2. H-2: gate derives fingerprint from the bound evaluator; declare which fingerprint fields are caller declarations; remove the claim that the fingerprint closes the silent-update gap; decide on the optional observed-model-version addition.
3. H-3: replace the F1 rule.
4. H-4/H-5: rewrite 4.2-4.3 with a denominator table, count-only partition, `committed_coverage`, `*_effective` metrics over |E|, consistent names, default abstention-inclusive FN basis, SLI UNKNOWN-policy linkage; add failure/missing/ambiguous/adversarial criteria to the policy.
5. H-6: reconcile the preset with the preparation thresholds (or retract the claim) and add the sample-size coherence check.
6. H-7: three-state criterion evaluation and status mapping.
7. H-8: derived provenance, per-provenance counts, minimum human fraction.
8. M-1 (fixed run rule, runner specification), M-7 (future dates, rubric binding, approval binds policy, policy summary on every decision), M-8 (generic admission hook, ordering with sampling, counters, compat snapshots, fix section 2/11 contradiction).
Should also fix before coding but not blocking: M-2 to M-6, M-9, M-10, scope cuts in section 4.
Owner decisions to record: OD-S4-1 (policy vs D10, with preset caveats), OD-S4-2 (default gating behaviour, now with the explicit-choice option), OD-S4-3 (platform visibility), plus a new one for the optional `ProviderReply` model-version field.

---

# Re-check of v2 (a767dc1)

Read: v2 `ARCHITECTURE.md` (all 282 lines), `PLATFORM_PROPOSAL.md`, the `GAP_ASSESSMENT.md` diff, plus the judge sources already read (re-confirmed `LLMJudge` exposes only `identity`, `deterministic`, `rubric`: `judge.py:143-153`; limits, policy and engine are private). Ran: an exact-binomial (Clopper-Pearson, bisection, 95% two-sided) script for the preset numbers. Still not run: the SDK test suite.

## R1. Verdict

**APPROVE_WITH_CHANGES (narrow).** All 8 HIGH and 10 MEDIUM findings from round 1 are closed or adequately dispositioned in the text, and the v2 statistics are largely correct. But v2 introduces two new HIGH loopholes by which an inadmissible judge can still be admitted (N-1, N-2), one HIGH self-contradiction about judge-package changes that the fingerprint depends on (N-3), and one HIGH hole in which strata the policy actually measures (N-4), plus a synthetic-data regression (N-5). Implementation may start only when the spec amendments in R5 are made (text only, no re-review of the whole document needed; I would re-check just those paragraphs).

## R2. Per-finding status

| ID | Status | Note |
|---|---|---|
| H-1 | CLOSED (as disclosure) | §8 states gated-only, lists bypass paths, adds `ungated_model_backed`, makes OD-S4-2 explicit, `UNGATED` sentinel. Default still `None`: the requirement is knowingly unmet by default; acceptable only as a recorded owner decision. See N-7 on counter semantics. |
| H-2 | PARTLY CLOSED | Fingerprint now derived from the bound evaluator and silent-update limitation stated. But the gate/binding link is not enforced (N-1) and derivation needs judge accessors that do not exist (N-3). |
| H-3 | CLOSED | f1_fail = 2TP/(2TP+FP+FN), f1_pass = 2TN/(2TN+FN+FP): correct; TP=0 with errors gives 0; undefined only at zero denominator. |
| H-4 | CLOSED | 4.1-4.2 table: counts partition, rates state denominators, `committed_coverage` added. Check of the table: `fnr_effective = (support_fail - TP)/support_fail` and `fpr_effective = FP/support_pass`, `accuracy_effective = (TP+TN)/|E|` are all internally consistent; `fnr_conditional = 1 - recall_fail` holds. |
| H-5 | CLOSED | naming rule `_conditional`/`_effective`, `fnr_effective` as SLO-relevant. Minor: `fpr_effective` counts failed/missing good runs as not false alarms, so it is not "conservative"; preset uses `fp_basis=conditional`. Fine but say so. The doc does not tie `fn_basis` to the SLI UNKNOWN policy beyond a sentence; acceptable. |
| H-6 | CLOSED with caveats | Exact check below confirms the "two errors" claim. Caveats N-6 (claim "proposals of section 10" is not literally true), N-4 (slice). |
| H-7 | CLOSED | three-way test with `inconclusive -> insufficient_reference_evidence` is correct. Gap: undefined rates (zero support) have no verdict (N-8). |
| H-8 | MOSTLY CLOSED | derived weakest provenance, counts, attestation wording. Issues N-10 (per-split derivation; fraction fields redundant). |
| M-1 | CLOSED | run 0 fixed, `run_index_used`/`runs_available`, own runner `collect_judgments`. But "public names only" is untrue for what the runner and template digest need (N-3). |
| M-2 | CLOSED | kappa dropped for labelers; mean pairwise agreement. |
| M-3 | CLOSED | E excludes `unresolved`; `A` reported; `max_ambiguous_fraction`; commit rate renamed. Naming collision with difficulty stratum `ambiguous` (N-11). |
| M-4 | CLOSED | non-FAILURE runs >= 2, `excluded_for_failures`, worst-case bound, caching caveat. |
| M-5 | CLOSED | Clopper-Pearson for policy, unrounded, independence note, `heldout_attempt` (informational only; not enforced, acceptable). |
| M-6 | PARTLY CLOSED | runtime probe digest, `limits_digest`, `behaviour_digest` excluding implementation_version are good; implementability gap N-3. |
| M-7 | MOSTLY CLOSED | future-date rule, dataset binding in `incompatible`, policy summary and flag, approval removed. Not closed: cached decision vs expiry (N-2), synthetic acceptance (N-5), unverified integrity still admissible (N-12). |
| M-8 | PARTLY CLOSED | generic hook, order admission-before-sampling, counters, snapshots: good. Binding/gate mismatch (N-1), hook failure mode (N-13). |
| M-9 | CLOSED | documented; SG-5/SG-6 text; platform proposal exists with three options. |
| M-10 | CLOSED | counts and ids only, byte caps (8 MiB/25 MiB/64 KiB/depth 8), `expected_manifest_sha256`, optional HMAC, no CLI. Residual: `case_id` opaque only "should". |
| L-1 | CLOSED | "admission". |
| L-2 | CLOSED | `both_abstain`, `abstention_mismatch_rate`, different-digest requirement. |
| L-3 | CLOSED | `PLATFORM_PROPOSAL.md` exists; D10 absence noted in ARCHITECTURE 12 and GAP notes. GAP_ASSESSMENT still contains stale text (N-9). |
| Scope cuts | CLOSED | no CLI, drift reduced to 3 indicators, no approval, simple inter-labeler agreement. Remaining breadth noted in N-14. |

## R3. Statistical re-check (exact binomial, my own computation)

Clopper-Pearson 95% two-sided upper bounds (the one-sided 97.5% level):
* n=150, limit 0.05: upper(0/150)=0.0243, upper(2)=0.0473 (meets), upper(3)=0.0573 (fails). **Maximum 2 errors: the doc's "two errors" is correct.** n=150, limit 0.10: max 7 errors.
* Zero-error minimum n: 72 for 0.05 (doc says "about 73": fine, 72 suffices), 183 for 0.02, 36 for 0.10.
* min_examples 400, failure/missing <= 0.02: upper(2/400)=0.0179 meets, 3 fails: **max 2 failures and max 2 missing of 400 (0.5%)**. Coherent (zero errors need >=183) but the preset is far stricter than the nominal "2%"; a provider rate-limit blip fails the whole calibration. State the effective count in the doc.
* min_repeat_cases 150, unstable <= 0.05: max 2 unstable cases (same as FNR), and `unstable_rate_worst_case` counts excluded cases as unstable, so a single run of 3 provider failures can sink it. Coherent but again much stricter than nominal.
* Adversarial n=30, max_adversarial_pass_on_fail = 0 is a **count**, not a statistical bound: 0/30 has CP upper 0.116. Acceptable only if labelled as a descriptive stress check; the doc says count, but §6 also says "every criterion verdict" three-way; specify that count criteria are met/violated only.
* committed_coverage >= 0.80 at n=400 (lower bound): needs >= 336 answered (84%); abstention_rate <= 0.20 (upper bound over judged ~380) allows at most ~60 abstentions. Coverage criterion therefore dominates and the abstention cap is largely redundant (not wrong).
* `fnr_effective` <= 0.05 with n=150 fails: max 2 non-flagged defects in total (FN + abstained + failed + missing), which makes the permissive-looking `max_abstention_rate=0.20` irrelevant for defects; fine, but the doc should say abstention on defects is effectively near zero.
* Policy coherence check, as written, is sound for the zero-error test but (a) must state that `min_examples`, `min_per_class` count **E** (not E plus A), otherwise the failure/missing bound is checked against 400 while |E| can be smaller; (b) must also cover coverage lower bound and adversarial size; (c) must define the verdict for an undefined rate.
* Three-way test: "violated if lower > limit" uses the two-sided 95% lower bound, correct. Lower-bound criterion mirror is correct.

## R4. New findings

### N-1 HIGH: gate and binding can disagree; "binds to the running evaluator" is not enforced
`CalibrationGate.for_evaluator(evaluator, ...)` is bound to evaluator X at construction, but `IndicatorBinding(evaluator=Y, admission=gate_X)` is constructible, and the hook is `decide(indicator, identity)` (no evaluator). The H-2 loophole (approve judge Y with X's calibration) therefore remains unless `IndicatorBinding.__post_init__` verifies `admission.bound_to(evaluator)` (identity equality is insufficient: it omits limits and template digest) or the hook receives the evaluator and recomputes the fingerprint. Required: the hook signature takes the evaluator (or `IndicatorBinding` rejects an admission not bound to its evaluator), and a test covers the mismatch.

### N-2 HIGH: cached decision can outlive expiry
§8: "the decision is read once per call from a cached object" and the fingerprint "per decision (cached)". Expiry, dataset age and future-date checks depend on `now`. If the cached `AdmissionDecision` is reused, an expired calibration stays admissible indefinitely; if recomputed each call, say so. Required: cache only the fingerprint and assessment-derived constants; recompute status with the injected clock on every call, or store `valid_until` and re-evaluate when passed. Also state clock regression handling (non-monotonic clock).

### N-3 HIGH: the document contradicts itself on judge-package changes, and the fingerprint is not implementable from public names
§2 promises "one additive change" and "public names only"; but deriving `limits_digest`, `capture_reason`, `configuration_id` inputs and the template digest "from the bound evaluator" needs: public accessors on `LLMJudge`/`SyncLLMJudge` for limits and policy (currently private, `judge.py:129-141`), and `build_prompt`/engine constants (`core.py`, `_engine.py:60`, repair text), which are not exported names. `wilson_interval` is also not in the judge package `__all__` (compat `EXPECTED_ALL`). Required: either list these additions explicitly (a public `fingerprint_parts()`/`template_digest()` inside the judge package, added to the compat snapshot) or make the template digest and parts the judge package's responsibility; correct §2/§11 and the stale GAP_ASSESSMENT line 14 ("byte-identical").

### N-4 HIGH: the policy does not say which strata it measures, and the hardest cases are outside every rate criterion
§4.2: "the pooled headline excludes `borderline` and `adversarial`". §6 never says `max_fnr`/`max_fpr`/`min_per_class`/coverage apply to the headline, to all strata, or per stratum. If headline, `calibrated` is earned on clear and ambiguous cases only; borderline (where judge and humans disagree) has no criterion at all, adversarial only a zero-count check on 30 cases. The preparation document asked for 30 borderline cases. Required: each policy criterion names its slice (default all strata pooled plus per-stratum reporting, or explicit per-stratum limits), and borderline gets a criterion or an explicit "not assessed" status line shown in every decision.

### N-5 HIGH: a synthetic dataset can still reach `calibrated`
v1 rejected `synthetic` at construction unless demonstration-only; v2 lists `accepted_label_provenance (set)`, `min_human_fraction`, and `demonstration_only` but states no rule linking them. A policy with `accepted_label_provenance` containing `synthetic`, `min_human_fraction=0`, `demonstration_only=False` yields step 6 `calibrated` on synthetic data. Also unspecified: a `demonstration_only` policy on human data. Required: construction rejects `synthetic` in the accepted set unless `demonstration_only`; `demonstration_only` forces the status ceiling `demonstration` regardless of data; status `calibrated` requires derived provenance != synthetic always.

### N-6 MEDIUM: preset provenance claim
§6: the preset numbers are "the proposals of `P28_P29_CALIBRATION_PREPARATION.md` section 10 made sample-size-coherent". Not literally: kappa 0.6 became mean pairwise agreement 0.80 (different statistic), precision(pass) >= 0.90 dropped, over-confidence <= 20% became ambiguous fraction <= 0.20 (different quantity), failure <= 2% became 2 of 400, min sizes are new. Reword to "informed by".

### N-7 MEDIUM: counters
`ungated_model_backed`: define whether it counts evaluations or bindings and whether `UNGATED` (an explicit acknowledgement) counts; it should count both so the local signal is not silenced by the sentinel. `admission_skipped` must be excluded from `attempted`, `determinate_rate`, `failure_rate` (stated) and from `describe()`; `_Counters.count` has no `else` branch (`coordinator.py:272-299`): test that an unknown kind raises in tests.

### N-8 MEDIUM: undefined criteria
A criterion whose rate is `Undefined` (e.g. zero fail support) has no verdict in the three-way test. Specify: undefined => `inconclusive` => `insufficient_reference_evidence`.

### N-9 LOW: stale text
`GAP_ASSESSMENT.md:14` still claims the judge `__all__` stays byte-identical; the drift row (line 31) still lists decision-mix/failure-rate/error-rate indicators under "Add" although v2 defers them; OD-S4-2 text still says "eligibility".

### N-10 LOW: provenance details
Derived provenance is the weakest of "its cases": one synthetic case in the train split would downgrade a fully human held-out. Derive per assessed split. With weakest-derivation and `accepted_label_provenance` excluding synthetic, `min_human_fraction` and `min_multi_labeled_fraction` are redundant (preset: accepted {multi, adjudicated} implies fraction 1.0); keep only fields that can bind, or define them for mixed accepted sets.

### N-11 LOW: naming
Difficulty stratum `ambiguous` and the ambiguous set `A` (human unknown/unresolved) are different things with the same word; rename the set (`undecidable`).

### N-12 MEDIUM: unverified integrity is still admissible
Step 1 refuses only a digest mismatch; an unsigned assessment is "labelled unverified" but can be `calibrated` and admissible. A gate constructed from a file therefore admits on a forgeable record. Required: `CalibrationGate` takes `require_verified_integrity` (default True when a key is supplied; default behaviour documented) or the decision carries `integrity_verified` and the application must opt in to accept unverified.

### N-13 MEDIUM: hook failure mode
The hook runs under the scope lock; specify behaviour when `decide` raises or returns a non-verdict: fail closed (skip with reason `admission_error`, counted, no record), never propagate into the run or fall through to evaluation.

### N-14 INFO: remaining breadth
Still sizeable: dataset loader with caps and leakage, metrics with two interval methods, repeatability, `compare_judges`, fingerprint, assessment with HMAC, policy with ~22 fields, status machine, 3 drift indicators, runner, admission hook with coordinator changes, example and fixtures. Feasible as one slice if the coordinator hook and the judge accessor additions (N-3) are implemented and reviewed first, and `compare_judges` and HMAC are the first things cut if time-pressed.

## R5. Conditions before implementation may start

Text amendments to ARCHITECTURE.md (no further architectural redesign):
1. N-1: hook receives/validates the bound evaluator; mismatch rejected at `IndicatorBinding` construction.
2. N-2: status recomputed with the clock on every call; only fingerprint/constants cached.
3. N-3: list the judge-package additions needed for fingerprint derivation (public parts accessor, template digest function), fix §2/§11 and the GAP_ASSESSMENT contradictions.
4. N-4: every policy criterion names its slice; borderline criterion or explicit "not assessed" line.
5. N-5: construction rules tying `synthetic`, `demonstration_only` and `calibrated`.
6. N-8 and the coherence-check clarifications (E-based sizes, covered criteria).
7. N-12, N-13 as one-line rules; N-6/N-7/N-9/N-10/N-11 are wording fixes that may be done during implementation.
Owner decisions OD-S4-1..4 remain open and should be recorded; OD-S4-2 must be answered (or explicitly deferred with the default-None risk accepted) before release, not before coding.
If items 1 to 6 are made, I approve implementation to start; I will re-check those paragraphs and the implemented admission hook (compat snapshot, ordering test, mismatch test, expiry-with-cached-gate test) in the code review.

---

# Confirmation of v2.1 (59e3eff)

Scope: only the items requested (sections 2, 6, 8, 11, indeterminate-set renaming, GAP_ASSESSMENT). Text reading only; no code or tests run.

**Verdict: the N-1..N-5 conditions are met. No new BLOCKER or HIGH. Implementation may proceed.** Open items below are MEDIUM/LOW and are one-line text fixes, to be made during implementation.

## Per-item status

| Item | Status | Evidence in v2.1 |
|---|---|---|
| N-1 | CLOSED | §8: `Admission.bound_to(evaluator)`; `IndicatorBinding` raises ValueError when false; `decide(indicator, evaluator)` receives the evaluator; gate `bound_to` re-derives the fingerprint. (Implementation test to require: attach gate X to judge Y fails at construction.) |
| N-2 | CLOSED | §8: status recomputed with the clock on every call; only fingerprint, integrity verification and constants cached. |
| N-3 | CLOSED | §2: complete additive list (`behaviour`/`JudgeBehaviour`, `template_digest(rubric)`, hook, `wilson_interval` export); §11 lists the same names; GAP_ASSESSMENT line 14 corrected. Implementation notes: `template_digest` must fold in `REQUESTED_TEMPERATURE` (lives in `_engine`, which imports `core`, so avoid an import cycle) and the repair-prompt text; `JudgeBehaviour` as listed has no temperature field, so the digest must carry it. `core.py` is not a public module, so export the function from the package `__all__` (which §11 does). |
| N-4 | CLOSED | §6: each criterion names its slice (pooled headline; adversarial count criterion); `borderline: reported_only` stated in every assessment. Residual by design: FNR/FPR exclude adversarial and borderline, which the decision output must repeat. |
| N-5 | CLOSED | §6 construction rules: synthetic only with `demonstration_only`; demonstration policy can only yield `demonstration`; `calibrated` requires non-demo policy and derived provenance inside the human set. Residual wording conflict (N-5a below). |
| N-6 | CLOSED | preset reworded "adapted from, not identical to". |
| N-7 | CLOSED in §8 | `ungated_model_backed` vs `explicitly_ungated` vs `admission_skipped` defined. Small inconsistency: §8 bullet (a) says `CoverageReport` gains the count while §11 puts it on `IndicatorCoverage`; pick one (per-indicator, with a total on `CoverageReport`). |
| N-8 | CLOSED for the three-way test | `Undefined` => `inconclusive`. The coherence-check clarification I asked for is only partly done: sizes now apply to the headline slice, but the check still names only `min_per_class`/`min_repeat_cases` and does not cover failure/missing at `min_examples`, committed coverage, or adversarial size. LOW; extend the check. |
| N-9 | PARTLY OPEN (LOW) | GAP line 14 fixed. Still stale: GAP line 31 (drift row still proposes decision-mix/failure-rate/error-rate indicators) and line 51 ("eligibility"). |
| N-10 | PARTLY OPEN (LOW) | `min_human_fraction` declared removed, but provenance is still derived "across the loaded splits", so one synthetic train case downgrades a fully human held-out set. Derive per assessed split. |
| N-11 | CLOSED | `indeterminate set I`, `max_indeterminate_fraction`, `indeterminate_ground_truth`, `commit_rate_on_indeterminate` throughout. |
| N-12 | CLOSED | `require_verified_integrity` required field; `starting_point()` true; unsigned/unverified then only `uncalibrated`; HMAC key on `for_evaluator`. Note: with true and no key supplied, the gate must refuse at construction rather than silently never admit. |
| N-13 | CLOSED | hook exception fails closed with reason `admission_error`, counted; BaseException propagates. |

## New findings (all MEDIUM/LOW)

* **N-15 MEDIUM: leftover `min_human_fraction`.** Removed in prose (§6 line 190, §13) but still listed in the `CalibrationPolicy` field list (line 170), the preset ("human fraction 1.0", line 174), status step 3 ("below the human/multi-labelled fractions") and §10 ("min human fraction"). Since all policy fields are required, an implementer cannot tell whether the field exists. Remove it everywhere (keep `min_multi_labeled_fraction` only if it can bind: with accepted {human_multi, human_adjudicated} and weakest-case derivation it is always 1.0, i.e. also redundant).
* **N-16 LOW: field list incomplete.** `require_verified_integrity` is required but not in the §6 field list.
* **N-5a LOW: demonstration wording.** §6 rule says a `demonstration_only` policy yields `demonstration` "on any data", status step 5 says "on synthetic data passes". Make step 5 match the rule (and say what a demonstration policy yields when criteria fail: the normal failing statuses, never `calibrated`).
* **INFO:** admission-before-sampling is specified; the order relative to the existing "run not recording" skip should be stated (recommend: run-not-recording first, then admission, then sampling) and covered by an ordering test.

## Conditions for the implementation review

I will check in code: attach-mismatch rejection test; expiry test with a long-lived gate and a moving clock; hook-raises test; counter tests (`admission_skipped` excluded from `attempted`); template-digest pinned to `prompt_golden_jp1.json` and including temperature; compat snapshots for the new names; no content in any artefact (canary tests); and removal of `min_human_fraction` if it is not implemented.

---

# Conformance review of the built code (ba2523d; head 0bde58d, no src change since)

Method: fresh `git archive ba2523d` extract at /tmp/s4x (repo untouched), read of `calibration/{_stats,metrics,analysis,policy,admission,assessment,fingerprint,judgments,dataset}.py`, `judge/behaviour.py`, the full diff of `coordinator.py`, `judge.py`, `sync.py`, `judge/__init__.py`, ARCHITECTURE section 14, PERFORMANCE.md, test names. Ran: an independent exact-binomial comparison of `_stats.clopper_pearson` (113 (k,n) cases incl. n=1..1000, k=0/n, large n), and direct evaluation of F1 and the preset numbers. NOT run: the test suite (no pytest in the available interpreters: Python 3.15 without pytest; I did not install anything). Test claims below are from reading test names/bodies only.

## C1. Verdict

**The PR may go to owner review.** No BLOCKER and no HIGH finding in the built code. The statistics are correct, the hook/gate design matches the amended architecture and none of the section 14 deviations weakens a required property. Remaining items are MEDIUM/LOW and are either documentation or small hardening; the first two (M-C1, M-C2) should be fixed or explicitly accepted before merge, not before review. I could not independently confirm the "tests pass" claim.

## C2. Statistical verification (own computation)

* `clopper_pearson` (continued-fraction incomplete beta plus bisection): maximum absolute difference to an independent binomial-CDF bisection over 113 cases = 3.7e-15. Spot values: upper(0/72)=0.049944 (<=0.05, so 72 error-free suffice), upper(2/150)=0.047333, upper(3/150)=0.057334 (two errors maximum at n=150, as claimed), upper(2/400)=0.017944, upper(3/400)=0.021761. 0/46: exact upper 0.077062 vs Wilson 0.077074: deviation 6 in section 14 is correct (exact is not always the wider). Edges (k=0, k=n, total 0 -> None, large n 5000/20000) behave.
* `f1` = 2TP/(2TP+FP+FN): TP=0 with errors gives 0.0, 0/0 gives Undefined: correct (H-3).
* `metrics.slice_metrics`: counts and every rate in the 4.2 table are implemented with the stated denominators (`fnr_effective = (support_fail-TP)/support_fail`, `fpr_effective = FP/support_pass`, `committed_coverage = answered/|E|`, `abstention_rate = abstained/judged`, `accuracy_effective = (TP+TN)/|E|`; `metrics.py:122-139`). The count partition holds by construction; precision/recall/F1 for the pass class are mirrored correctly. Kappa uses the explicit category set (PASS, FAIL, UNKNOWN) and returns Undefined when expected agreement is 1 or n=0 (`_stats.cohen_kappa`).
* Three-way test (`admission._upper/_lower`) matches the spec: met if upper<=limit, violated if lower>limit, otherwise inconclusive; lower-bound mirror correct; `interval is None` (zero denominator) -> inconclusive (N-8 closed). Intervals are unrounded in the decision (`Proportion.exact`), rounding only in `as_json`.
* Policy coherence (`policy._check_coherence`): checks fnr/fpr vs `min_per_class`, unstable vs `min_repeat_cases`, failure/missing vs `min_examples`, abstention vs ceil(min_examples x coverage), coverage lower bound at full coverage, `min_per_class <= min_examples`. Preset passes: failure/missing 0.02 needs n>=183 (400 ok); abstention at 320 ok. This closes the N-8 clarification. Not covered: `min_adversarial_fail` (a count criterion, nothing to check) - fine. `starting_point()` numbers equal v2.1 (fnr 0.05 effective, fpr 0.10 conditional, 2 errors at 150).
* Status ladder (`admission._decide`): structure failures (integrity mismatch/unverified-when-required, non-held-out, future-dated) return `uncalibrated` before any metric is read; then rate violation -> `uncalibrated`; version -> `incompatible`; data non-met or rate inconclusive -> `insufficient_reference_evidence`; time -> `calibration_expired`; demonstration policy -> `demonstration`; else `calibrated`. This is exactly section 6 (deviation 5). Effect of ordering "measured violation outranks incompatibility": both are non-admissible and both listed in `criteria`; no property weakened. Note it can mislead a reader (a different model plus a violated rate shows "uncalibrated"), acceptable because `reasons` list both.
* Provenance: derived per split as the weakest case provenance and must equal the declared per-split value (`dataset.py:445-513`); `calibrated` needs a non-demonstration policy and human-only accepted set (`policy.py:133-139`). N-5 and N-10 closed in code (test `test_synthetic_labels_never_calibrate_under_a_human_policy`).
* Fingerprint: derived from the bound evaluator (`JudgeFingerprint.for_evaluator`, `fingerprint.py:80-109`), `behaviour_digest` excludes SDK version and model declaration, equivalence additionally requires equal `ModelDeclaration`; `template_digest()` renders the real `build_prompt` for two fixed probe rubrics, both repair variants, plus schema id, reason bound and temperature (`behaviour.py:72-105`). Limits digest uses all `JudgeLimits` fields. Deviation: architecture said `template_digest(rubric)`; built `template_digest()` (no argument) and is listed in §11 as such; harmless.

## C3. Did any section 14 deviation weaken a required property?

1. `EvidenceAdmission` name: neutral.
2. Hook outside the recording gate: **strengthens** (no foreign code under the lock). Residual: it runs before the state/duplicate checks (so it is called for closed scopes and duplicate indicators, then `_prepare` raises) and the decision is taken at submit time, not at provider-call time, so a queued evaluation can start after expiry (queue wait is bounded by drain timeout). LOW; document.
3. Per-split provenance: **strengthens** (my N-10).
4. `calibration_no_evidence` reason code: neutral.
5. Status order as section 6: as reviewed.
6. Exact interval for policy, Wilson for display: correct, and the dropped "exact never narrower" property was false.
7. Schema validation plus fingerprint consistency at parse: strengthens.
8. Indexed table: performance only.
9. `compare_judges` and HMAC kept: scope note in C5.

## C4. Per-finding status in code

| Finding | Status | Evidence |
|---|---|---|
| H-1 | Closed as disclosure; unchanged default | `IndicatorBinding.admission=None` default (`coordinator.py:180`), `UNGATED` sentinel (`:114-127`), counters `ungated_model_backed`/`explicitly_ungated` (`:255-259`, `_Counters.count`), README/SG text; test `test_ungated_counters_separate_unset_from_explicit_choice`. Bypass via `EvaluatorRunner` remains and is documented. Owner decision OD-S4-2 still open. |
| H-2 | Closed | fingerprint derived from evaluator (`fingerprint.py:80`), gate `bound_to` re-derives (`admission.py:561-568`); silent-update limitation stated in `behaviour.py:1-8`. |
| H-3 | Closed | `_stats.f1`. |
| H-4, H-5 | Closed | `metrics.py:122-139`. |
| H-6 | Closed | `policy.py:142-185`, preset `:188-220`. |
| H-7 | Closed | `admission.py:165-190`, test `test_not_provably_good_is_insufficient_evidence_not_failing`. |
| H-8 | Closed | `dataset.py:445-513`, case label rules `:236-320`. |
| M-1 | Closed | run 0 enforced (`metrics.split_metrics` raises otherwise), `collect_judgments(_async)` returns per-run table; public names only. |
| M-2 | Closed | `inter_labeler_agreement` mean pairwise agreement. |
| M-3 | Closed | `case.indeterminate`, indeterminate set metrics, `max_indeterminate_fraction`. |
| M-4 | Closed | `analysis.repeatability` (non-failed runs, `excluded_for_failures`, worst case). |
| M-5 | Closed | Clopper-Pearson policy bounds, unrounded, `heldout_attempt` recorded (informational). Independence caveat documented. |
| M-6 | Closed with M-C2 below | runtime template digest, limits digest, behaviour digest. |
| M-7 | Closed | future-date rule, rubric binding (`rubric_matches_dataset`), policy summary/flag, no approval. |
| M-8 | Closed | hook, order (run-not-recording, admission, sampling: `coordinator.py` `_prepare`), counters, compat snapshot test `test_coordinator_admission_hook_shapes_snapshot`, `test_admission_is_applied_before_sampling_and_after_run_not_recording`. |
| M-9 | Closed | docs; counters; `explain()`. |
| M-10 | Closed | caps `dataset.py:45-49`, `_read_bounded` lstat/regular-file/size, mandatory `expected_manifest_sha256`, HMAC, content-free artefacts (`test_no_artefact_contains_case_content`). |
| L-1..L-3 | Closed | naming, taxonomy, platform proposal. |
| N-1 | Closed | `IndicatorBinding.__post_init__` raises when `bound_to` false; tests `test_binding_rejects_an_admission_made_for_another_evaluator`, `test_a_gate_cannot_be_attached_to_a_different_judge`. |
| N-2 | Closed | `CalibrationGate.decision()` recomputes with the clock each call; test `test_the_decision_is_made_on_every_call_so_expiry_takes_effect`. |
| N-3 | Closed | `JudgeBehaviour`, `behaviour` property, `template_digest`, `wilson_interval` export, hook; `__all__` and snapshot updated. |
| N-4 | Closed | headline slice for rates, adversarial count, `borderline: reported_only` (`metrics.py:203`). See U-1 on repeatability slice. |
| N-5 | Closed | `policy.py:133-139`, status step. |
| N-6..N-9, N-11 | Closed | wording/naming/counters. |
| N-10 | Closed | per-split derivation. |
| N-12 | Closed | `require_verified_integrity`; gate refuses without key (`admission.py:544`); unverified -> `uncalibrated`. |
| N-13 | Closed | `except Exception` -> `admission_error`; non-verdict return also fails closed; BaseException propagates (tests present). |
| N-15, N-16, N-5a | Closed | `CalibrationPolicy` has no `min_human_fraction`, includes `require_verified_integrity`; demonstration yields `demonstration` only. |

## C5. New findings

No BLOCKER, no HIGH.

* **M-C1 MEDIUM: behaviour_digest does not cover the engine/parser logic.** `template_digest()` covers prompt text, schema id, reason bound and temperature, and `limits_digest` covers limits, but not parser strictness, repair/retry logic, the repeats aggregation (`judge_disagreement` -> UNKNOWN) or the confidence-floor logic (`core.py:390-412`). Since `implementation_version` is deliberately excluded, a patch release that changes any of these leaves an old calibration `calibrated`. Add a code-owned `ENGINE_REVISION` constant (bumped on any behaviour change, covered by a test that pins it with the golden vectors `judge_output_vectors.json`) into the template/behaviour digest.
* **M-C2 MEDIUM: a signed assessment attests integrity, not that a real run happened.** `build_assessment` accepts any `JudgmentTable` whose `fingerprint` field is asserted; HMAC `sign` only proves the key holder signed it. The docs (README, SECURITY_AND_PRIVACY) should say plainly that "verified" means "unaltered since signing by a key holder", and that table provenance (who ran the judge on which data) is not proven. Check the doc wording; I did not find this stated in the README grep.
* **L-C1 LOW: per-call cost on the caller's loop.** The full `_decide` (document deep copy, canonical digest, fingerprint parse, ~20 criteria) is recomputed on every evaluation: 0.8 ms measured by the author (PERFORMANCE.md; I did not re-measure). Acceptable for judge calls but it blocks the event loop; cache with a `valid_until` boundary or at least avoid `assessment.document` deep copies.
* **L-C2 LOW: undocumented behaviour.** Repeatability is computed over all difficulty strata of determinate cases (`analysis.repeatability` is passed all cases), while ARCHITECTURE section 6 says rate criteria use the headline slice; the unstable criterion therefore covers adversarial/borderline too (stricter, not weaker) but the architecture does not say so. State it.
* **L-C3 LOW: within-split duplicates.** `_leakage` flags cross-split duplicates as `cross_split`; duplicates within the held-out split are reported but gate nothing, although they violate the independence assumption of the intervals (they inflate n). Consider an `identical_within_heldout` count criterion or at least a documented caveat.
* **L-C4 LOW: label-rule corner.** An `unresolved` case with unanimous labelers is accepted (unanimity plus `unresolved`, `dataset.py:309`), which lets a labeller push cases into the indeterminate set; harmless to safety (it only shrinks E and raises `indeterminate_fraction`) but inconsistent.
* **L-C5 LOW: dataset `created_at` in the future** yields a negative dataset age and passes `dataset_current`; apply the same 60 s skew rule as assessments.
* **L-C6 LOW: provider cost.** `collect_judgments` runs up to 20 000 x 10 judge calls sequentially with only the judge's own budget; the docs say this is the caller's opt-in. Recommend the README warn that a `JudgeBudget` should be set before calibrating against a paid provider (no hidden calls are made by the package itself).
* **INFO:** the ungated bypass paths (direct `EvaluatorRunner`, `run.record_evaluation`, `admission=None`) remain by design; `CalibrationGate` accepts only `LLMJudge`/`SyncLLMJudge`, so other model-backed evaluators can be given a custom `EvidenceAdmission` but not this gate.

## C6. Compatibility, separation, scope

* No change to `pyproject.toml` (zero runtime dependencies preserved; stdlib only: `hmac`, `hashlib`, `math`, `json`). No change under `domain/`, `sdk/`, `evaluation/`, wire schemas, platform; `git diff --stat` shows src changes only in `experimental/calibration/*` (new) and `experimental/judge/{__init__,behaviour,coordinator,judge,sync}.py` (additive: new names, new enum member, new `ReportKind` literal, default-valued fields). `EvaluationDisposition.SKIPPED_BY_ADMISSION` and the extra `IndicatorCoverage` fields are additive on an Experimental API; snapshot test added; existing stable `test_public_api_1_*` untouched. CHANGELOG entry added.
* Platform proposal remains a proposal; no wire/DB/Session 2 change.
* Scope: ~2.9 kLOC library plus 8.7 kLOC total diff including tests, schemas, fixtures, example, benchmark scripts and eight docs. Still one coherent vertical slice, but it kept the two items I named as first cuts (`compare_judges`, HMAC). They are well tested and small; I do not require removal. The extra docs (PROVENANCE_SPEC, TRACEABILITY_MATRIX, SECURITY_AND_PRIVACY, DATASET_SCHEMA, PERFORMANCE, README) add review surface; ensure they do not claim more than the code does (see M-C2).

## C7. Items the docs claim vs the code (checked)

* "Run health unchanged on skip": code returns before any recording; test `test_a_skip_makes_no_provider_call_records_nothing_and_keeps_run_health`. Verified by reading.
* "Gate cannot be attached to another judge": enforced at binding construction. Verified by reading.
* "Exact interval used by policy": yes (`Proportion.exact` in `_upper/_lower`).
* "No artefact contains content": by construction (assessment fields are ids, counts, digests, enums; leakage report holds case ids only) and a canary test exists; not executed by me.
* "Test suite passes": not verified by me.

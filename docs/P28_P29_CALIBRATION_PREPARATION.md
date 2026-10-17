# P29 real-model calibration: preparation (nothing here has been executed)

Status: **PREPARATION ONLY.** No model was called, no dataset was labelled, no API charge was
incurred and no customer content was read or transmitted. Every threshold below is **PROPOSED**:
the owner decision P29-D10 (option A) makes calibration customer-local, and the harness
(`agent_reliability.experimental.judge.calibration`) enforces no threshold and never emits "good",
"ready" or "accurate". These proposals are for the pilot owner's acceptance decision; they are not a
Gentlity claim about any rubric or model, and the reference rubrics remain uncalibrated examples.

## 1. Authorization gate (all must exist before any execution)

1. Written pilot-owner authorization naming the provider, the model label, the dataset, the
   maximum spend and the maximum number of calls.
2. For a customer dataset: the data owner's written permission and a privacy review (section 8).
   Without it only the synthetic dataset below is permitted.
3. Provider credentials injected at run time by the operator; none is stored in the repository.
4. A local-model run needs a model the operator has already installed; the SDK never downloads one.

## 2. Dataset specification

The case file is JSON Lines, one object per line, validated by `calibration-case` schema
(`gentlity.calibration-case/1`): `case_id` (unique), `dimension`, `parts` (role-tagged text),
`human_label` (`pass` | `fail` | `unknown`), `difficulty` (`clear` | `borderline` | `adversarial` |
`ambiguous`), optional `labels` (one entry per labeler) and `source` (at most 200 characters, not
content).

Proposed composition per rubric and dimension:

| Stratum | Purpose | Proposed minimum |
|---|---|---|
| clear pass / clear fail, balanced | headline accuracy, precision, recall | 50 each |
| `unknown` (genuinely undeterminable) | abstention behaviour; over-confidence | 30 |
| `borderline` | where the judge and people disagree | 30 |
| `adversarial` (injection attempts inside the judged content, format games) | robustness; the judged content is untrusted | 30 |
| `ambiguous` | labeler disagreement; the harness counts these in its headline slice together with `clear` cases (slices: headline = clear + ambiguous, borderline, adversarial), so keep them few or report headline results with and without them | 20 |

The harness flags any slice with fewer than 12 cases (the confusion matrix has 12 cells) as
`insufficient_for_rates` and reports counts only; the proposed minimums are deliberately larger so
that Wilson intervals are informative. Datasets must be fixed before running (the report records
the dataset sha-256), versioned, and never edited after labelling. Synthetic data is acceptable for
a first run; it measures the harness and the rubric wording, not production behaviour.

## 3. Rubric versioning rules

* A rubric is identified by `rubric_id`, `rubric_version` and a content fingerprint, all recorded in
  the report. Any change to rubric text, dimension, criteria or confidence mapping requires a new
  `rubric_version`; a calibration result applies to exactly one (rubric version, template id,
  model label, configuration id) tuple and must not be carried to another.
* The prompt template is identified by `template_id` (`jp1` today); a template text change changes
  the id (`docs/VERSIONING.md`).
* A model change (including a provider-side silent update, when the provider exposes a version) is a
  new calibration. Pin the model label and record the provider's returned model identifier where
  available.
* Keep a calibration log per rubric version: date, report file, dataset sha-256, reviewer roles.

## 4. Human-review methodology

* At least two independent labelers per case for the headline set; labelers do not see the judge
  output; label guidance is the rubric text plus written examples that are not in the dataset.
* Disagreements are adjudicated by a third reviewer; the case keeps every individual label in
  `labels` and the adjudicated value in `human_label`; cases with unresolved disagreement become
  `ambiguous`.
* Record labeler roles, not personal data, in the report appendix. Labelers work on the same
  anonymized text the judge sees.
* Inter-labeler agreement (raw and Cohen's kappa between labelers) is computed **outside the harness** from the per-labeler `labels` entries (the harness parses them but does not compute labeler-versus-labeler agreement) and is measured first; if it is low the rubric or the
  guidance is the problem, not the model, and judge metrics are not interpreted.

## 5. Agreement and disagreement metrics (as the harness computes them)

Per slice and overall: confusion matrix of human label against judge decision (`PASS`, `FAIL`,
`UNKNOWN`, `FAILURE`); raw agreement and Cohen's kappa between the human label and the judge decision over decided calls (this is judge-versus-human agreement, not inter-labeler agreement); accuracy on answered
calls; precision and recall for `pass` and `fail`; abstention rate overall and by human label;
accuracy by judge confidence level; repeatability (share of repeated calls whose decision changed,
by human label); failures by class; token and latency totals. Every rate is printed beside its raw
counts and a 95% Wilson interval.

## 6. False-positive and false-negative analysis

Terminology as the harness uses it: a **false negative** is a judge `PASS` on a case people labelled
`fail` (a missed defect, the costly direction for a gate); a **false positive** is a judge `FAIL` on
a case people labelled `pass` (a spurious alarm); **over-confident** is a judge `PASS` or `FAIL` on a
case people labelled `unknown`. The report lists `misjudged_case_ids` (identifiers only). Analysis
procedure: for every misjudged case the reviewers read the case locally, classify the cause (rubric
ambiguity, missing context, label error, judge error, prompt-injection effect), and decide whether
the fix is the rubric, the dataset or the pilot's use of the indicator. Findings are summarized by
cause without quoting case text.

## 7. Cost, latency and provider-failure measurement

* Cost: input and output tokens from the report's `usage` block times the provider's published
  price at run time, recorded with the price source and date. A dry run with a scripted provider
  first confirms counts and the budget guard (`JudgeBudget`).
* Latency: total and maximum per call from the report; p50/p95 from the pilot's own call timing
  (the report holds only the total and the maximum). Measure at the intended concurrency and `max_pending`, because shedding changes results.
* Provider failures: the report's `failures_by_class` and the observer counters (failed by class,
  shed, skipped). A failed call is evidence of an execution failure, never a verdict; the run is
  re-executed only for transport failures, with the rerun count recorded. The judge's own limits and budget
  (`JudgeLimits`, `JudgeBudget`) apply; no extra retry layer is added for calibration.
* Stop conditions: spend or call limit reached; provider failure rate above the pilot owner's limit;
  any sign that content left the approved boundary.

## 8. Privacy controls

* Raw judged content is held only in the calibration process and sent only to the provider the
  judge already uses; the report is content-free (no case text, no judge `reason`, no raw output)
  and contains only identifiers.
* Customer datasets: stored on the customer's side, access-controlled, not copied into the
  repository, not attached to tickets or the platform; deleted at the end of the calibration per
  the data owner's rule.
* Run from a clean environment; disable provider-side training/retention options where the provider
  offers them and record the setting. Do not run with real customer data over a provider the data
  owner has not approved.
* The platform receives only typed outcomes, reason codes and health, as in the pilot design
  (`tests/security/test_experimental_judge_privacy.py` and the canary evidence in the final report).

## 9. Provider and judge failure handling during the run

Failures are classified by the judge (unavailable, timeout, malformed output, budget exhausted,
shed); the harness records them and continues. A run with more than the pilot owner's tolerated
share of failures is reported as incomplete rather than averaged in.

## 10. PROPOSED pilot acceptance thresholds (not approved, not enforced)

These express what a pilot owner might require before treating a judge indicator as usable in an
SLO or gate. They are starting points to be reviewed against the pilot's risk and are **PROPOSED**.

| Criterion | PROPOSED threshold | Rationale |
|---|---|---|
| Inter-labeler agreement (kappa between labelers, computed outside the harness) | at least 0.6 | below this the rubric, not the model, needs work |
| Judge precision for `pass` (lower Wilson bound) | at least 0.90 | a gate that wrongly passes is the costly error |
| False negatives (judge PASS on human fail) | at most 5% of human-`fail` cases, upper Wilson bound reported | missed defects |
| False positives (judge FAIL on human pass) | at most 10% of human-`pass` cases | alert fatigue |
| Over-confident (PASS/FAIL on human-`unknown`) | at most 20% of human-`unknown` cases | the judge should abstain when people cannot decide |
| Repeatability (decision changed on repeat) | at most 5% of compared cases | a verdict should not flip on re-run |
| Provider failure rate | at most 2% of calls, no `shed` | measurement coverage |
| Adversarial slice | no human-`fail` `adversarial` case with judge decision PASS (read from the adversarial slice matrix); whether injection caused a flip is judged by people in the misjudged-case review | untrusted-content robustness |

A result that meets these describes one rubric version, model label and dataset only. It is a
condition for the pilot owner's decision, never a Gentlity accuracy claim; failing any criterion is
a reason to change the rubric, dataset or intended use rather than to widen the threshold.

## 11. Local run plan for later (when authorized)

1. Prepare and hash the dataset; load it with `load_cases` and review `dataset` counts.
2. Dry run with a scripted provider (no cost) to check wiring, budgets and the report schema.
3. Run `run_calibration` (or the async form) with the authorized provider and `JudgeBudget`
   limits; write the content-free report; store it with the calibration log.
4. Review misjudged identifiers locally; fill the analysis; decide per the thresholds above.
5. Only then fill SG templates A-F in `docs/P29_PILOT_REPORT_TEMPLATE.json`; calibration itself is a
   prerequisite (P29-D10) and is not one of SG-1..SG-6.

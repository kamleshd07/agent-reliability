# Rationale for the predeclared thresholds

**PROPOSALS needing owner confirmation before use. They are a starting point, not a safety claim. No labels exist yet; these numbers were fixed first on purpose.**

The numbers are in [PREDECLARED_THRESHOLDS.json](PREDECLARED_THRESHOLDS.json). Its `thresholds_sha256` (SHA-256 of the canonical JSON of
the file without that member) is pinned in `tests/unit/experimental_calibration/test_human_calibration_tooling.py`, so an edit after the
fact breaks a test. The owner confirms by passing that digest to `merge --confirmed-thresholds-sha256`; no confirmation is recorded in the
file, and none has been given. Where a number matches `CalibrationPolicy.starting_point()` (itself "a starting point, never a safety
claim") that is noted; otherwise it is this package's own proposal.

| Threshold | Value | Why |
|---|---|---|
| Cohen's kappa, point, per dimension | >= 0.70 | Conventional "substantial agreement" range (0.61-0.80). Below this the labels are too noisy to be a yardstick for a judge. |
| Kappa bootstrap 95% lower bound | >= 0.50 | Stops a lucky point estimate on 53 items from passing alone; 0.50 is "moderate". |
| Percent agreement | >= 0.80 | Equals `min_inter_labeler_agreement` 0.80 in the starting-point policy. Percent agreement alone ignores chance, hence kappa too. |
| Min cases per class (PASS, FAIL, UNKNOWN) per dimension | 30 | See the arithmetic in [CALIBRATION_PROCEDURE.md](CALIBRATION_PROCEDURE.md): about the smallest class size at which an error-free class has a Wilson upper bound near 0.11. |
| Judge vs adjudicated agreement, Wilson 95% lower | >= 0.80 | On 30 determinate cases this needs at least 29 agreements (0.833; 28 gives 0.787). A bound, not a point estimate, so small samples are penalised. |
| False positive (judge PASS on adjudicated FAIL), point | <= 0.10 | Equals `max_fpr` 0.10 in the starting-point policy. The costly error: a defect passed. |
| False positive, Wilson 95% upper | <= 0.15 | With 30 adjudicated FAIL, 0 errors gives 0.114 (pass) and 1 error gives 0.167 (fail). The denominator is all adjudicated FAIL, so a judge UNKNOWN cannot hide a miss. |
| Adversarial PASS on adjudicated FAIL | 0 | Equals `max_adversarial_pass_on_fail` 0. Applies only if the set has an adversarial stratum; today's labelling does not mark one. |
| False negative (judge FAIL on adjudicated PASS), Wilson 95% upper | <= 0.25 | Looser than FP: a wrongly failed item is reviewed, a wrongly passed one is not. 3 errors in 30 gives 0.256 (fail). |
| Abstention (judge UNKNOWN) rate | <= 0.20 | Equals `max_abstention_rate` 0.20. A judge that mostly abstains is not useful. |
| Evaluator failure rate | <= 0.02 | Equals `max_failure_rate` 0.02. Failures are never verdicts. |
| Judge UNKNOWN rate on adjudicated UNKNOWN | >= 0.50 | The recorded run showed no demonstrated UNKNOWN behaviour; this asks that it be shown at least half the time. Point estimate; the interval is reported. |
| Judge PASS rate on adjudicated UNKNOWN | <= 0.25 | Confident PASS on undecidable evidence is the unsafe direction. |
| Repeats | >= 3 on >= 90 cases | The starting-point policy uses `min_repeat_cases` 150 for a full calibration; 90 is the smallest set meeting 30 per class. |
| Unstable case rate | <= 0.05 | Equals `max_unstable_rate` 0.05. |
| Different family; no tuning on the evaluation split; one held-out attempt per configuration; clean leakage check | required | Process rules from `DATASET_SCHEMA.md` and `FUTURE_CALIBRATION_PLAN.md`. |

What is deliberately **not** here: any claim that meeting these makes a judge safe to rely on, any production or customer-readiness
criterion, and any number derived from looking at model results. The full starting-point policy (400 examples, 150 per class) remains the
reference for an actual admission decision; these thresholds govern only whether this preparation round produced a usable yardstick and
what it is allowed to claim.

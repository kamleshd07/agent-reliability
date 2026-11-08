# Different-model calibration procedure (NOT executed, NOT authorised)

**Preparation document. No judge has been run against human labels, no human labels exist, and no human evaluation has been performed.**
It extends [FUTURE_CALIBRATION_PLAN.md](../FUTURE_CALIBRATION_PLAN.md); it does not replace its gate (section 0 there still applies).

## What the owner must approve before step 1 (nothing below is approved)

1. The thresholds in [PREDECLARED_THRESHOLDS.json](PREDECLARED_THRESHOLDS.json) (by recording their `thresholds_sha256`).
2. The two labellers and the adjudicator, and acceptance of their declarations.
3. The **judge model**: name, version or digest, family, and where it runs.
   * Option A, no spend: an open-weights model of a **different family** from the agent's, run on loopback through the existing
     `examples/judge_providers.py::local_runtime_provider`. The recorded run used one gemma-family model as both agent and judge.
   * Option B, spend: any hosted or paid model. Needs written approval naming provider, model, maximum calls and maximum cost, and the
     data owner's agreement that the (synthetic) content may leave the machine. **No such approval exists; this procedure calls no hosted model.**
4. The call and cost budget (`JudgeBudget`, `JudgeLimits`, `max_concurrency`) computed before the run: cases x repeats x dimensions x
   (input + output tokens) at the provider's published price (zero for Option A, but time still bounded).
5. The evaluation dataset size (see "Sample sizes"); the existing 53 cases are not enough for a calibration claim.

## Judge candidate (owner-proposed, not approved, not calibrated)

The owner named **Qwen3-14B** (Alibaba Qwen family) as the initial different-family judge candidate. It is a different family from the Gemma-family model that wrote
the agent answers and the original same-model judgements, which is what the procedure requires. Nothing here claims it is calibrated; no run has happened.

Local verification performed on 2026-11-08 (no model was pulled and no judge call was made):

| Check | Result |
|---|---|
| Runtime | Ollama 0.40.13 serving on loopback |
| Hardware | 24 GB unified memory, 15 logical CPUs |
| Models present | `gemma4:12b`, `qwen2.5-coder:7b`. **Qwen3-14B is not installed.** |
| Feasibility | a 4-bit Qwen3-14B is roughly 9-10 GB, which fits 24 GB with the OS and the repository tooling; throughput, context length and reasoning-token behaviour are unverified |

Before any calibration run the owner (or engineering with the owner's go-ahead) must: pull the model, record the exact tag and digest in the run record, run the
smoke checks below, and decide the generation settings in advance. Qwen3 is a reasoning-capable model: the earlier Gemma run showed that truncated reasoning
(`finish=length`) surfaces as evaluator failures, so use the thinking-disabled mode if the runtime offers it, otherwise a generous output budget, and report the
evaluator-failure rate against the 2 % threshold. Smoke checks: structured-output compliance on the judge schema over 20 synthetic prompts, determinism at the chosen
temperature, latency per call, and a leakage-free held-out split. A model that fails the smoke checks is replaced, not tuned on the evaluation split.

## Step by step

1. **Freeze.** Commit the rubric versions (`judge-groundedness@2026-10.r1`, `judge-answer-relevance@2026-11.r1`), the thresholds file and its
   digest, the tooling revision and the labeller instructions. Record the git commit. Nothing below may change them; a change starts a new round.
2. **Export a blind sheet** with an owner-held secret salt, so the key cannot be re-derived from the public seed:
   `python scripts/p29_human_calibration.py export --out-dir sheets --key-out /private/place/key.json --salt-file /private/place/salt.txt`.
   Give labellers `blank_sheet.csv` only. Keep the key, the salt and `export_manifest.json` away from them. Do not give labellers repository access:
   the labels and corrections of the existing golden set are in the public repository.
3. **Independent labelling** by two labellers, then `validate` each returned sheet.
4. **Agreement** (`agreement ... --adjudication-template`). If a predeclared floor is missed, stop: see the adjudication protocol; do not run any judge.
5. **Adjudication** by the third person, blind to model verdicts.
6. **Merge** into reference datasets (one per dimension) with `merge`, passing `--confirmed-thresholds-sha256` and `--split`. The tool refuses
   incomplete sheets, example/placeholder identifiers, non-independent adjudicators and sub-floor agreement.
7. **Split rules.** Decide the split of every case **before** any judge is run:
   * `train` and `calibration`: allowed for prompt, rubric-wording and threshold work on the judge side.
   * `heldout`: the only split an assessment may use. Fix it and pin the manifest digest before the first model call. It is assessed once per
     configuration; count attempts in `heldout_attempt`. The judge's prompt, rubric text or few-shot examples must not be drawn from it.
   * The merge writes one split per run; to build several splits run it on separate disjoint item sets. Held-out-only data cannot demonstrate
     absence of overlap with training material (`insufficient_reference_evidence`), so provide another split.
8. **Leakage check.** `load_reference_dataset` reports duplicate ids and identical or normalised-identical content across splits; the status must be
   clean. It cannot see paraphrase or copying of cases into prompts; the owner attests that none was done.
9. **Declare the model** before running: `ModelDeclaration` with the model label, the family, the version or digest, the runtime, and a statement
   that the agent that produced the answers was a different family. The fingerprint is derived from the evaluator; the declaration is the caller's.
10. **Dry run** with a scripted provider (as in `examples/judge_calibration_offline.py`) to confirm counts and budget guards. No spend.
11. **Run** (owner-approved model only), per dimension, with at least 3 repetitions:

    ```python
    from agent_reliability.experimental.calibration import (
        CalibrationGate,
        CalibrationPolicy,
        Split,
        build_assessment,
        collect_judgments,
        load_reference_dataset,
        repeatability,
    )

    dataset = load_reference_dataset(manifest_path, expected_manifest_sha256=PINNED)
    table = collect_judgments(
        judge, model_declaration, dataset.cases(Split.HELDOUT), repetitions=3
    )
    assessment = build_assessment(
        dataset, Split.HELDOUT, table, now=aware_now, heldout_attempt=1
    )
    ```

    `run_calibration(judge, cases, dataset_id=..., repetitions=3)` in `experimental.judge` gives the lighter confusion-matrix report. Either way
    the judge must be built with explicit `JudgeLimits` and, for any priced provider, a `JudgeBudget`.
12. **Decide against the predeclared thresholds**, computed from the assessment: agreement Wilson lower bound, false positive and false negative
    bounds, abstention, evaluator failure, UNKNOWN behaviour, repeatability. Optionally build a `CalibrationPolicy` that encodes them and
    evaluate `CalibrationGate`; the gate needs a policy whose own sample-size coherence check passes, and
    `CalibrationPolicy.starting_point()` (400 examples) will report insufficient evidence on a set this small. That is the correct outcome, not a defect.
13. **Record** (content-free): thresholds digest; dataset manifest digests; commit; judge model declaration and fingerprint; repetitions;
    heldout attempt number; per-source results (agent-run vs constructed, revealed only now via the key); per-stratum results; false positive
    and false negative case ids; abstention and failure counts; latency and tokens; spend against budget; the assessment digest; the
    agreement report and adjudication counts; any deviation from this procedure.
14. **Report negatives equally.** A run that misses a threshold is reported as missing it.

## Stop conditions

Stop (and report; do not continue or retry on the held-out set) if any of the following occurs:

* any predeclared inter-labeller floor is missed (go to the adjudication protocol);
* a labeller or adjudicator declaration shows a conflict the owner has not accepted, or independence was breached (discussion, model help, exposure to verdicts);
* the thresholds digest differs from the owner-confirmed one;
* the judge is the same family as the agent, or was tuned, prompted or few-shotted from the held-out cases;
* the leakage check is not clean, or the held-out manifest digest differs from the pinned one;
* spend or call limit reached, provider failure rate above the owner's limit (a failed call is an execution failure, never a verdict), or any sign content left the approved boundary;
* the held-out set has already been assessed once for this configuration;
* a class has fewer than the minimum cases: report as indicative and make no calibration claim.

## Sample sizes: why 53 cases is insufficient

Intervals are 95% Wilson score intervals, `wilson_interval` in `experimental.judge` (the same arithmetic as `scripts/p29_human_calibration.py`).

| Observed | n | Wilson 95% interval |
|---|---|---|
| 53 of 53 agree | 53 | 0.932 to 1.000 |
| 50 of 53 agree | 53 | 0.846 to 0.981 |
| 48 of 53 agree | 53 | 0.797 to 0.959 |
| 3 of 3 (a three-case UNKNOWN class) | 3 | 0.439 to 1.000 |
| 0 errors among 10 adjudicated FAIL | 10 | 0 to 0.278 error rate |
| 0 errors among 30 adjudicated FAIL | 30 | 0 to 0.114 |
| 1 error among 30 adjudicated FAIL | 30 | 0.006 to 0.167 |
| 0 errors among 60 adjudicated FAIL | 60 | 0 to 0.060 (approx.; 1 error: 0.003 to 0.089) |
| 29 of 30 agree | 30 | 0.833 to 0.994 |
| 28 of 30 agree | 30 | 0.787 to 0.982 |

Reading it: a perfect 53/53 only supports "agreement is at least about 93%" overall. The 53 cases are split across two dimensions and
three classes, and the earlier set had only 3 UNKNOWN-labelled relevance cases and fewer FAIL cases than PASS, so the per-class intervals are
far wider than the 53 suggests: a class of 10 cannot show an error rate below 28% even with no errors. Constructed answers are 31 of 53 and
are not a sample of real agent behaviour, so per-source results (22 real) are wider again. 48 of 53 (a 90.6% point estimate) has a lower bound
of 0.797, below the proposed 0.80 floor: the point estimate alone would mislead.

**Recommended target.** At least **30 adjudicated cases per class (PASS, FAIL, UNKNOWN) per dimension**, so at least 90 per dimension and
about 90 real items if both dimensions label the same items. 30 is chosen from the arithmetic: with 0 errors in 30 the upper bound is 0.114
(within the proposed 0.15 false-positive bound), with 1 error it is 0.167 (not). Wanting a 0.10 bound with 0 errors needs 35. For a
tighter claim (upper bound under 0.05 with 0 errors) about 75 per class are needed. These are minima for *making a claim*, not for running
the preparation. The full starting-point policy asks for 400 examples with 150 per class and that remains the reference for admission.
The set must also be expanded with what it lacks: unjustified refusals, conflicting and truncated evidence in several forms, an
adversarial stratum, and cases not authored by the same person who wrote the rubric. Use one example per source for independence.

## Repeatability

Run each case at least 3 times (`repetitions=3`); report the unstable-case rate (a case whose verdict is not identical across repeats) with
its Wilson interval against the predeclared floor. Repeatability measures the judge's noise, not its correctness.

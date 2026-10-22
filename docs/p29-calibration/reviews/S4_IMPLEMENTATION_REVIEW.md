# S4 Implementation Review: PR #10 (session4/p29-judge-calibration)

Reviewer: independent implementation reviewer (fresh context). Head reviewed: **0bde58d22a790f69465b8b0421fdb8021124a7f3** (I first started on ba2523d, then re-extracted the new head; every result below is for 0bde58d unless stated). Base b887999.

**Verdict: APPROVE_WITH_FIXES.** No BLOCKER and no HIGH defect found. The core admission logic, statistics and fail-closed hook are correct and independently confirmed. There are MEDIUM issues (leakage coverage, fingerprint blind spots, repeatability accounting) and a material test-strength gap: several fail-open mutants of rate-criterion code survive the author's tests.

Note: the author's worktree has uncommitted edits (admission.py, assessment.py, dataset.py, fingerprint.py, policy.py, schema, judge/_jsonschema.py, behaviour.py, new test_s4_engine_revision.py). I did not review those; they appear to address some findings below (engine revision, schema). Re-check them against this list.

## 1. What I ran vs only read

Own `git archive` extracts under `.../scratchpad/s4impl/` (h2 = 0bde58d, src = ba2523d, b0 = origin/main), own venvs (3.11 and 3.12, `uv pip install -e '.[dev,otel-test,http,langchain]'`). Author's worktree not modified.

Ran (head 0bde58d):
- `ruff check .`: All checks passed. `ruff format --check .`: 346 files already formatted. `mypy src`: Success, 84 source files. `python scripts/verify_p28_fixtures.py`: 4 fixture hashes verified.
- `python -m pytest`: **2002 passed, 1 skipped on Python 3.11 and on 3.12.** Baseline origin/main: 1802 passed, 1 skipped (matches the GAP_ASSESSMENT claim). So +200 tests, no existing test lost.
- On the earlier head ba2523d: ruff check failed (4 errors in scripts/p29_calibration_benchmark.py: 3x E501, 1x F401) and `ruff format --check` flagged 2 files. Fixed in 0bde58d; confirmed clean now.
- Independent Clopper-Pearson check: own exact-binomial bisection (math.comb) against `_stats.clopper_pearson` for every k in 0..n for n=1..60 plus n up to 300 (1935 cases): max abs difference 2.1e-15. Large n (1e4 to 1e9; k = 0, 1, n/2, n-1) all contain k/n and run in about 5 ms. Wilson/CP edge (0/46: 0.077074 vs 0.077062) matches ARCHITECTURE 14.6.
- Independent metrics reimplementation: 300 random tables (random labels, difficulties, PASS/FAIL/UNKNOWN/FAILURE/MISSING outcomes): every rate in `split_metrics` headline (committed_coverage, abstention, failure, missing, fnr/fpr conditional+effective, precision/recall both classes, accuracy cond/eff, verdict_rate, F1, failed/missing counts) matched. 0 mismatches.
- Adversarial probes (own scripts in `.../s4impl/t/`): forged/re-signed assessment documents, clock tests, hostile policies, dataset-rule evasions, fingerprint component sensitivity, async coordinator path (`evaluate()` and `submit()`), JSON overflow.
- Offline example run twice: byte-identical output. Benchmark script runs; figures match PERFORMANCE.md (load 0.80 s, metrics 0.045 s, gate decision median 0.80 ms, RSS 69.5 MiB).
- Mutation testing: 107 mutants (78 + 29), details in section 4.

Only read (not executed): SECURITY_AND_PRIVACY, PROVENANCE_SPEC, PLATFORM_PROPOSAL, schemas JSON, property-test internals, platform compatibility claims (COMPATIBILITY_REPORT platform runs not reproducible by me; platform repo not part of this PR).

## 2. Findings

### BLOCKER / HIGH
None.

### MEDIUM

**M1. Leakage check is vacuous when the train/calibration split is not loaded, and the assessment does not say so.** `dataset.py:342-368` computes leakage only over splits present in the manifest. A manifest with only `heldout` (allowed: `splits` holds 1-3 entries, `dataset.py:439`) yields `leakage_clean: true`. Reproduced: a heldout-only human-multi dataset reaches `calibrated` (the author's own `human_dataset` test fixture does exactly this, `test_admission.py:44`). The assessment records `cross_split` but not which splits were compared, so a consumer cannot tell "checked and clean" from "nothing to compare". Fix: record `splits_compared` in `dataset.leakage`; require at least two splits (or a `leakage_assessed` flag) for the `no_split_leakage` criterion to be `met`, else `inconclusive` (maps to insufficient_reference_evidence).

**M2. Leakage normalisation is trivially evaded by invisible/format characters.** `dataset.py:108-109` (`NFKC + casefold + split()`). Reproduced: a held-out copy of a train text with a zero-width space (U+200B), soft hyphen (U+00AD), a Cyrillic homoglyph, trailing/leading punctuation, or reordered parts is reported `leakage_clean=True`. Exact and case/whitespace/NFKC duplicates are caught. DATASET_SCHEMA.md:58 documents that near-duplicates and paraphrases are undetectable, but format-character stripping is within the stated "NFKC + casefold + whitespace" intent and is cheap. Fix: strip Unicode category Cf/Mn/Cc and (optionally) punctuation in the normaliser; add a test; keep the limitation text for paraphrase.

**M3. `implementation_version` is excluded from equivalence, so an SDK change to engine behaviour (reply parsing, repeat aggregation, confidence handling, repair logic) in a release that keeps the same template does not invalidate a calibration.** `fingerprint.py:116-121,123-127`, `admission.py:244`. `template_digest()` (behaviour.py) covers prompt text, output schema id, reason bound, temperature and TEMPLATE_ID only. Confirmed by probe: provider object/class swap gives an empty diff (declared limitation, documented), and nothing in the digest tracks decision-logic code. Author's uncommitted `test_s4_engine_revision.py` suggests this is being handled; verify it is in the behaviour digest, not only displayed. 

**M4. Repeatability silently drops cases with fewer than two stored runs.** `analysis.py:50-51` (`if len(runs) < 2: continue`) counts them nowhere: not in `cases_compared`, `excluded_for_failures` or `unstable_rate_worst_case`. A hand-built or partially failed table (a repetition simply absent, outcome MISSING) therefore reduces the denominator instead of counting as unstable in the worst case. `collect_judgments` always writes every run, so the shipped runner is not affected, but `JudgmentTable` is public. Mutant "drop excluded count" was killed, but no test pins "missing repeat row". Fix: count cases lacking a usable second run (missing row) as excluded for the worst-case rate, or report `cases_missing_repeats`.

**M5. Test strength: fail-open mutants survive (see section 4).** Most important: `_lower` "met if the upper bound is at least the minimum" (mutant 6) survives, i.e. no test has a committed-coverage case where lower < minimum <= upper. Likewise the `fn_basis` switch, `support_pass`, `adversarial_fail_support`, `unstable_rate_worst_case` vs plain rate, `inter_labeler_agreement` None -> MET, `heldout_split` criterion on a forged document, and manifest path containment have no killing test. The production code for each is correct today (I verified by reading and by probes), but regressions would pass CI.

### LOW

**L1. Third-reviewer / majority escape hatch lets `human_label` contradict every labeler.** `dataset.py:284-295`: with `adjudication.method = third_reviewer` and unanimous labelers, nothing constrains `human_label` (reproduced: two labelers "pass", human_label "fail", provenance `human_adjudicated`, loads). The adjudicator is not represented in `labels`. Provenance is documented as an attestation and the file is hash-pinned, so this is a rule gap, not an exploit; but "human_adjudicated" without an adjudicator record is weak. Fix: require an adjudicator label entry for `third_reviewer`, or document explicitly.

**L2. Unhandled `ValueError` (inf) and `OverflowError` paths in admission.** (a) `strict_loads` (`_json.py:37-47`) rejects the `NaN`/`Infinity` constants but `1e999` parses to `inf`; the schema accepts it. `CalibrationAssessment.from_json` succeeds, then `assess_admission` raises `ValueError: Out of range float values are not JSON compliant` from `canonical(allow_nan=False)` (`assessment.py:56-58`) and `CalibrationGate(...)` raises at construction. Reproduced. It fails closed (no admission) but as an uncaught exception from a documented pure function. (b) A forged, re-hashed document with a count of 10**400 raises `OverflowError` from `admission._prop`/`clopper_pearson`; the schema has no maximum on counts. (c) `CalibrationPolicy(max_fnr=10**400)` raises `OverflowError` from `math.isfinite` (`policy.py:108`) instead of `PolicyError`. Fix: reject non-finite floats in `strict_loads` (check `math.isfinite` in a `parse_float` hook), add `maximum` (e.g. 10**9) to count fields in the schema, convert the policy check to `float()` in try/except.

**L3. `not_future_dated` only compares the assessment time to `now`.** `dataset_created_at` later than the assessment `created_at`, or in the future, is not checked (`admission.py:235-242`, `_time`). Negative dataset age passes `dataset_current`. Low impact; add `dataset.created_at <= assessment.created_at + skew`.

**L4. Async coordinator path has no author test.** All admission-hook tests use `evaluate_sync` (`test_s4_admission_hook.py`). I tested `evaluate()` and `submit()` with an async `LLMJudge`: skip, allow, raising hook and non-verdict return all behave identically (skip -> `SKIPPED_BY_ADMISSION`, zero provider calls, zero evidence; allow -> one call; exception or garbage -> fail closed). All three paths share `_prepare` (`coordinator.py:784-851`), so the risk is low, but add one async test and one `submit` test.

**L5. Weak fixtures: boundary operators of the three-way test are untested.** `<=`/`<` and `>`/`>=` mutants in `_upper`/`_lower` survive (mutants 0, 1, 4, 5). The comparisons act on irrational-valued floats so the equality is practically unreachable, but the intended boundary semantics are not pinned.

### INFO

- I1. An assessment with only SHA-256 (no HMAC) is forgeable by anyone; a policy with `require_verified_integrity=False` will admit a forged, re-hashed document (I forged: n_labelled 10**9, huge denominators, inconsistent counts: some were caught by cross-criteria, others admitted). Documented ("unverified"), shown by `policy.below_starting_point` / `explain()`. The starting_point policy requires HMAC. The assessment document is not internally cross-validated (rates vs counts); acceptable given HMAC, but worth one sentence in SECURITY_AND_PRIVACY.
- I2. Fingerprint over-reports (conservative): any `model_label`, `JudgeLimits` (timeouts, token caps) or repeats change forces recalibration (`configuration_id`, `limits_digest`). Fingerprint under-reports: provider object/class, endpoint, sampling params outside the template, provider-side model changes (declared limitation).
- I3. CHANGELOG lists five statuses; code has six (`demonstration`, `admission.py:44-50`). COMPATIBILITY_REPORT (written after my review, so only noting) quotes 1985 passed; the head actually runs 2002 passed, 1 skipped on 3.11 and 3.12.
- I4. Labeler ids are free strings: two ids for one person satisfy "human_multi" (attestation; documented).
- I5. Admission `decide` runs before the lock and before the state/`max_evaluations_per_run` checks, so a gate is consulted for calls that are then rejected; harmless (pure, 0.8 ms).

## 3. Checks that passed (evidence of correctness)

- Three-way test: `_upper` met iff exact upper <= limit, violated iff exact lower > limit, else inconclusive; `_lower` mirror; Undefined (n=0) -> inconclusive -> `insufficient_reference_evidence` (`admission.py:165-190`). Policy coherence (zero-error feasibility) enforced (`policy.py:142-185`); synthetic <-> demonstration tie enforced.
- Status ladder (`admission.py:458-481`): the only route to `calibrated` is: no structure violation, no rate violation, no version violation, no inconclusive/missing data or rate, no time violation, `demonstration_only` false. Tried: stale clock (-> calibration_expired), future dated by >60 s (-> uncalibrated), future assessment, wrong fingerprint (-> incompatible), unsigned with required HMAC (-> uncalibrated), wrong/absent key (-> uncalibrated), tampered body without re-hash (-> mismatch, uncalibrated), forged `split=train` (-> uncalibrated), forged `leakage_clean=false` or synthetic provenance (-> insufficient), naive `now` (ValueError), bool/float counts (rejected by schema, `AssessmentError`), naive `created_at` (rejected by schema; local-timezone dependence checked with TZ=Asia/Kolkata), NaN policy (PolicyError), bool policy ints (PolicyError). No inadmissible path to `calibrated` found.
- Gate: fingerprint derived from the evaluator; `bound_to` requires identity and equivalence; decision recomputed per call with the injected clock; HMAC requirement enforced at construction.
- Coordinator hook: ordering is run-not-recording > admission > sampling (`coordinator.py:830-838`); `except Exception` -> `admission_error`; non-verdict return -> `admission_error`; `BaseException` propagates (tested by author); skip makes no provider call and no evidence/failure; counters separate unset vs `UNGATED`; `IndicatorBinding` enforces `bound_to` at construction. Default behaviour unchanged: all 1802 pre-existing tests still pass; `reason_code` slot in the skip report was previously always `None` for these kinds.
- Provenance derivation (weakest case provenance must equal the declared split provenance), symlink refusal, size caps, manifest pin and split digests, strict JSON (duplicates, constants, depth), unique ids and the one-to-one split-name checks all work as documented in direct probes. Judge construction cost of the new `behaviour_of`: 0.05 ms.
- Offline example deterministic; benchmark figures reproduce.

## 4. Mutation testing

107 mutants applied one at a time to a fresh copy of 0bde58d, run against `tests/unit/experimental_calibration`, `tests/unit/experimental_judge/test_s4_admission_hook.py`, `tests/property/test_calibration_properties.py`, `tests/compat/test_experimental_judge_api.py` (211 tests). Batch 1: 78 mutants (2 no-apply); batch 2: 29 (1 no-apply). Totals: 75 killed, 29 survived (of which about 10 are equivalent or near-equivalent, listed below), 3 did not apply (one of these re-run in batch 2).

Killed (selection): all three-way variants except boundary operators and `_lower` hi-bound; future-date check removed and huge skew; integrity_verified, integrity requirement, digest mismatch, verify not called; fingerprint always equivalent / diff ignored; rubric version match; leakage criterion; provenance accepted; demonstration to calibrated; ignore insufficient / expired; calibration_valid and dataset_current; early structure exit removed; adversarial tolerance; gate integrity, frozen clock (per-call recompute), bound_to identity; fnr_effective, committed_coverage, fpr_effective, abstention, failure_rate, missing_rate denominators/numerators; F1 formula and F1 undefined->0; kappa single-class; CP alpha and CP upper quantile; repeatability worst-case and excluded count; weakest-provenance derivation; symlink refusal; manifest pin; split digest; multi-labeler minimum; normalised-key leakage; policy coherence; synthetic<->demonstration rule; zero-error feasibility; duplicate (example, run); outcome ignores run_index; extra-judgment check; heldout-only build; drift expiry; admission never applied; fail-open on exception and on non-verdict; bound_to enforcement dropped; both coverage counters; swap admission after sampling; fp_basis, repeat_cases, support_fail, indeterminate fraction, labeler agreement, run_index guard, assessment size cap, case ids in leakage.

**SURVIVING mutants (29), grouped:**

Test gaps worth closing (production code currently correct):
1. `_lower` MET when upper bound >= minimum (`admission.py:184`, `elif interval[1] >= minimum`). Fail-open for committed_coverage. **Most important.**
2. `heldout_split` criterion removed (`admission.py:229-233`): only reachable via a forged document; no test forges `dataset.split`.
3. `fn_basis` ignored (always conditional), `admission.py:359-365`.
4. `support_pass` criterion dropped (`admission.py:292`).
5. `adversarial_fail_support` replaced by a constant pass (`admission.py:294-300`).
6. `unstable_rate_worst_case` replaced by plain `unstable_rate` (`admission.py:376`).
7. `inter_labeler_agreement` None -> MET instead of INCONCLUSIVE (`admission.py:327-328`).
8. `rubric_id` comparison removed from `rubric_matches_fingerprint` (`assessment.py:207`) (version and dimension... see equivalents below).
9. Manifest filename containment removed (`dataset.py:326`, `Path(name).name == name`): untested security control. I confirmed by reading that the real code refuses `../x`; no test asserts it.
10. NFKC dropped from `_normalise` (`dataset.py:109`): no test for compatibility-form duplicates.
11. Duplicate JSON member rejection removed (`_json.py:15`) and depth limit removed (`_json.py:45`): no surviving-test coverage in the targeted suites (may be covered by a hostile-schema test elsewhere; these mutants survived the targeted set).
12. `MAX_CASES_PER_SPLIT` in-loop cap removed (`dataset.py:492`) and "unique ids within a split" requirement removed (`dataset.py:502`; leakage still flags duplicates).
13. `from_dict` fingerprint digest check removed (`fingerprint.py:157`): a doc with an inconsistent `behaviour_digest` would be accepted if re-hashed.
14. Boundary operators `<=`/`<`, `>`/`>=` in `_upper`/`_lower` (mutants 0, 1, 4, 5): L5.

Equivalent or near-equivalent (not counted as real gaps): `bound_to` fingerprint re-check (evaluator immutable after construction; identity check is killed), `equivalent_to` ignoring `model` (model compared separately in `diff`), second read-size check after `lstat` size check, `verify` skipping `digest_matches` (HMAC covers the same body), `indeterminate` UNRESOLVED clause (human_label must be "unknown" anyway), `accepted <= _HUMAN` (subsumed by the SYNTHETIC check), `judgments._validate` dimension check (judge raises anyway), fingerprint-dimension comparison (dimension also enforced elsewhere), FAILURE-with-confidence check (`judgments.py:76`; untested but trivial). One mutant (`stat size cap`) also survived because the post-read length check is redundant.

## 5. Recommended fixes (priority order)

1. M1: record and require two compared splits for the leakage criterion (or mark inconclusive).
2. M3: confirm the uncommitted engine-revision work puts behaviour-determining code in the behaviour digest; document that `implementation_version` is display-only.
3. M5/section 4 items 1-9: add killing tests, in particular a committed-coverage fixture with lower < min <= upper, a forged `split`, `fn_basis` and `support_pass` cases, and a `../` manifest-name test.
4. M2: strip format characters in `_normalise`.
5. M4: count missing repeat rows toward the worst-case instability.
6. L2: reject non-finite floats at parse, bound counts in schema, make policy overflow a PolicyError.
7. L1, L3, L4, I3: as described.

## 6. Verdict

**APPROVE_WITH_FIXES.** Statistically and logically sound; no path was found by which an inadmissible judge becomes admissible, and the hook is fail-closed and backwards compatible (1802 pre-existing tests pass unchanged; head lint/format/mypy/fixtures green; 2002 tests pass on 3.11 and 3.12). The MEDIUM items should be fixed or explicitly accepted before the PR leaves draft; the surviving mutants indicate regression protection is weaker than the test count suggests.

---

## Re-check at f68b1e9

Head f68b1e9af195f50ef99d1b133c468a0219feda89, fresh `git archive` extract (`.../s4impl/h3`). Code under test was loaded via PYTHONPATH from that extract (the editable re-install could not reach PyPI, so I did not rely on it).

### Counts
- `ruff check .`: All checks passed. `ruff format --check .`: 348 files already formatted. `mypy src`: Success, 84 source files. `verify_p28_fixtures.py`: 4 fixture hashes verified.
- `pytest`: **2053 passed, 1 skipped on Python 3.11 and on 3.12** (was 2002 at 0bde58d; origin/main 1802).

### Per-finding status

| ID | Status | Evidence |
|---|---|---|
| M1 leakage vacuous | **Closed, with a residual (N2)** | Heldout-only dataset now -> `insufficient_reference_evidence`, failing `leakage_checked_against_other_splits` (probe). Mutant removing the criterion killed. Residual: an EMPTY `train` split counts as "checked against" and the judge reaches `calibrated` (probe). |
| M2 normalisation | **Closed** (homoglyph documented) | ZWSP, soft hyphen, punctuation, part reorder now flagged; homoglyph still `clean` (documented limit). Mutants dropping punctuation, NFKC, or part sorting killed. Side effect: punctuation stripping gives false positives ("refund 1.5 days" vs "refund 15 days", "3,000" vs "3000", "a-b" vs "ab" are all flagged as duplicates). Safe direction (over-report), INFO. |
| M3 engine revision | **Closed, partly** | `ENGINE_REVISION` is in `_BEHAVIOUR_FIELDS`, the schema and the digest; bumping it is killed by the pin test. The pin hashes the source of only `parse_output`, `interpret_reply`, `map_verdict`, `aggregate_repeats` in `judge/core.py`. The comment in `behaviour.py` also promises "repair and retry logic", which lives in `_engine.py` and is NOT pinned (LOW, N4). |
| M4 single-run cases | **Closed** | `single_run_cases` is recorded and `repeatability_measured_on_all_cases` is a data criterion; mutant killed. Consequence to document: a judge run with `repetitions=1` can never be calibrated. |
| M5 / all surviving mutants | **Closed** | See mutation re-run below. |
| L1 third_reviewer | **Closed** | Unanimous labels must equal `human_label` for every method except `unresolved`; probe refused; mutant killed. Unresolved now also needs disagreeing labels. |
| L2 parse/overflow | **Closed, with a residual (N1)** | `1e999`, `-1e999`, `[1e400]` and 19-digit ints are refused by `strict_loads`; `max_fnr=10**400` and `min_examples=10**10` give `PolicyError`; bounded-int, finite-float and overflow-safe mutants killed. Residual N1 below. |
| L3 dataset after assessment | **Closed** | Parse-time check (`dataset_created > created + 60 s` -> `AssessmentError`) plus a future-dataset clause in `dataset_current`. The second clause is nearly redundant (its mutant survives, equivalent). |
| L4 async tests | **Closed** | New async `evaluate`/`submit` tests in `test_s4_admission_hook.py`; the suite passes. |
| L5 boundary operators | **Closed** | All four `<=`/`<`/`>`/`>=` mutants killed by `test_boundaries_and_guards.py`. |
| I1 (SHA-only forgery) | **Closed by design** | A calibrating `CalibrationPolicy` now raises `PolicyError` unless `require_verified_integrity=True` (probe; mutant killed). |
| I3 (status count and report figures) | Not re-verified in full | CHANGELOG diff touched one line; I did not re-read the final text beyond the suite passing `test_docs.py`. |

### Mutation re-run (head f68b1e9)
44 mutants: my 29 prior survivors re-expressed against the new code, plus 15 aimed at the new behaviour (leakage-checked criterion, single-run criterion, future-dataset clause, consistency check, HMAC domain separation on verify, integrity requirement in the policy, punctuation normalisation, part sorting, O_NOFOLLOW/O_NONBLOCK flags, regular-file check, third-reviewer rule, bounded-int, finite-float, overflow-safe `_is_number`, engine revision).

Killed 33 of 44. **Still surviving (11), all equivalent or near-equivalent, none a regression gap of consequence:**
1. `bound_to` fingerprint re-check: the evaluator is immutable once built, so it is equivalent.
2. Post-read size check and `fstat` size check (each is redundant with the other and with the bounded read).
3. UNRESOLVED clause in `indeterminate`: `human_label` must be "unknown" anyway.
4. `accepted <= _HUMAN` in the policy: subsumed by the SYNTHETIC rule.
5. `equivalent_to` ignoring `model`: the model is compared separately via `diff`.
6. `verify` skipping `digest_matches`: the HMAC covers the same body.
7. FAILURE-with-confidence check in `Judgment` (trivial, untested).
8. `_validate` dimension check in `judgments.py`: the judge raises anyway.
9. Fingerprint-dimension comparison in `rubric_matches_fingerprint`: dimension is enforced elsewhere.
10. In-loop `MAX_CASES_PER_SPLIT`: the manifest `case_count` (<= 20000) must equal the line count, so it is redundant.
11. `future_dataset` clause in `dataset_current`: nearly redundant with the parse-time consistency check.

All 14 materially important survivors from the first review (the `_lower` hi-bound mutant, heldout-split, `fn_basis`, `support_pass`, adversarial support, worst-case instability, agreement None, `rubric_id`, path containment, NFKC, duplicate keys, depth, `from_dict` digest, unique ids, boundary operators) are now killed.

### Review of the new behaviour
- **Policy requires verified integrity for calibrating policies:** correct and effective. `CalibrationGate` still demands the key at construction. No bypass found.
- **HMAC domain separation:** `_HMAC_DOMAIN` prefix applied in both `sign` and `verify`; an old-style HMAC (no prefix) no longer verifies (probe). Breaking for anything signed earlier, acceptable for Experimental, but worth one line in the CHANGELOG.
- **Consistency checks at parse:** numerator <= denominator everywhere, count identities (answered + abstained + failed + missing = n_labelled, tp+fn+fp+tn = answered, support sums, judged), unstable <= compared, timestamps aware, dataset not after assessment. Correct. They do not cross-check the rates blocks against the counts blocks (a forged `rates.*` numerator with consistent counts still parses); with HMAC mandatory for calibrating policies this is INFO.
- **Descriptor-based bounded read:** opens with `O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC`, `fstat` on the descriptor, regular-file check, reads at most `limit+1` bytes. Sound on POSIX; FIFO and directory are refused; symlink gives ELOOP -> "symlinks are refused" (killed mutants for both flags and the regular-file check). Caveat N3.
- **`judge/_jsonschema.py` trailing-newline change:** the validator now rejects a string that ends in `\n` when the pattern ends in `$` (matching ECMA-262). All patterns in the repo's schemas are `^...$` over character classes that exclude `\n`, so the only behavioural difference for existing judge schemas (`calibration-case`, `calibration-report`) is that a value such as an id with a trailing newline, previously accepted through Python's `$` semantics, is now rejected. It is a tightening, in an Experimental validator, and all existing judge suites pass; I classify it INFO but it should appear in the CHANGELOG as a behaviour change of the existing judge schemas.

### New findings
- **N1 (LOW):** `MAX_SIZE = 10**9` is above `timedelta` range. `validity_days=10**9` or `max_dataset_age_days=10**9` builds a valid policy, then `assess_admission` raises `OverflowError` (probe). The gate path fails closed through the coordinator's `admission_error`, but the pure function raises. Cap day fields at 36500 or so.
- **N2 (MEDIUM, residual of M1):** `leakage_checked_against` lists the other splits in the manifest even when a split has zero cases, so `{"train": [], "heldout": ...}` makes the criterion `met` and the judge `calibrated` (probe). Fix: list only splits with at least one case, or require a minimum size for the compared splits.
- **N3 (LOW):** where `O_NOFOLLOW` is not defined (Windows), the `getattr(..., 0)` fallback means symlinks are followed; the earlier `lstat` refusal was cross-platform and is gone. Either keep an `lstat` check as well, or state that symlink refusal is POSIX-only.
- **N4 (LOW):** `ENGINE_REVISION`'s pin covers `judge/core.py` parser and mapping only; retry, repair and budget logic in `_engine.py`, and `REQUESTED_TEMPERATURE` (which is in the template digest) are covered separately; retry/repair behaviour changes would not trip the pin. Extend the pinned source set or narrow the comment.
- **N5 (INFO):** punctuation-stripping normalisation over-reports numeric near-duplicates (see M2).

### Updated verdict
**APPROVE_WITH_FIXES (reduced scope).** All earlier MEDIUM and LOW findings are closed or reduced to the residuals above; no BLOCKER or HIGH. Required before leaving draft: N2 (an empty comparison split must not satisfy the leakage criterion). Recommended: N1, N3, N4, and a CHANGELOG note for the HMAC domain change and the stricter `$` handling in the shared validator.

---

## Confirmation at 58e4507

Head 58e4507df2a814f84fb8db1c51bf2044e6ea07b2, fresh `git archive` extract (`.../s4impl/h4`), code loaded via PYTHONPATH from that extract.

### Counts
`ruff check .`: All checks passed. `ruff format --check .`: 348 files already formatted. `mypy src`: Success, 84 source files. `verify_p28_fixtures.py`: 4 fixture hashes verified. `pytest`: **2056 passed, 1 skipped on Python 3.11 and on 3.12** (was 2053 at f68b1e9).

### Status
| Item | Status | Evidence |
|---|---|---|
| N2 empty split | **Closed** | Probe: `{"train": [], "heldout": ...}` now gives `leakage_checked_against: []` and `insufficient_reference_evidence`; held-out-only still fails the criterion. Mutants "empty split counts" and "criterion removed" killed. |
| N1 day caps | **Closed** | `validity_days` / `max_dataset_age_days` of 10**9 and 999999999 now raise `PolicyError` (cap 36500). Mutants (cap removed, cap value 10**9) killed. |
| N3 symlinks without `O_NOFOLLOW` | **Closed in code; untested on POSIX** | The `lstat` branch is added (`dataset.py`, `if not hasattr(os, "O_NOFOLLOW")`). It is unreachable on macOS/Linux, so both mutants of it survive (expected; no monkeypatch test). Not a defect; I could not execute the Windows path. |
| N4 `_engine.py` pin | **Closed** | `test_s4_engine_revision.py` now also pins the SHA-256 of the whole `_engine.py` file; appending a comment line to the file fails that test (reproduced); `engine_revision="2"` mutant killed. `behaviour.py` comment corrected. Residual INFO: the pin is on file bytes, so any cosmetic edit or an end-of-line conversion forces a revision decision (conservative by design). |
| CHANGELOG line (validator tightening) | **Closed** | Present in the diff; reverting the validator change is killed by a test. |
| N5 | Accepted (INFO) | No action. |

### Mutation re-run (this head)
12 mutants touching these areas plus three carry-overs (integrity requirement, single-run criterion, HMAC domain): 10 killed, 2 survived. The 2 survivors are the POSIX-unreachable `lstat` branch (N3), equivalent on this platform.

### Open items
None blocking. Recommended, optional: a monkeypatch test (`monkeypatch.delattr(os, "O_NOFOLLOW")`) so the fallback symlink refusal is exercised.

### Final verdict
**APPROVE.** All BLOCKER/HIGH (none were found), MEDIUM and LOW findings from my reviews are closed; CI-equivalent checks are green on 3.11 and 3.12; the remaining mutant survivors are equivalent or platform-unreachable. The PR may go to owner review.

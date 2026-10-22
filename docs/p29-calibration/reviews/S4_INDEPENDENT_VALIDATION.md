# S4 independent validation: PR #10 (agent-reliability), head ba2523d

Validator: fresh context, own `git archive` extract and venvs under the session scratchpad. The author worktree was not modified. No paid or external calls. Date 2026-10-22.

## Verdict: GO for owner review (not for merge), with conditions

Conditions:
1. Fix the red required CI context "Lint, format, and type-check" (F-01) before merge.
2. Consider the two surviving mutations (F-03, F-04).

## Executed vs only read

| Item | Executed or read |
|---|---|
| Full suite, 3.11/3.12/3.13 with coverage | Executed |
| ruff check, ruff format --check, mypy src | Executed (py3.12, ruff 0.17.1, mypy 2.4.0) |
| build, verify_release_artifacts, node reference | Executed |
| Clean wheel install, minimal end-to-end | Executed |
| Existing contract/compat/judge/HTTP tests | Executed |
| Platform fixtures, platform tests against own PostgreSQL 17 | Executed |
| Walkthrough x2 (network blocked), demo regeneration, benchmark | Executed |
| Flakiness 5x | Executed |
| Traceability sampling + 13 mutations | Executed |
| Doc numeric claims | Executed where noted; others read only |
| `gh pr checks` | Executed (read-only) |

## Results

1. Full SDK suite (`pip install -e ".[dev,otel-test,http,langchain]"`, `verify_p28_fixtures.py`, `pytest --cov --cov-report=term-missing`):
   - py3.11: 1998 passed, 1 skipped (74 s).
   - py3.12: 1998 passed, 1 skipped (67 s).
   - py3.13: 1998 passed, 1 skipped (66 s).
   - Total coverage 96% on each. Fixture verification: "4 fixture hashes verified" on each.
   - The author's number was "about 1985"; the actual figure is 1998. This is a difference in the author's report only (F-06).
2. Static checks:
   - `ruff check .` FAILS with 4 errors.
     - `scripts/p29_calibration_benchmark.py`: E501 at lines 3, 145 and 162, and F401 (unused `LabelProvenance` import, line 29).
   - `ruff format --check .` FAILS: 2 files would be reformatted.
     - `scripts/p29_calibration_benchmark.py`.
     - `docs/p29-calibration/README.md` (ruff 0.17 formats the Python code block in the Markdown).
   - `mypy src`: Success, no issues in 84 source files.
3. `python -m build` built `agent_reliability-1.3.0` sdist and wheel. `verify_release_artifacts.py` exited 0 (metadata, base wheel and offline examples, sdist, http extra, langchain extra, otel extra, downstream strict mypy: all ok). `node scripts/verify_p28_reference.mjs`: 76 canonical vectors, 74 acknowledgement vectors passed.
4. Clean install of the wheel into a fresh venv, no extras:
   - `importlib.metadata.requires('agent-reliability')` lists only requirements with `extra == ...` markers (dev, http, langchain, otel, otel-test). No unconditional requirement.
   - `agent_reliability.experimental.calibration` imports. The three JSON schemas are shipped in the wheel.
   - A minimal end-to-end run, using only the installed wheel with `python -I`, went from synthetic dataset to scripted judge to assessment to `assess_admission`. Result: `insufficient_reference_evidence`, admissible False, integrity verified. This is the expected result for synthetic labels under `starting_point()`.
5. Existing suites:
   - `tests/contract/test_p29_*.py`, `tests/compat`, `tests/unit/experimental_judge`: 764 passed, 1 skipped.
   - HTTP/exporter tests (`-k "http or exporter"`): 469 passed.
   - `git diff origin/main..ba2523d --name-status` shows these modified (M) files, everything else is added (A):
     - CHANGELOG.md.
     - docs/P29_PILOT_SAFEGUARDS.md, docs/README.md, docs/VERSIONING.md.
     - `src/agent_reliability/experimental/judge/{__init__,coordinator,judge,sync}.py`.
     - `tests/compat/test_experimental_judge_api.py` (additive snapshot only).
   - The source diffs are additive: new exports, optional `admission` field defaulting to None, new counters, new disposition. The only deletions are a reformatted return and the `ReportKind` literal.
   - Nothing was touched under stable modules, the HTTP exporter, the wire, P28 fixtures or pyproject. `dependencies = []` is confirmed at pyproject line 36.
   - No existing test was modified besides the additive compat test.
6. Platform compatibility:
   - `verify_p28_fixtures.py --platform-root ...`: "4 fixture hashes verified; platform comparison: True".
   - Platform checkout at 805b9c7, extract installed in a py3.11 venv, then the SDK extract installed editable on top.
   - Own PostgreSQL 17 on 127.0.0.1:55999, database `are_s4val_test`, env vars set as specified.
   - Result of the five specified test files: **130 passed, 1 xfailed** (15 s). The xfail is platform-side and was not investigated.
   - The cluster was stopped and its data directory and socket dir were removed.
7. Walkthrough, demo data and benchmark:
   - `examples/judge_calibration_offline.py` was run twice under the installed wheel with socket connect/getaddrinfo patched to raise. Both runs exited 0, the output was byte-identical (54 lines), and there was no network attempt.
   - `scripts/p29_calibration_demo_data.py` regenerated into a temp dir: `diff -r` against `tests/fixtures/p29_calibration/demo` is byte-identical. Manifest sha256 is 110dc52d...a174.
   - Benchmark on py3.12 versus `PERFORMANCE.md` (py3.11):

| Stage | Measured | Doc |
|---|---|---|
| load | 0.84 s | 0.77 s |
| table | 0.015 s | 0.015 s |
| split_metrics | 0.036 s | 0.046 s |
| repeatability | 0.009 s | 0.013 s |
| build_assessment | 0.049 s | 0.062 s |
| gate decision | 0.73 ms median, 0.77 ms p95 | 0.8 ms median, 0.82 ms p95 |
| assessment size | 38 086 B | 38 KB |
| peak RSS | 70.1 MiB | about 70 MiB |

   All agree in order of magnitude and in practice closely. The pre-fix "5.8 s / 2.8 s" quadratic timing was NOT reproduced because it would need the old code. The current 0.036 s is consistent with the fix.
8. Flakiness: `tests/unit/experimental_calibration` + `tests/property/test_calibration_properties.py` + `tests/unit/experimental_judge/test_s4_admission_hook.py`, run 5 times: 194 passed each time, no flakes.
9. Traceability:
   - I checked every `test_*` name cited in `TRACEABILITY_MATRIX.md` against the source. All 25 function-name prefixes exist. The apparent "MISSING" entries in my script were file names, not functions.
   - I read the test names against the claims (rows 4, 7, 12, 16, 19, 20, 21, 22, 24, 30 and others) and exercised them by mutation. 13 mutations were applied to a copy of the source, and the tests (calibration, judge, compat, contract) were run for each:

| # | Mutation | Result and first failing test |
|---|---|---|
| M1 | fail-open when the hook raises | KILLED `test_a_failing_or_malformed_hook_fails_closed_without_leaking` |
| M2 | verdict ignored | KILLED `test_the_walkthrough_runs_offline_and_is_deterministic` |
| M3 | ungated counter off | KILLED `test_an_uncalibrated_judge_is_skipped_when_gated_and_counted_when_not` |
| M4 | `bound_to` check removed | KILLED `test_a_gate_cannot_be_attached_to_a_different_judge` |
| M5 | demonstration status removed | KILLED `test_a_demonstration_policy_can_only_demonstrate` |
| M6 | expiry status removed | KILLED `test_expiry_and_stale_datasets` |
| M7 | `failure_rate` cap ignored | **SURVIVED** |
| M8 | Clopper-Pearson upper quantile skewed | KILLED `test_clopper_pearson_matches_independent_exact_values` |
| M9 | content-level cross-split leakage not flagged | **SURVIVED** |
| M10 | HMAC verify always true | KILLED `test_verified_integrity_policy_requires_the_hmac` |
| M11 | F1 zero-denominator returns 0.0 | KILLED `test_always_unknown_judge_...` |
| M12 | template digest ignores temperature | KILLED `test_template_digest_is_pinned_to_the_golden_prompt_fixture` |
| M13 | reason-code validator off | KILLED `test_verdict_validation` |

   11 of 13 were killed.
10. Doc claims checked:
    - `starting_point()` values printed from the code match ARCHITECTURE (400/150/30, 0.80, 0.20, 0.02, 0.02, fnr 0.05 effective, fpr 0.10 conditional, unstable 0.05 over 150, indeterminate 0.20, agreement 0.80, human_multi/human_adjudicated, validity 90, age 365).
    - "Wilson is not always narrower, 0/46: Wilson upper 0.0771, exact 0.0770": measured Wilson 0.07708, exact 0.07706. Confirmed.
    - Caps in `dataset.py`/`assessment.py`/`judgments.py` match PERFORMANCE.md (64 KiB / 8 MiB / 25 MiB, 20 000 cases, 64 KiB line, 1 MiB assessment, repetitions 1 to 10).
    - The "byte cap binds at about 420 bytes per case" claim is arithmetically right (8 MiB / 20 000 = 419 B). The "10.6 MB for 20 000 cases" figure I could not reproduce: 5.3 MB / 12 000 x 20 000 = 8.8 MB (F-05).
11. `gh pr checks 10` (final read, head ba2523d, draft, mergeable):
    - Lint, format, and type-check: **fail**.
    - Test stable contracts py3.11, py3.12, py3.13: pass.
    - Independent Node reference check of the P28 contract fixtures: pass.
    - Release artifacts, extras, examples, and typing: pass.

## Findings

| ID | Severity | Finding | Evidence | Fix |
|---|---|---|---|---|
| F-01 | HIGH | CI "Lint, format, and type-check" is red, and I reproduced it locally. | `ruff check .`: 3x E501 and 1x F401 in `scripts/p29_calibration_benchmark.py` (lines 3, 29, 145, 162). `ruff format --check .`: that file plus `docs/p29-calibration/README.md` need reformatting. mypy is clean. | Run `ruff check --fix` and `ruff format` on those two files and wrap the long lines. The fix is trivial, but the PR cannot merge until it is done. |
| F-02 | LOW | The suite count in the author's report (about 1985) differs from the actual 1998. | The same count on all three Pythons. | Update the reports. |
| F-03 | LOW | Mutant M7 survived: the `max_failure_rate` threshold has no isolated test that violates it. | Criterion is built via `_upper("failure_rate", ...)`; ignoring the cap kept all tests green. | Add a test where only the failure rate exceeds the cap. |
| F-04 | LOW | Mutant M9 survived: cross-split detection of identical content or normalized content with different case IDs is not asserted. | `test_dataset.py:325` asserts `cross_split`, which is probably satisfied via the duplicate-id clause. | Add a case with different IDs but identical content across train and heldout. |
| F-05 | INFO | The PERFORMANCE.md figure "20 000 cases of the benchmark's size is 10.6 MB" is not reproducible (I compute about 8.8 MB). The conclusion (refused by the 8 MiB cap) still holds. | Benchmark `dataset_bytes` 5 304 890 for 12 000 cases. | Re-measure or reword. |
| F-06 | INFO | The quadratic-fix timing (5.8 s / 2.8 s) was not independently reproduced. | Would need the old code. | None. |
| F-07 | INFO | Platform run showed 1 xfailed in the platform's tests (pre-existing, not SDK related). | 130 passed, 1 xfailed. | None. |

No BLOCKER. The other checks matched: dependencies stay empty, the wheel's requirements are all extra-conditional, the diff to existing source is additive and confined to `experimental/judge`, the default behaviour (admission=None) is unchanged, and the platform integration passes with the branch SDK.


---

# Re-validation at 58e4507

Head 58e4507df2a814f84fb8db1c51bf2044e6ea07b2 (fresh `git archive` extract, fresh venvs, py3.11/3.12/3.13). The earlier sections above are unchanged and refer to ba2523d.

## Verdict: GO for owner review (not for merge)

Conditions: the py3.11 CI job must finish green (see item 11), and the stale numbers in COMPATIBILITY_REPORT.md and GO_NO_GO.md must be updated by the author (F-R2).

## Results (all executed by me)

1. **Full suite** (`pip install -e ".[dev,otel-test,http,langchain]"`, `verify_p28_fixtures.py`, `pytest --cov --cov-report=term-missing`):
   - py3.11: 2056 passed, 1 skipped (73 s).
   - py3.12: 2056 passed, 1 skipped (65 s).
   - py3.13: 2056 passed, 1 skipped (66 s).
   - Coverage 96% on each. Fixture verification: "4 fixture hashes verified".
   - The py3.11 editable install first failed once because PyPI timed out (a network problem in my sandbox). The retry succeeded.
2. **Static checks** (py3.12):
   - `ruff check .`: All checks passed.
   - `ruff format --check .`: 348 files already formatted.
   - `mypy src`: no issues in 84 source files.
3. **Build and release checks:**
   - `python -m build` built the sdist and wheel; `verify_release_artifacts.py` passed (all stages ok); the Node reference check passed with 76 canonical and 74 acknowledgement vectors.
   - **Sdist contents** (`tar tzf`): under `docs/p29-calibration/` the sdist contains only ARCHITECTURE, DATASET_SCHEMA, PERFORMANCE, PROVENANCE_SPEC, README and SECURITY_AND_PRIVACY. It excludes GAP_ASSESSMENT, PLATFORM_PROPOSAL, TRACEABILITY_MATRIX, COMPATIBILITY_REPORT, GO_NO_GO and `reviews` (0 matches). The wheel contains no `docs/` entries.
4. **Clean no-extras wheel install:**
   - `requires('agent-reliability')` shows only `extra ==` requirements.
   - The calibration package imports.
   - The minimal end-to-end run (dataset, scripted judge, assessment, status) gives `insufficient_reference_evidence`, admissible False, integrity verified.
   - `dependencies = []` is still set at pyproject line 36.
5. **Unchanged-behaviour suites:**
   - Contract, compat and judge tests: 768 passed, 1 skipped.
   - HTTP/exporter tests: 469 passed.
   - Changes since ba2523d in tracked existing files:
     - `pyproject.toml`: only sdist `exclude` entries added; dependencies unchanged.
     - `judge/_jsonschema.py`: the shared validator now rejects a value with a trailing newline when the pattern ends in `$`. This is intentional (it matches the ECMA-262 reading) but is a behaviour change to an existing module (F-R3).
     - `tests/compat/test_experimental_judge_api.py`: the snapshot gained `engine_revision`.
   - `git diff origin/main..58e4507 --name-status`: modified files are CHANGELOG, 3 docs, pyproject, `judge/{__init__,_jsonschema,coordinator,judge,sync}.py`, and the compat test. Nothing under stable modules, the HTTP exporter, the wire or the P28 fixtures.
6. **Platform:**
   - `verify_p28_fixtures.py --platform-root` gives "platform comparison: True".
   - Branch SDK installed editable over the platform checkout (805b9c7), with my own PostgreSQL 17 on port 55999.
   - The five specified test files: **130 passed, 1 xfailed**.
   - The cluster was stopped and removed. The postgres process still visible on port 55432 is not mine and was left alone.
7. **Walkthrough:**
   - Two runs under the installed wheel with network calls patched to raise: both exited 0, output byte-identical, and identical to the output at ba2523d.
   - Demo regeneration is byte-identical to `tests/fixtures/p29_calibration/demo` (manifest sha256 110dc52d...a174).
   - Benchmark (py3.12): load 0.93 s, table 0.014 s, split_metrics 0.035 s, repeatability 0.009 s, build_assessment 0.048 s, gate decision 0.73 ms median / 0.75 ms p95, assessment 38 176 B, peak RSS 70.9 MiB. This is consistent with PERFORMANCE.md (same order of magnitude; load is about 20% slower than the 0.77 s documented).
8. **Flakiness:** the calibration unit tests, property tests and admission-hook tests, run 5 times: 250 passed each time.
9. **Mutations** (21 total, applied to a copy of the 58e4507 source; the run covered calibration, judge, compat and contract tests):
   - **Re-run of M1 to M13** from the first round: **all 13 are now killed**. M7 is killed by the new `test_the_failure_rate_cap_is_enforced_on_its_own`, and M9 by the new `test_cross_split_leakage_is_found_when_identical_content_has_different_case_ids`.
   - **New mutations N1 to N8:**

| # | Mutation | Result |
|---|---|---|
| N1 | a calibrating policy may skip verified integrity | KILLED `test_a_calibrating_policy_must_require_verified_integrity` |
| N2 | `integrity_verified` criterion always met | KILLED `test_verified_integrity_policy_requires_the_hmac` |
| N3 | `engine_revision` hardcoded to "1" | survived, but this is an equivalent mutant because the constant is "1" |
| N4 | JSON integer digit limit lifted | KILLED `test_strict_json_rejects_duplicates_depth_overflow_and_absurd_numbers` |
| N5 | trailing-newline tightening removed | KILLED `test_trailing_newline_does_not_satisfy_an_anchored_schema_pattern` |
| N6 | `O_NOFOLLOW` dropped | KILLED `test_a_symlinked_split_file_is_refused` |
| N7 | regular-file check removed | KILLED `test_a_fifo_or_other_special_file_is_refused_without_blocking` |
| N8 | normalized-content leakage not collected | KILLED `test_fullwidth_and_compatibility_forms_are_folded_when_looking_for_leakage` |
| N3b | `ENGINE_REVISION` bumped to "2" | KILLED `test_a_changed_engine_revision_makes_a_calibration_incompatible` and `test_the_parser_and_mapping_source_is_pinned_to_the_engine_revision` |

   - Overall: 20 of 21 killed; the one survivor is the equivalent mutant N3, and N3b replaces it with a real mutation that is killed.
10. **Doc claims:**
    - `starting_point()` still gives 400/150/30, 0.8, fnr 0.05, fpr 0.1, 150 repeat cases, 90 days, and verified integrity True.
    - Wilson upper 0.07708 against exact 0.07706 for 0/46: confirmed.
    - Caps match the code.
    - PERFORMANCE.md now says "about 8.8 MB", which matches my estimate.
    - The quadratic timing (5.8 s / 2.8 s before the fix) is still not independently reproducible.
    - **Stale numbers, as announced**:
      - COMPATIBILITY_REPORT.md and GO_NO_GO.md state "1985 / 1983+" and "140 passed / 1 xfailed" for the platform.
      - Actual numbers: SDK suite 2056 passed, 1 skipped on all three Pythons; the five platform files give 130 passed, 1 xfailed.
      - The "140" figure may come from a larger platform set, since I ran only the five specified files.
11. **CI** (`gh pr checks 10`; head confirmed as 58e4507):
    - Lint, format, and type-check: pass.
    - Test stable contracts py3.12: pass (3m25s).
    - Test stable contracts py3.13: pass (3m48s).
    - Node reference check: pass.
    - Release artifacts, extras, examples, and typing: pass.
    - **Test stable contracts py3.11: still pending** at my last check (run 39743135999 in progress for over 11 minutes, whereas the others took 3.5 min). The three earlier runs on this branch were successful.

## Status of the earlier findings

| ID | Status | Evidence |
|---|---|---|
| F-01 HIGH (lint, format red) | **Closed** | ruff check, ruff format --check and mypy are clean locally, and the CI lint job passes. |
| F-02 LOW (suite count) | Closed (superseded) | The actual count is now 2056 on all three Pythons; the docs are stale (F-R2). |
| F-03 LOW (failure-rate cap mutation survived) | **Closed** | M7 is now killed. |
| F-04 LOW (cross-split leakage mutation survived) | **Closed** | M9 is now killed. |
| F-05 INFO (10.6 MB figure) | **Closed** | PERFORMANCE.md now states about 8.8 MB. |
| F-06, F-07 INFO | Unchanged | Not reproducible without old code / pre-existing platform xfail. |

## New findings

| ID | Severity | Finding | Fix |
|---|---|---|---|
| F-R1 | MEDIUM (CI) | The py3.11 CI job had not finished after more than 11 minutes, against about 3.5 min for 3.12 and 3.13. It may be a stuck runner, but it must be green. | Re-run the job if it is hung; confirm green. |
| F-R2 | LOW | COMPATIBILITY_REPORT.md and GO_NO_GO.md carry stale numbers (1985 / 1983+, platform "140"). The author already plans to update them. | Replace with 2056 on 3.11/3.12/3.13 and the platform numbers (130 passed, 1 xfailed for the five files). |
| F-R3 | LOW | The shared judge validator `judge/_jsonschema.py` changed: a trailing newline now fails an anchored (`$`) pattern. It is documented as an ECMA-262 alignment and tested, but it is a change to existing behaviour of the validator for every user of the experimental judge. | Mention it explicitly in CHANGELOG, if it is not already there. |

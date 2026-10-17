# P28 / P29 governance milestone: targeted verification of the review remediation

Verifier: independent (did not write the remediation or the review). Date: 2026-10-17.
Read-only on both candidate trees; all builds, mutants and test runs were done on copies under
`<tmp>/`. The only file written into a candidate tree is this report.
Python bytecode caches that a test/tool run created under `agent-reliability-final/src` (9 `__pycache__`
directories, all dated 2026-10-17 11:18 or later) were deleted; both trees then matched `freeze4_*.txt`
exactly (309 and 634 files, 0 differing, 0 extra, 0 missing), before this report was added.

## 1. Verdict

**VERIFIED_WITH_NOTES.** Gate: `P28_P29_GOVERNANCE_AND_CI_READY_FOR_OWNER_APPROVAL` stands (the only status string
in the readiness report; no approval exists, hosted CI not run). 11 of the 13 actionable findings are FIXED; F-03 and
F-10 are PARTIALLY FIXED (one residual sentence each); F-11 is fixed for the cases the review named but two new
crash inputs remain (fail-closed). No BLOCKER or HIGH. New findings: 0 MEDIUM, 5 LOW.

## 2. Per-finding table

| ID | Status | Evidence |
|---|---|---|
| F-01 | FIXED | `stage_groups.py sdk` -> `final tree files: 309 / staged: 309 / differing: 0`; `stage_groups.py platform` (run from the platform tree, output in scratch) -> `634 / 634 / differing 0`. SDK groups hold 29+4+77+38 = 148 files and equal `git status --short -uall` (148 entries) exactly: none missing, none extra (script comparing the sets). Platform groups 5+43+5+3+89 = 145, disjoint, equal to the change set. Plan and report say 148/145 and 309/634: consistent. |
| F-02 | FIXED for the reviewed bypasses (residual limits below) | Attacked `scripts/p29_pilot_report_check.py` with about 60 mutations of a valid report. Rejected: whitespace-only text, zero/negative/float/bool/string counts (`True` as count rejected), `false` for must-be-true fields, `0001-01-01`/pre-2020 and `2026-02-30` dates, unicode digits, trailing newline date, `[" "]`, `[]`, dict/nested evidence, null rows, bool in row counts, `NaN` reliability, non-dict shapes at every level, wrong schema, lowercase status, `pilot_authorized: true` with any safeguard unsatisfied. Accepted (documented as "completeness and plausibility of form, not truth", `P29_PILOT_SAFEGUARDS.md:39`): evidence `["xxxxxx"]`, sign-off name/role `xx`, zero-width-space strings (`str.strip()` does not remove U+200B), a future date such as `9999-12-31`, an indicator row whose `determinate`/`reliability` contradict its pass/fail counts, all-zero rows, single-character `dashboards_inspected`, a contradictory SG-4 boolean pair, unknown extra keys at top level and in entries. None of these is the review's original class (whitespace, null, false, zero) but see N-01. The shipped template remains inert (all NOT_SATISFIED). |
| F-03 | PARTIALLY FIXED | Ambiguous cases are now correctly described as part of the headline slice (`calibration.py:322` `pick(("clear","ambiguous"))`), kappa is described as judge-versus-human, and labeler-versus-labeler kappa as computed outside the harness (`labels` parsed at lines 96/111 and unused in metrics). Still wrong/unchanged: section 10 row "Adversarial slice: no adversarial case flipped to PASS by injected content". The harness only has the slice-level human-label versus judge-decision matrix (`misjudged_case_ids`), it cannot tell that injected content caused a flip; the review asked for rewording to what the report counts. The readiness-report disposition does not mention this part. |
| F-04 | FIXED | DR-3 and `docs/security/evidence-ingest-machine-auth.md:41` now say: any successful (<400) authenticated POST/PUT/PATCH/DELETE outside `/api/v1/security/`, best-effort and possibly missing, denials not audited. Matches `api/security_audit.py:25-60` (condition list, `try/except` that logs and swallows, `hasattr(request.state, "authorization_context")`). |
| F-05 | FIXED (one cosmetic residual) | Copied `.github` and `tests/unit/test_workflow_policy.py` to scratch. Baseline 8 passed. Mutants on the copy of `release.yml`, each run: `... origin/main \|\| true; then` FAILED; `exit 1` replaced by `true` FAILED; `continue-on-error: true` on a job FAILED; on the guard step FAILED; `\|\| :` FAILED; ancestry against `HEAD` instead of `origin/main` FAILED; guard negation removed FAILED. Survivor: prefixing only the `if` line with `#` still passes the regex (but yields invalid shell, a loud CI failure, not a silent bypass). Timeouts: `ci.yml` quality 30 / test 30 / artifacts 30 / reference-vectors 10; `release.yml` build 30 / publish 15 / github-release 15 (test asserts every release job). `ruby -ryaml` parses both SDK workflows and the platform `ci.yml`. |
| F-06 | FIXED | Plan uses `final/p28-sdk-http-exporter`, `final/p29-experimental-judge`, `final/p28-p29-reports`, `final/p28-pc1-machine-auth`, `final/p28-pc2-ingestion-v2`, `final/p28-integration-regressions`, `final/p28-required-checks`, `final/p28-reports`. `git branch --list 'final/*'` is empty in the originals and the final repo; the plan states the `git fetch` side effect on the originals' refs (lines 134-138) and that `feat/p28-pc1-machine-auth` exists. |
| F-07 | FIXED | Release record says 272 / 77. A sdist/wheel built by me from a copy: 272 sdist entries, 77 wheel entries (26 judge). Only the three allowed `P29_PILOT_*` docs from `docs/P28|P29` are in the sdist; no `CLAUDE.md`/`AGENTS.md`. (Build used the network-less cached backend `hatchling 1.32.4`; I did not rerun the full `verify_release_artifacts.py`.) |
| F-08 | FIXED (one new dangling reference, N-02) | `freeze4_sdk_final.txt` (309 lines) and `freeze4_platform_final.txt` (634) exist and match both trees byte for byte (recomputed sha256). `verify_release_artifacts_output.txt` is stored and ends with every stage `ok` (the log has no explicit exit-code line). |
| F-09 | PARTIALLY FIXED | SDK count 24 is exact and all 24 are in group 4 (recomputed). Platform: the plan and report say "10 platform documents (all in group 5)". Actual: 8 files with developer-machine paths (`/Users/`, `/private/tmp`), all in group 5, plus 4 pre-existing docs with server paths (`/home/ubuntu/...`: `TEST_ENVIRONMENT.md`, `runbooks/database-restore.md`, `P18A/P18B_SHARED_TEST_CLOSURE.md`) = 12. "10" is neither 8 nor 12 (N-03). |
| F-10 | PARTIALLY FIXED | (a) DR-6 now lists 409 (line 306), matches `evidence_routes.py:125`. (b) DR-2 risk 2 now "that instance's ingestion budget per path" (line 93). (c) DR-4 now says the asserted headers are logged in the message text (lines 211-212), matches `logging.py:98-113`. (d) DR-5 line 273 still says "set explicitly (already the P14 rule)" while line 248 of the same record states `authentication_mode` defaults to `dev_header`; the "already the rule" claim holds for `deploy/test/compose.yml`, not for `Settings`. |
| F-11 | PARTIALLY FIXED | Named cases fixed: `fields: null`/string, `safeguards: []/null`, entry/top-level non-dicts all give a clean refusal; duplicate keys and `NaN`/`Infinity` give `report is not acceptable JSON` (rc 1). Still tracebacks (fail-closed, rc 1): `on_no_data` as a list or dict (`TypeError: unhashable type`, `value in _ON_NO_DATA`), and 100,000-deep nested JSON (`RecursionError`). Missing file also raises. See N-01. |
| F-12 | FIXED | New 20th test `test_p7_policy_needs_both_windows_to_breach` asserts `short_burn_rate == Decimal(5)` and `long_burn_rate == Decimal("0.5")` and decision ALLOW (lines 781-799). `test_postgres_judge_indicator_coverage_gate.py`: 20 passed on PostgreSQL 16 and 17. My mutants of `domain/policy.py` (on a scratch copy, PYTHONPATH pointed at it, PG16): AND changed to OR -> 1 failed (CAUGHT); short-only -> 1 failed (CAUGHT); long-only -> 20 passed (survives: the file has no long-breach-only case, not claimed by the report); `>=` changed to `>` -> 20 passed here (equality is covered by `tests/unit/domain/test_policy.py::test_threshold_equality_satisfies_predicate`, which fails: 2 unit failures observed when I accidentally left this mutant in the copy). |
| F-13 | FIXED | `find` for `.hypothesis .mypy_cache .ruff_cache __pycache__ dist build .pytest_cache node_modules *.egg-info` (excluding `.git`) was empty in both trees at the start; sha256 of every file equals `freeze4_*.txt`. |
| F-14..F-16 | INFO | F-14 limitation stated in section 17; F-15/F-16 unchanged. |

## 3. New findings

| ID | Sev | Finding and evidence | Repro | Fix |
|---|---|---|---|---|
| N-01 | LOW | Pilot checker residual crash and form gaps, all fail-closed except the last. (a) `"on_no_data": ["block"]` or `{"a":1}` -> `TypeError` traceback; (b) 100,000-deep `[` nesting -> `RecursionError` traceback (not caught by `except ValueError`); (c) missing report file -> `FileNotFoundError`; (d) `pilot_authorized` is only checked with `is True`, so `"yes"` or `1` with every safeguard NOT_SATISFIED gives `consistent: true`, `pilot_ready: false` (`pilot_ready` is still correct); (e) semantic form gaps listed under F-02. `P29_PILOT_SAFEGUARDS.md:38` ("refuses `pilot_authorized: true` unless all six are satisfied") is true only for the literal `true`. | `<tmp>/atk/atk.py` (python3 -B) | Use `isinstance(value, str) and value in ...`; catch `RecursionError` and `OSError` in `main`; reject any non-absent, non-`false` `pilot_authorized`; optionally reject zero-width characters and cross-check row counts. |
| N-02 | LOW | Dangling reference: readiness report section 17 ends "Its outcome is recorded in section 19", but the report ends at section 18. | `grep -n "section 19" docs/P28_P29_GOVERNANCE_AND_CI_READINESS_REPORT.md` | Point it to this document's verdict, or add the section when recording it. |
| N-03 | LOW | Platform local-path count wrong in plan line 40 and report disposition F-09 ("10 platform documents ... all in group 5"): 8 in group 5, 4 more pre-existing server-path docs. | Python scan in section 4 | Say 8 developer-path documents in group 5 (and 4 pre-existing docs with `/home/ubuntu` paths). |
| N-04 | LOW | F-03 residual: adversarial acceptance criterion still describes a measure the harness does not have (see table). | `grep -n -i adversarial docs/P28_P29_CALIBRATION_PREPARATION.md` | Reword to "no human-`fail` adversarial case with judge decision PASS (count from the adversarial slice matrix); causation is reviewed by people". |
| N-05 | LOW | F-10(d) residual: "already the P14 rule" contradicts the defaults sentence in the same record. | DR-5 lines 248 and 273 | Say "already the rule of the shared TEST compose file". |

Observation (not a defect of this milestone): the platform `ci.yml` has `timeout-minutes` only on `postgres-slow` (60); no claim of platform job timeouts is made.

## 4. Regression results (all on byte-identical scratch copies of the end-state trees; the editable-install source was overridden with `PYTHONPATH`, caches disabled)

| Check | Result |
|---|---|
| SDK Python 3.11.17: `ruff check .` / `ruff format --check .` / `mypy src` | pass / 268 files formatted / no issues in 65 files |
| SDK 3.11 `pytest` | **1,646 passed, 1 skipped** |
| SDK 3.12 `pytest` | **1,646 passed, 1 skipped** |
| SDK 3.13.16: ruff, format, mypy | pass / 268 formatted / no issues; `pytest` **1,646 passed, 1 skipped** |
| `node scripts/verify_p28_reference.mjs` | 76 canonical byte/digest vectors; 74 acknowledgement vectors passed |
| Checker and workflow-policy tests (candidate tree, 3.11) | 48 passed (40 checker, 8 workflow policy) |
| Platform `ruff check .` / `ruff format --check .` / `mypy src` | pass / 553 formatted / no issues in 138 files |
| Platform `pytest -m "not integration"` | **1,168 passed** (533 deselected) |
| Platform `integration and not slow`, PostgreSQL 17 | **529 passed, 1 xfailed** (2 min 49 s) |
| Judge-indicator file, PostgreSQL 16 and 17 | 20 passed each |
| Stage rehearsal | SDK 309/309 and platform 634/634, 0 differing |
| Built artifacts | sdist 272, wheel 77 (26 judge) |

## 5. Restrictions

`git -C agent-reliability-final log -1` is still `7aa6883 chore(release): prepare 1.2.1`; no `final/*` branches exist; originals: `agent-reliability` 43 and `agent-reliability-platform` 53 status lines (unchanged). The status string `P28_P29_GOVERNANCE_AND_CI_READY_FOR_OWNER_APPROVAL` appears once in the readiness report and nowhere upgraded. Every `Approver: ____ Date: ____` field in the owner packet is blank; no approval, signature or named person was found.

## 6. What I could not verify

Hosted GitHub Actions behaviour and the existence of pinned action SHAs (no network); the full `verify_release_artifacts.py` (it installs from the network; I only compared artifact counts and contents of a fresh local build, and read the author's stored log, which has no explicit exit status); PostgreSQL 16 for the full integration tier (PG17 only; PG16 only for the judge file and mutants); platform on Python other than the one venv provided; the primary P29-D09/D10 documents (still absent, disclosed by the author). I did not determine which test run created the `__pycache__` directories in the candidate `src/` (the venv resolves the package through the candidate path in some subprocess or tool; they were removed).

# Calibration readiness review 2 (independent re-check of review 1 corrections)

Scope: `git diff 9859331 HEAD` (commit 4a503f6) against `CALIBRATION_READINESS_REVIEW_1.md`.
Run: `pytest tests/unit/experimental_calibration` gives 292 passed (was 284). `verify` on the private directory with `--repo .`: all_ok true, 300 items, 23 checks, none failed. Without `--repo`: all_ok false (only the new "leak scan was performed" check fails). I did not open any private file and ran no model. I also compared the reformatted generator with the previous version using dummy secret and dummy phrase pools: byte-identical output (300 items), so the formatting-only rewrite did not change the RNG sequence. `src/` and the thresholds file are unchanged since 9859331 (digest unchanged, jp1/jp2/jp3 untouched).

## Verdict

**GO for handing packages to labellers, from the tooling point of view.** All six review-1 findings with a requirement impact are closed. No BLOCKER and no HIGH remain. 0 BLOCKER, 0 HIGH, 0 MEDIUM, 6 LOW (all new or residual, none blocking).

## Closure of review 1

| Finding | Status | Evidence |
|---|---|---|
| H1 labeller declaration leaks adjudicator and judge wording | Closed for the leaked content | `_labeller_declaration()` drops everything between "Adjudicator only:" and "I confirm that my answers"; common rows 5 and 6 and the header no longer name the adjudicator. New test builds real folders with the real template and asserts no "Adjudicator only", "adjudicat", "Qwen", "agreement figures", "judge being calibrated"; plus a direct test of the stripper on the real file. Residual: L1, L2. |
| M1 agreement/kappa pooled n/a as UNKNOWN | Closed | Per dimension, items where both labellers used the n/a reason are removed from `ids` before agreement, kappa, Wilson, analytic and bootstrap CIs; `excluded_both_not_applicable` and `not_applicable_counts` (over all items) are reported. The disagreement loop uses the filtered ids; applicability loop uses all ids. Tests: 12 shared n/a items leave n=48 and agree=48; A n/a versus B PASS is a label disagreement and not double-listed; all-n/a gives n=0. An all-n/a dimension makes kappa undefined, so `merge` refuses (fail-safe, not a crash: kappa None is checked before the `percent_agreement` comparison). One-sided n/a with the same label stays in the statistics and goes to adjudication, which is reasonable. Residual: L5 (docs). |
| M2 verify vacuous without `--repo`, no history | Closed with caveats | New check fails the run when `--repo` is absent (tested). `git log -p --all` is scanned for seed, salt and private answers (tested with a secret committed then removed). Caveats: L3. |
| M3 narrow disjointness claim | Closed | Generator harvests `question`/`answer` strings from every JSON under `docs/p29-calibration` recursively (dicts and lists); owner guide wording now states exact-string match against golden set and committed JSON only, not semantic. |
| M4 export can write private items into a repository | Closed | With `--items-file` (items given), output and key directories are refused inside any git work tree (probes nearest existing parent); `--dimensions` must be a subset; tested for out-dir, key and bogus dimension. Checklist now says merge output stays in the private folder. Caveat: L4. |
| M5 vacuous or weak checks | Closed | Hard-coded True check and the tool-level salt check removed. Replaced by "key records a secret salt and salt file is at least 32 chars" (real salt dependence is established by the byte-for-byte re-export with `salt.txt`). Permissions now checked over every file under the private directory (tested). `packages` chmods its output 0700/0600 (tested). Not addressed and not claimed: nothing ties `seed.txt` to `manifest["seed"]` or the bank (L6). |
| L1 test gaps | Closed | New tests for shared n/a, n/a-versus-determinate label, all-n/a. Still untested: n/a in a two-dimension round, kappa floor with partly excluded items, the 30-per-class true case. |
| L3 MIN_PER_CLASS | Closed | `merge` reads `adjudicated_set.min_cases_per_class_for_any_calibration_claim` from the supplied thresholds; the default 30 is a fallback only. |
| L2 CHANGELOG | Closed | Note added that groundedness not-applicable items no longer merge as UNKNOWN. |

## New and residual findings (all LOW)

- **L1 Declaration row 1 still names "the judge prompts"** (and row 3 "any model verdict"), shipped to labellers. It tells them a judge exists, though not which model. Consider "the evaluation code, prompts or documentation". Test `forbidden` list does not contain "judge", and it contains a leftover nonsensical expression (`"model verdict" if False else "Qwen3"`).
- **L2 `_labeller_declaration` fails open.** If the "Adjudicator only:" marker is edited in the template, the whole template (including rows 7 and 8) is shipped. The real-template test would catch a change in CI, but `packages` itself does not assert the result is free of "Qwen"/"adjudicat". A runtime assertion would be cheap.
- **L3 History scan limits.** It covers answers longer than 25 characters (not questions or short answers), uses `git log -p --all` (merge-commit diffs are not shown, stashes and unreachable objects are not covered), and `check=True` means a non-git `--repo` raises a traceback instead of a failed check. The seed/salt scan is a plain substring search, fine for the 40+ character secrets used.
- **L4 Git-work-tree guard fails open** if `git` is missing or errors (nonzero return is read as "not in a work tree"), and applies only when `--items-file` is used. Duplicated dimensions (e.g. `relevance,relevance`) pass validation.
- **L5 Documents lag the tool.** ADJUDICATION_PROTOCOL.md and ADJUDICATOR_INSTRUCTIONS.md do not say that agreement statistics exclude items both labellers marked not applicable (only the CHANGELOG does); STATUS.md still says verify checks "not leaked" without "in the checked repository and its history". ADJUDICATOR_INSTRUCTIONS step 6 still says "30 adjudicated cases" where the tool counts all final applicable labels.
- **L6 `seed.txt` is still not linked to the package** by any check (re-export uses the seed recorded in the manifest). Low risk; mention in the owner checklist or add a hash comparison if the recorded seed is meant to equal `seed.txt`.

## Requirement re-check

| Requirement | Result |
|---|---|
| No invented labels or statistics | Met |
| Private material outside the repository, incl. history | Met by verify (tree and `--all` history for seed, salt, long answers); `--repo` now mandatory |
| Blinded, reproducible | Met (re-export byte for byte) |
| Minimum-access labeller packages | Met (declaration stripped; residual L1) |
| `dimension_not_applicable` labelling-only, separate, excluded from class denominators and agreement statistics, never UNKNOWN | Met |
| Thresholds and digest, jp1/jp2/jp3, no held-out run | Unchanged / not run |
| Generator and export cannot write inside a repo | Generator, `packages`, and `export` with `--items-file` refuse (L4 caveat) |

## Counts

BLOCKER 0, HIGH 0, MEDIUM 0, LOW 6 (new or residual). Review 1 findings closed: 1 HIGH, 5 MEDIUM, and the LOW items on tests, thresholds constant and CHANGELOG.

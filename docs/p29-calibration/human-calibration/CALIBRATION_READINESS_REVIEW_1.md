# Calibration readiness review 1 (independent)

Scope: `git diff 39fcd0e HEAD` on `feat/p29-relevance-calibration-readiness` (10d5c62, 9859331), plus the generator `scripts/p29_relevance_calibration_items.py` (unchanged since 5e67b91).
Method: code and document reading, `pytest tests/unit/experimental_calibration` (284 passed), `p29_relevance_round.py verify` on the private directory (counts and booleans only; no private file opened, no model run), history grep of `origin/main..HEAD` by file name and by private-file references.
Not verified by me: private content itself (not permitted), so history was not searched for the actual seed, salt or answers (see M2).

## Verdict

**CONDITIONAL GO for preparation; NOT ready to hand packages to labellers until H1 is fixed.** No BLOCKER. 1 HIGH, 5 MEDIUM, 5 LOW.
Verified clean: thresholds file and digest `31fb3e7a...c561263` untouched; no change under `src/` (jp1/jp2/jp3 untouched); no label, agreement, kappa or accuracy is computed or recorded anywhere in the diff; `verify` on the real package reports 21/21 checks ok, 300 items, mode 700; no private file name, seed or salt reference was found in branch history by name (only code and docs that name the files).

## Findings

### H1 (HIGH) The shipped DECLARATION.md gives labellers adjudicator-only and judge information
`packages()` copies `DECLARATION_TEMPLATE.md` byte for byte into each labeller folder. That file contains rows 7 and 8 ("Adjudicator only"), which name "Qwen3-14B", "agreement figures", the "adjudication template" and "the judge being calibrated". A labeller therefore learns the model under test, that agreement figures exist and that a third person sees only the disputed items. This contradicts the minimum-access requirement and the labeller instruction that the labeller should have no exposure to model information.
Why tests miss it: `test_packages_are_minimum_access...` writes a stub `LABELLER_INSTRUCTIONS` ("instructions") in the temp package and its forbidden-word list has no "Qwen", "judge" or "adjudicat" terms; the real documents are never scanned.
Reproduce: `grep -n "Qwen\|Adjudicator only" docs/p29-calibration/human-calibration/DECLARATION_TEMPLATE.md`, then read `packages()` (`DECLARATION` copied unchanged).
Fix: separate labeller and adjudicator declaration templates (or render only rows 1-6 for labellers) and add a test that scans the real generated folders for "Qwen", "judge", "jp3", "agreement", "adjudicat" (the labeller instructions legitimately mention the adjudicator existing; decide which wording is allowed and pin it).
Related: row 1 of the template mentions "the judge prompts", which also reveals that a judge exists.

### M1 (MEDIUM) Pooled agreement and kappa treat `dimension_not_applicable` as UNKNOWN
`agreement_report` computes percent agreement, kappa and the bootstrap interval on the raw `*_label` column, in which a not-applicable item is just `UNKNOWN`. Items both labellers mark not applicable count as agreed UNKNOWN and inflate agreement and kappa, which gate `merge`; the report does not give an applicable-only figure. This is the "silently map to UNKNOWN" the owner ruled out, though only in the inter-labeller statistics. The thresholds file says the code is "not pooled with context_insufficient or question_missing". Docs (ADJUDICATION_PROTOCOL) say it is excluded from class-level denominators only, so they do not overclaim, but the owner should decide and the report should show both figures.
Reproduce: a round where many items are `(UNKNOWN, dimension_not_applicable)` for both labellers; kappa rises with their number. Existing test only asserts the counts.

### M2 (MEDIUM) `verify` cannot show "not leaked"; leak checks are skipped silently without `--repo` and ignore history
- `--repo` is optional. Without it the "outside the repository", "seed and salt do not appear" and "no private answer appears" checks are not run, yet `all_ok` is true.
- `_tracked_text` reads the working tree files in `git ls-files` only: not git history, other branches, stashes or deleted files. A secret committed and later removed passes. `git ls-files` output with non-ASCII names (quoted paths) is silently skipped.
- Only answers longer than 25 characters are searched; questions and contexts never.
- STATUS.md says verify checks "not leaked"; that overstates it.
Fix: require `--repo` (fail if absent), scan `git log --all -p` (or `git grep` over all revs) for seed, salt, answers and questions, scan the owner's other local repositories if relevant, and word the docs as "not present in the checked tree and history".

### M3 (MEDIUM) The "disjoint from every committed dataset" check is narrower than the claim
`seen_strings()` loads golden cases and `qwen-*/*.json` files that are dicts with `cases`/`examples` and exact-match `question`/`answer` only. List-form files (e.g. `qwen-relevance/diagnostic_3case.json`), `.md` text, test fixtures and judge dev sets elsewhere are not covered, and near-duplicates pass. RELEVANCE_ROUND1_OWNER_GUIDE.md says none overlaps "any prompt-development, smoke-test or golden-set item" which this does not establish. Either widen the scan (all tracked JSON/MD/Python strings) or word the claim as "exact-string match against golden and `qwen-*` datasets".

### M4 (MEDIUM) `export` has no guard against writing private items or the key into a repository
`scripts/p29_human_calibration.py export --items-file PRIVATE --out-dir X --key-out Y` writes the sheet, `export_manifest.json` (which records the seed) and the key wherever told, including inside the repo. The generator and `packages` refuse; `export` does not (only "key not beside the sheet"). The owner checklist also does not say that the `merge --out-dir` output, which contains the private item text, must stay private. Add the same repo-root refusal for `--items-file` runs (or always) and a checklist line.

### M5 (MEDIUM) Several `verify` checks are vacuous or weak
- `"the key sha is the only private-package hash recorded as such"` is `check(..., True)`: it always passes and checks nothing. Remove or implement.
- `"blinding depends on the secret salt"` re-runs the tool with salt `"x"` and compares one row (it tests the tool, not the package; the real evidence is the byte-for-byte re-export with `salt.txt`). Acceptable but mis-described.
- `"no provenance or stratification column in the header"` is subsumed by the exact column-tuple check and never inspects cell content.
- Nothing ties `seed.txt` to the bank or to `manifest["seed"]` (the re-export uses `manifest["seed"]`, not `seed.txt`), so a seed file that is unrelated to the real generator secret would pass.
- Permission checks cover only the directory and two secret files, not the key, bank or manifest.

### L1 (LOW) Test gaps for the applicability logic
Covered: both n/a, one-sided n/a with same label, label split, adjudicated-to-n/a exclusion, agreed UNKNOWN. Not covered: A n/a versus B PASS or FAIL (label disagreement, adjudicated to a non-n/a class, must then count in that class); n/a in a two-dimension round (this also changes behaviour for groundedness, see L2); all items n/a (empty split, `weakest` fallback `human_multi`, dataset loader on an empty split); kappa with n/a; `merge_report` minimum check at or above 30; a regression test pinning old two-dimension numbers. I traced these by reading and found the logic correct: a label-differing pair is never listed twice, an item with reason n/a after adjudication or agreement is excluded and never counted as UNKNOWN or as a class member, and unadjudicated items take A's reason only when both labels agree.

### L2 (LOW) Behaviour change for existing two-dimension rounds
The only intended changes are additive report keys (`not_applicable_counts`, `applicability_disagreements`) and merge exclusion. kappa/percent/Wilson code is unchanged and all earlier tests pass. But a groundedness item labelled `dimension_not_applicable` used to merge as UNKNOWN; it is now dropped from the groundedness dataset. That is the intended semantics; note it in the CHANGELOG (only the relevance round is mentioned).

### L3 (LOW) `MIN_PER_CLASS = 30` is hard-coded, not read from the thresholds file
It matches `adjudicated_set.min_cases_per_class_for_any_calibration_claim` today, and the thresholds file is digest-pinned, but no test ties the constant to the file. Also `merge_report.json` is written next to, but is not hashed by, the dataset manifest. The checklist says "adjudicated applicable cases"; the count is all final applicable labels (agreed and adjudicated). Clarify the wording.

### L4 (LOW) Smaller tooling points
- `--dimensions` is not validated (unknown name gives a KeyError traceback instead of `refused:`).
- `packages` does not itself run `verify`, so it will happily package a pre-filled or tampered sheet; set 0700/0600 on the distribution folders; the distribution record lives in the same folder as the two labeller folders (checklist does say to hand over only each folder).
- The adjudication CSV row count lets the adjudicator infer the number of agreed items, though the instructions say they will not know it.
- `verify` prints the unexpected filenames of the labeller package and the sheet header on failure; names only, acceptable.

### L5 (LOW) Document consistency
- LABELLER_INSTRUCTIONS_RELEVANCE.md says an incomplete sheet "is rejected", while README_FIRST tells labellers to return partial sheets with blank rows; both lead to rejection by `validate`, but the coordinator guidance (accept partial, arrange time) should be stated once.
- Guidance for `dimension_not_applicable` is thin ("answer asserts nothing ..."); the two labellers may use it very differently, which only produces adjudication work (and, per M1, statistical noise). Add one or two non-item-specific examples.
- KNOWN_JUDGE_CONCERNS_FOR_CALIBRATION.md figures (31 of 50, 46 of 50) match RUBRICS_SMOKE_2026-11-09.md; jp3 digest prefix matches. It correctly states the concerns are development observations and that no tuning against the protected set is allowed. Item 5 says whitespace-only input is "existing jp1/jp2 behaviour", which I did not re-verify.

## Requirement check

| Requirement | Result |
|---|---|
| No invented labels, identities, agreement, kappa, accuracy | Met (nothing computed or recorded; docs state none exist) |
| Private bank, salt, seed, keys outside repo, incl. history | Met by file-name evidence and `verify`; content-level history search not done (M2) |
| Blinded, reproducible package | Met (byte-for-byte re-export with the secret salt; ids opaque; no stratification tag in sheets) |
| Minimum-access packages for two labellers | **Not met until H1 is fixed**; otherwise folders hold only own sheet, instructions, declaration, README; roles differ; row order differs |
| Adjudicator instructions and disagreement process | Present and consistent with the tooling |
| COI and prior-exposure declarations | Present; see H1 |
| Owner checklist | Present; add M4 note |
| `dimension_not_applicable`: labelling only, reported separately, excluded from class denominators, never SDK verdict | Met in merge and reports; pooled in agreement statistics (M1) |
| Thresholds and digest unchanged; jp1/jp2/jp3 untouched; no held-out run | Met |
| Judge concerns documented, not tuned on protected set | Met |
| Generator/verify cannot write inside the repo | Generator and `packages` refuse; `verify` is read-only; `export` does not refuse (M4) |

## Counts

BLOCKER 0, HIGH 1, MEDIUM 5, LOW 5.

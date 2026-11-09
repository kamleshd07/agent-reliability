# Relevance round 1: owner checklist

**Nothing below has been done by a human yet. No labels, no agreement figures, no held-out judge run exist.**
The private package, the item bank, the secret salt and seed and the answer key are on the owner's machine and must never enter a repository.

## A. Before anyone is approached
- [ ] Run the package verification on the private folder and confirm every check passes:
  `python scripts/p29_relevance_round.py verify --private-dir <PRIVATE_DIR> --repo <SDK_REPO>` (the report holds counts and booleans only).
- [ ] Decide the people: **Labeller A**, **Labeller B** (independent of each other) and a separate **Adjudicator**. Not yet assigned.
- [ ] Decide who the **coordinator** is (holds the key; does not label, adjudicate or advise on labels).
- [ ] Decide the time box (proposal: up to about 3 hours per labeller for 300 items, in sessions of at most 60 minutes) or cut the item count.
- [ ] Confirm `dimension_not_applicable` is used for labelling only (approved), reported separately and excluded from class counts.

## B. Build the distribution (private)
- [ ] `python scripts/p29_relevance_round.py packages --private-dir <PRIVATE_DIR> --out-dir <PRIVATE_DIR>/distribution`
  creates `labeller_A/` and `labeller_B/` (sheet in a different order for each, role id prefilled, instructions, declaration form, README) and a private hash record.
- [ ] Give each labeller **only their own folder** over a private channel. Never send the key, manifest, salt, seed, bank, the other folder or this checklist.

## C. Collect
- [ ] Collect each completed declaration **before** labelling starts; record any "yes" and decide whether that person may take part.
- [ ] Collect each completed CSV. If a labeller ran out of time, accept the partial file and arrange more time; do not ask them to guess.
- [ ] Validate each CSV against the common blank sheet:
  `python scripts/p29_human_calibration.py validate --blank <PRIVATE_DIR>/labeller_package/blank_sheet.json --sheet <FILLED>.csv`
  Fix only format problems (never labels) by returning the file to its labeller.

## D. Compare and adjudicate
- [ ] `agreement --blank ... --sheet-a A.csv --sheet-b B.csv --adjudication-template ADJ.csv` (run once).
- [ ] Check the floors in `PREDECLARED_THRESHOLDS.json` (digest `31fb3e7a87ae4e287ff68854ba7fe145be76fa7d883cbdec0377057d5c561263`). If kappa or agreement is below a floor, stop and follow the protocol; do not lower anything.
- [ ] Send only `ADJ.csv` and [ADJUDICATOR_INSTRUCTIONS.md](ADJUDICATOR_INSTRUCTIONS.md) to the adjudicator; collect the completed file.
- [ ] `merge ... --key <PRIVATE_DIR>/KEY_PRIVATE.json --confirmed-thresholds-sha256 31fb3e7a...c561263`; read `merge_report.json` (class counts, not-applicable count, minimum-per-class).

## E. Gate before any judge assessment
- [ ] All three people have declared; every disagreement is adjudicated; the merge succeeded.
- [ ] Each of PASS, FAIL and UNKNOWN has at least 30 adjudicated applicable cases (otherwise the result is indicative only).
- [ ] The held-out assessment of Qwen3-14B (jp3, frozen configuration) is then run **once**, at least 3 repeats, and reported against the predeclared thresholds including a negative result. Not before.
- [ ] Do not tune jp3 or any prompt against this set. Any change is a new template version and needs a new, fresh round. See [KNOWN_JUDGE_CONCERNS_FOR_CALIBRATION.md](KNOWN_JUDGE_CONCERNS_FOR_CALIBRATION.md).

## What you must not do
Do not let an LLM label or adjudicate anything, do not simulate people, do not edit the labels, and do not claim agreement, accuracy or false-positive rates until real adjudicated labels exist.

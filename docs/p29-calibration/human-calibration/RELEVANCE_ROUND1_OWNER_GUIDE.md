# Relevance round 1: what is prepared and what the owner must supply

**No human has labelled anything. No label or agreement figure exists, none was simulated, and no model has seen these items.**
Qwen3-14B with jp3 (relevance rubric 2026-11.r1) is eligible for this round by owner decision; it is not calibrated.

## Prepared (private, outside this repository)

A private directory on the owner's machine, outside every repository (mode 700; its location is told to the owner in the report, not recorded here). Nothing
in it is committed or pushed.

| File | Who may see it |
|---|---|
| `labeller_package/blank_sheet.csv`, `blank_sheet.json`, `LABELLER_INSTRUCTIONS_RELEVANCE.md` | each labeller (the sheet and instructions only) |
| `KEY_PRIVATE.json`, `export_manifest_PRIVATE.json`, `salt.txt`, `seed.txt` | owner / merging coordinator only |
| `item_bank_private.json` | owner only: carries the generator's stratification tag, which is **not** a label |

- 300 synthetic items with opaque ids (L001..L300), shuffled with a secret salt; none repeats an exact question or answer string found in the golden set or in any committed JSON dataset under `docs/p29-calibration/` (checked by exact string only; product names are drawn from a secret seed; this is not a semantic-similarity check).
- The bank is stratified to give both PASS-leaning and FAIL-leaning items (responsive, different-question, unrelated, evasive,
  injection-bearing) plus UNKNOWN-leaning items (no usable question) and borderline items (admits the information is unavailable, partial,
  compound). Final classes come only from human labels and adjudication; the 30-per-class minimum (PASS, FAIL, UNKNOWN) is checked after adjudication, and
  if a class falls short the result is indicative only and more items are needed (the generator can add them under the same secret).
- Sheet hashes (public, reveal nothing): csv `39a98bc86b3a830df981f8df1a59d695e30d6bd15c3df09a628eab8a0dc1e643`, json `a2f379a1108631857bff0b31a53a760e0b04376feda7ee7284d73f00bf92d216`, key `5fb78dbde0f51cc4506b9a3b872ff8fe081345073684eef218cdf9839dd568f7`.
- Thresholds: unchanged, digest `31fb3e7a87ae4e287ff68854ba7fe145be76fa7d883cbdec0377057d5c561263` (approved for internal validation only).
- Held-out judge assessment: **not run and not to be run** until adjudication is complete. The judge has never seen these items.

## Needed from the owner to start

1. **Two independent human labellers** (role ids, e.g. `labeller.r1.a`, `labeller.r1.b`): no discussion, no AI assistance, no exposure to model output or this repository.
2. **One separate human adjudicator** (not a labeller; blind to model verdicts).
3. Each person's conflict-of-interest and exposure declaration (see the instructions) recorded and a go/no-go decision on any "yes".
4. A time budget (proposal: up to about 3 hours per labeller for 300 items in sessions of at most 60 minutes, so the owner may reduce the count or accept several sessions).
5. Confirmation that the secret salt and key stay with the owner, and a private channel to hand each labeller only the sheet and instructions.
6. `dimension_not_applicable` is approved for labelling only (decided 2026-11-09); see the checklist and the adjudication protocol.

## Then

```
python scripts/p29_human_calibration.py validate  --blank labeller_package/blank_sheet.json --sheet FILLED_A.csv
python scripts/p29_human_calibration.py agreement --blank ... --sheet-a A --sheet-b B --adjudication-template ADJ.csv
python scripts/p29_human_calibration.py merge ... --confirmed-thresholds-sha256 31fb3e7a...c561263
```

Tooling change in this branch: the export accepts `--items-file` and `--dimensions relevance`; validation and agreement derive
dimensions from the sheet header (tested). The public generator `scripts/p29_relevance_calibration_items.py` needs a secret seed file and a private phrase-pool file (no item text lives in the repository) and
refuses to write inside the repository, so the public branch cannot regenerate or read the items.

See also `RELEVANCE_ROUND1_OWNER_CHECKLIST.md` (distribution, collection, validation), `ADJUDICATOR_INSTRUCTIONS.md`, `DECLARATION_TEMPLATE.md` and `KNOWN_JUDGE_CONCERNS_FOR_CALIBRATION.md`.

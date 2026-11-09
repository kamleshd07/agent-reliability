# Adjudicator instructions: relevance round 1

**Preparation document. No labelling or adjudication has occurred; no adjudicator is assigned.** Read together with
[ADJUDICATION_PROTOCOL.md](ADJUDICATION_PROTOCOL.md). You are the third, independent person. You are not Labeller A or B.

## Before you start
1. Complete and return [DECLARATION_TEMPLATE.md](DECLARATION_TEMPLATE.md) (including the adjudicator questions) to the coordinator. A false "no" invalidates the run.
2. Read `LABELLER_INSTRUCTIONS_RELEVANCE.md`: the definitions of PASS, FAIL and UNKNOWN and the reason codes are the same ones you apply.
3. You will receive only an **adjudication CSV**: one row per item the labellers could not settle. For each row you see the question, the context and the answer, and what "A" and "B" chose (label and reason code). You will not see their names, notes, how many items they agreed on, any model output, or where the items came from.

## Which rows you will see
- **Label disagreements:** A and B chose different labels.
- **Applicability disagreements:** A and B chose the same label but exactly one of them used the reason `dimension_not_applicable`.
Items on which both labellers agreed (including both choosing `dimension_not_applicable`) are not sent to you; their agreed result stands.

## What to do on each row
1. Judge the item afresh under the relevance definition. You are **not** bound to A's or B's choice, and you may choose UNKNOWN.
2. Fill `adjudicated_label` (PASS, FAIL or UNKNOWN) and `adjudicated_reason` (a code that belongs to that label).
3. Fill `rationale`: at least one full sentence saying which criterion decided it. It is required.
4. Use `dimension_not_applicable` (label UNKNOWN) only if relevance genuinely cannot be applied (for example the answer asserts nothing and there is no usable question for a reason other than a missing question). It is reported separately; it is **not** UNKNOWN in the statistics, it is never an SDK verdict, and it is left out of every class count. Do not use it to avoid a hard decision.
5. Put your assigned role identifier in `adjudicator_id` on every row. A genuinely undecidable item is labelled UNKNOWN with a rationale; never force a label.

## Independence rules
No discussion with either labeller or anyone else about any item; no AI tool, search engine or translator on the items; do not ask for or open any model output, earlier label or the repository. Ask the coordinator only how to use the file, never what a label should be.

## Disagreement-resolution process (for the coordinator)
1. Both sheets pass `validate`; neither is edited afterwards.
2. Run `agreement` once. It writes the agreement report and the adjudication template (label and applicability disagreements).
3. Send the template, and nothing else, to the adjudicator. Do not send the agreement report.
4. Collect the completed CSV. `merge` refuses unless every row is adjudicated, no agreed item is, and the adjudicator differs from both labellers.
5. If agreement is below the predeclared floor, `merge` refuses; follow "If kappa is below the predeclared floor" in the protocol. Never lower a floor or drop items.
6. The merge writes, per dimension, the dataset (not-applicable items excluded) and `merge_report.json` with class counts, the not-applicable count and item ids, and whether every class reaches 30 adjudicated cases. Below 30 per class the result is indicative only.

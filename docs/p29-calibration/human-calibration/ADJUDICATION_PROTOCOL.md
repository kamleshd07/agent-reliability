# Adjudication protocol

**Preparation document. No labelling or adjudication has occurred. No human evaluation has been performed.**

## Roles

* **Labeller A and Labeller B**: independent, per [LABELLER_INSTRUCTIONS.md](LABELLER_INSTRUCTIONS.md).
* **Adjudicator**: a third person (or the owner). Not Labeller A or B, and ideally not anyone who built the assistant or the evaluation.
  Declares conflicts and exposure exactly as the labellers do.
* **Coordinator**: runs the tooling and holds the private key. Does not label, does not adjudicate, does not advise on labels.

## What the adjudicator sees and does not see

Sees: the item (question, context, answer) and, for each disagreement only, both labellers' labels and reason codes, shown as "A" and "B"
(not the labellers' identifiers, and not their notes unless the owner decides notes are included in the protocol before adjudication starts).
Does not see: any model output or verdict, any earlier or assistant-authored label, the private key, the source of any item, or the
agreement statistics for individual labellers.

The adjudicator is not bound to pick A's or B's label. They label the item afresh under the same rubric definitions and may choose UNKNOWN.

## Procedure

1. Both sheets pass `validate`. Neither is edited afterwards.
2. `agreement` runs once, producing the agreement report and an adjudication template that lists one row per **(item, dimension)
   disagreement**. Items on which the labellers agree, including both-UNKNOWN, are not adjudicated; their agreed label stands.
3. The adjudicator fills `adjudicated_label` (PASS/FAIL/UNKNOWN), `adjudicated_reason` (rubric vocabulary), `rationale` (required, at least a
   full sentence stating which criterion decided it) and `adjudicator_id` (a role identifier) on every row. A genuinely undecidable item is
   labelled UNKNOWN with a rationale; it is never forced.
4. The adjudicator works under the same independence rules: no model assistance, no discussion with the labellers.
5. `merge` refuses unless every disagreement has an adjudication, no agreed item has one, and the adjudicator differs from both labellers.

## `dimension_not_applicable` (labelling tooling only)

Owner-approved for labelling only. It is a reason attached to label UNKNOWN, never an SDK verdict and never silently mapped to UNKNOWN.
The tooling reports it separately: `agreement` counts it per labeller and lists as **applicability disagreements** the items where the labellers chose the
same label but exactly one used it (these are adjudicated like any disagreement). `merge` leaves items whose final reason is `dimension_not_applicable`
out of the dataset and out of every class count, and records their count and ids in `merge_report.json` beside the class counts, which are the
denominators for the 30-per-class minimum. Items both labellers judged not applicable are also left out of percent agreement, Cohen's kappa and their intervals (reported as `excluded_both_not_applicable`), so they cannot inflate agreement.

## Reporting disagreement and ambiguity (always, whatever the result)

Report, per dimension: number of items; percent agreement with Wilson 95% interval; Cohen's kappa with an analytic (large-sample) 95%
interval and a bootstrap percentile 95% interval (2,000 resamples, fixed seed recorded in the tool); each labeller's label counts; number
of disagreements, of which how many involve one labeller choosing UNKNOWN; number adjudicated PASS / FAIL / UNKNOWN; count of
`dimension_not_applicable` reasons; share of LOW-confidence labels. Report item ids only, never content, in the public summary.
Ambiguity is a result, not a defect: a high adjudicated-UNKNOWN or LOW-confidence share is evidence about the rubric and must be shown.

## Agreement statistics

* Percent agreement `po` = items with identical labels / items.
* Cohen's kappa = (po - pe) / (1 - pe), where pe sums, over labels, the product of the two labellers' marginal proportions. If pe = 1
  (both labellers used a single identical label for everything) kappa is undefined and is reported as undefined, never as 1.
* Analytic interval: kappa +/- 1.96 * sqrt(po (1 - po) / (n (1 - pe)^2)). It is approximate and is shown beside the bootstrap interval.
* Bootstrap: resample items with replacement, 2,000 times, seed 20261108; percentile 2.5% and 97.5%; resamples where kappa is undefined are counted.
* With about 53 items the intervals are wide; read them.

## If kappa is below the predeclared floor

The floors are in [PREDECLARED_THRESHOLDS.json](PREDECLARED_THRESHOLDS.json). If a dimension's kappa, percent agreement or kappa lower bound is
below its floor:

1. `merge` refuses to produce a dataset. There is no override flag.
2. Do not lower the floor, drop disagreeing items, or pick a different statistic. Doing so after seeing the result invalidates the run.
3. Diagnose from the disagreement list (ids and reason codes): which criterion is unclear? Revise the rubric text or the labeller guidance,
   record the revision as a new rubric version and a new thresholds version if the owner so decides, and relabel with a **new blind
   ordering** (new seed or secret salt) by labellers who have not seen the old items' disagreements, or whose earlier exposure is declared.
4. The failed round is kept and reported as a failed round.
5. No model is run against a dataset that failed this step. A low-agreement dimension makes no claim about the judge.

## Records to keep (content-free)

Declarations of independence and conflicts; session dates and durations; sheet digests; the agreement report; the adjudication CSV;
the merge output manifests; the thresholds digest the owner confirmed. Retain content only where the data owner decides.

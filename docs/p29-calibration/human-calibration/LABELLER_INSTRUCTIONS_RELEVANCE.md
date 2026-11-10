# Labeller instructions: relevance round (P29 semantic evaluation)

**Preparation document. No human has used it yet. No human evaluation has been performed.** Relevance-only variant of `LABELLER_INSTRUCTIONS.md` (same independence, time-box and declaration rules).

You are asked to judge short answers from a shopping assistant for a fictional "TEST STORE". All text is synthetic. You will label each
item on one dimension (relevance). You label what you read; you are not expected to know how anyone else labelled it.

## What you receive and what you must not seek

You receive one sheet (CSV or JSON) with the columns `item_id`, `question`, `context`, `answer` and empty label columns. The `context` (which may be empty) is
the store information that was available to the assistant, as numbered blocks `[1]`, `[2]`. It is not needed to judge relevance, but it is shown because the assistant had it.

You must not look for, ask for or open: the repository these instructions live in, any model output or "verdict", any earlier label, the
other labeller's sheet, or any explanation of how items were made. If you have already seen any of these, declare it (below).

## The dimension you label

This round labels **one dimension only: relevance**. There are no groundedness columns on your sheet.

### Relevance (the only dimension in this round)

Question you answer: does the ANSWER address what the QUESTION actually asks?

* **PASS**: the answer is responsive to the question that was asked.
* **FAIL**: the answer is off topic, mainly unrelated material, or evades the question (for example only restates it, or defers without reason).
* **UNKNOWN**: there is no usable question to compare against (for example it is empty).

Relevance is not correctness and not groundedness. Decide only whether the answer is responsive. Whether being responsive can include saying
the information is not available is for you to judge from the criteria above; explain your reasoning in `note` when it was a close call.

## Reason codes

Choose exactly one reason that belongs to the label you chose. These come from the rubric vocabulary.

| Dimension | PASS | FAIL | UNKNOWN |
|---|---|---|---|
| relevance | `addresses_question` | `off_topic`, `evasive_or_non_answer` | `question_missing`, `low_confidence`, `dimension_not_applicable` |

`dimension_not_applicable` is an addition for human labellers and is not part of the shipped rubrics; it is reported separately. Use it only when the answer or question makes relevance impossible to apply for a reason other than a missing question.

## What UNKNOWN means

UNKNOWN is a valid, final answer: "a careful reader cannot decide this from what is on the page." It is not "I am unsure between PASS and
FAIL because I am tired" and it is not "skip". If you lean one way but are not sure, give that label and record low confidence (below).
If the page genuinely does not contain enough to decide, give UNKNOWN. Every row needs a label; a blank is invalid.

## Recording uncertainty

* `relevance_confidence`: `LOW`, `MEDIUM` or `HIGH`. `LOW` means you could reasonably have chosen another
  label. Use it freely; it is information, not a failure.
* `note`: free text, at most 2000 characters, for anything a third reader needs (which phrase, which block, why close). Do not copy any text
  from outside this sheet. Do not write the name of any person.

## Independence rules

1. Two labellers work separately. **No discussion** of items, labels, definitions or difficulty with each other or anyone else, before,
   during or after, until the adjudicator has finished.
2. **No model assistance** of any kind: no chatbot, search engine, translator, autocomplete or grammar tool applied to the items.
3. **No exposure to model outputs** or earlier labels. If you notice something that looks like one, stop reading it, note the item id to the
   coordinator, and carry on with your own judgement.
4. Do not look up the store, product or prices anywhere. The context on the page is the only evidence.
5. Ask the coordinator only about *how to use the sheet*. Questions about what a label should be will not be answered; they are not
   evidence-neutral.
6. Do not edit `item_id`, `question`, `context` or `answer`. An edited sheet is rejected.

## Time-boxing

The coordinator states the time budget before you start (proposal: at most 3 hours in total, in sessions of at most 60 minutes, with a
break between sessions). Record the date and approximate minutes in `note` of the first row of each session if asked. Do not rush items to
fit; if you run out of time, return what you have with the remaining rows blank: an incomplete sheet is rejected and the coordinator
arranges more time. Do not guess to finish.

## Conflict-of-interest and exposure declaration

Before starting, send the coordinator (not the other labeller) a short statement answering:

1. Did you write, review or help build the assistant, the store text, the evaluation code or its documentation?
2. Do you have a financial or reporting-line interest in the result of this evaluation?
3. Have you seen any model verdict, earlier label or discussion of these items?
4. Have you used AI systems to work on this project in a way that shaped what you expect the answers to be?

A "yes" is not automatically disqualifying; it must be recorded and the owner decides whether you may label. A false "no" invalidates the run.

## Identity

Put your assigned **role identifier** (for example the one the coordinator gives you) in `labeller_id` on every row. Use a role identifier
(letters, digits, `.`, `_`, `-`; no personal names). Identifiers containing words such as example, test, sample or placeholder are refused.

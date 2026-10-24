# Evaluation checklist (30-60 minutes)

Tick as you go; write the time each step took in the margin. Stop at any point and tell us
where and why.
See the [guide](../EXTERNAL_EVALUATION.md).

## Before you start (5 min)

- [ ] I can run Python 3.11, 3.12 or 3.13.
- [ ] I have one agent flow or pipeline I can call from a Python script.
- [ ] I can state, in code, what a correct result looks like for at least one kind of request
      (a phrase, a tool that must or must not be called, a latency bound).
- [ ] I will use synthetic or non-sensitive inputs only.

## Install (5 min)

- [ ] Cloned the repository and created a virtual environment.
- [ ] `pip install "agent-reliability>=1.2.0"` succeeded.

## Example (10 min)

- [ ] `cd examples/support_agent_evaluation && python run_evaluation.py` ran.
- [ ] My console output matches the README (differences: ______).
- [ ] I read one failure in `--format markdown` and understood why it was flagged.
- [ ] I could tell which failures a "run completed" status would not have shown.

## Your agent (20-30 min)

- [ ] Wrapped one request in `sdk.run(...)` ([guide](../EXTERNAL_EVALUATION.md), section 5).
- [ ] Chose one indicator and one evaluator; recorded the evaluation.
- [ ] Ran at least 30 requests (fewer is fine for a first look; say how many).
- [ ] Set a first SLO and read the report (reliability, SLO status, error budget).
- [ ] Checked at least three failures and three passes by hand.

## Judge it (5-10 min)

- [ ] Did it find a failure you did not already know about? Describe it in the template.
- [ ] Was any flag wrong (false positive) or any problem missed (false negative)?
- [ ] What would you need to run this regularly?

## Finish

- [ ] Fill in [FEEDBACK_TEMPLATE.md](FEEDBACK_TEMPLATE.md) and send it to the person who invited
      you, or open an issue without secrets or customer data. Report security problems privately
      (Security tab, Report a vulnerability), never in a public issue.

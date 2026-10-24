# Evaluating Agent Reliability on your own agent

A guide for a first, independent evaluation of the open-source `agent-reliability` Python
SDK. Plan 30 to 60 minutes. A tick-list is in
[external-evaluation/EVALUATION_CHECKLIST.md](external-evaluation/EVALUATION_CHECKLIST.md). You need no account, no hosted service and no API key.

> The bundled example is **synthetic validation** written by the SDK authors. It is not
> evidence about real users or about your agent.

## 1. What the SDK does (and does not)

Agent runs often *complete* while the answer is wrong. The SDK lets you wrap one logical
agent execution in a run, judge one property of its result with an evaluator (pass, fail
or unknown), and compute reliability against an explicit objective:

* an **SLI**: passes divided by considered observations, as an exact fraction;
* an **SLO**: a target for that ratio (for example at least 90%);
* an **error budget**: how many bad results the SLO tolerates, and how much is left;
* **provenance**: every result records which evaluator produced it, and the SDK **refuses**
  to average results from different evaluators or evaluator versions instead of returning a
  misleading number.

It runs locally. It sends nothing over the network, and it does not capture prompts,
responses or tool arguments unless you pass them to an evaluator yourself.

It does **not**: trace your agent automatically, call a model to judge answers (the LLM-judge
tooling is experimental and not covered here), decide what "correct" means for you, or give
you a dashboard. Nothing in this evaluation needs a server or a hosted service.

## 2. Who should evaluate

A developer who owns a Python agent or LLM pipeline and can say, in code, what a good result
looks like for at least one kind of request (an expected phrase, a tool that must or must not
be called, a latency bound). If correctness for your agent can only be judged by a person or a
model, the stable evaluators will cover little; please say so in your feedback.

## 3. Install

Python 3.11, 3.12 or 3.13.

```bash
git clone https://github.com/kamleshd07/agent-reliability.git
cd agent-reliability
python -m venv .venv && . .venv/bin/activate
python -m pip install "agent-reliability>=1.2.0"
```

The runnable example lives in the repository (`examples/`), not in the installed package, so a
clone is needed for step 4. Your own agent only needs the pip install.

## 4. Run the example (about 10 minutes)

```bash
cd examples/support_agent_evaluation
python run_evaluation.py
```

It evaluates a synthetic support agent in two versions over 38 synthetic requests, offline.
Compare your console output with the README in that folder, and read `--format markdown` for
the full report. Everything in it is synthetic: it shows what the reports look like, not how
good the SDK is for your agent.

## 5. Instrument your own agent

Wrap one request in `sdk.run(...)`, evaluate one property, record it, and keep the observation.
This complete script runs as written; replace `my_agent` and the request list with yours.

```python
from fractions import Fraction

from agent_reliability.domain import ObjectiveDirection, Slo, UnknownPolicy
from agent_reliability.evaluation import (
    ContainsEvaluator,
    EvaluationExecutionFailure,
    EvaluatorIdentity,
)
from agent_reliability.reliability import (
    AggregationConflict,
    ReliabilityObservation,
    evaluate_reliability,
)
from agent_reliability.reporting import format_report
from agent_reliability.sdk import AgentReliability, EvaluatorRunner


def my_agent(request: str) -> str:  # stand-in for your existing agent call
    return (
        "Refund issued for ORDER-1" if "refund" in request else "Please contact support"
    )


my_requests = [
    "refund order 1",
    "where is my parcel",
    "refund order 2",
    "refund order 3",
]

sdk = AgentReliability()  # no network, no configuration
runner = EvaluatorRunner()
evaluator = ContainsEvaluator(EvaluatorIdentity("mentions-order-number", "1"), "ORDER-")
observations = []
for request in my_requests:
    with sdk.run(agent_id="my-agent", name="My Agent", version="1") as run:
        answer = my_agent(request)
        result = runner.evaluate(evaluator, answer)
        if isinstance(result, EvaluationExecutionFailure):
            continue  # the evaluator itself failed; decide how you want to count this
        run.record_evaluation(indicator="task_success", result=result)
        observations.append(
            ReliabilityObservation.from_evaluation(
                indicator="task_success", result=result
            )
        )

report = evaluate_reliability(
    indicator="task_success",
    observations=observations,
    slo=Slo("task-success", Fraction(9, 10), ObjectiveDirection.AT_LEAST),
    unknown_policy=UnknownPolicy.TREAT_AS_BAD,
)
if isinstance(report, AggregationConflict):
    raise SystemExit(
        f"incomparable evaluations: {sorted(r.value for r in report.reasons)}"
    )
print(format_report(report))
```

With the stand-in agent above it prints (3 of 4 pass, so the 90% objective is breached and
the error budget is overspent):

```text
Indicator: task_success
Observations: pass=3 fail=1 unknown=0 considered=4 (unknown_policy=treat_as_bad)
Reliability: 75.00%
SLO: task-success target=90.00% direction=at_least status=BREACHED
Error budget: status=measured remaining=-150.00%
Measurement health: HEALTHY
```

Built-in evaluators you can use today: equality, predicate (any Python function returning
true/false/unknown), contains, regex match, latency threshold, tool called and tool not called.
The tool evaluators take the **names** of tools your code decides to disclose, never arguments.
See [INTEGRATIONS.md](INTEGRATIONS.md) and [EVALUATE.md](EVALUATE.md); the objective
semantics are in [SLO_SEMANTICS.md](SLO_SEMANTICS.md).

## 6. Define a first SLO

1. Pick **one** indicator that matters (for example "the answer states the refund amount").
2. Pick an evaluator you trust more than your intuition; keep its identity (name and version)
   fixed. If you change what it judges, change its version.
3. Run at least 30 representative requests; fewer is anecdotal.
4. Set the target near what you measure today minus a margin you accept, not at 100%.
5. Choose the UNKNOWN policy deliberately: `TREAT_AS_BAD` is conservative, `EXCLUDE` reports
   only what could be judged. The SDK makes you choose.
6. Re-run after each change to the agent and compare.

## 7. Read the result

* **Reliability** is exact, not an estimate. With small samples one case moves it a lot.
* **SLO status** is met or breached against your target. **Budget remaining** below zero means
  the budget is overspent; the size shows by how much.
* **Pass/fail/unknown counts** are kept separate; UNKNOWN is never silently counted as pass.
* **A conflict** (for example `evaluator_version_mismatch`) means you mixed incomparable
  evaluations; report each cohort separately.
* The important comparison is *run completed* versus *evaluation failed*: those are the runs a
  green status page does not show you.
* A failing evaluation is only as right as the evaluator. Check a few failures and a few
  passes by hand before you believe the number.

## 8. Known limitations

* Stable evaluators are deterministic checks; they cannot judge meaning or tone.
* The stable SDK does not trace tool calls automatically; you pass tool names to an evaluator.
* Burn rate needs timestamps and windows you must supply; the example does not demonstrate it.
* The example is synthetic and offline; its results say nothing about your agent.
* Failure grouping across many runs is not part of the SDK.
* The example folder is in the repository, not the installed package.
* Python 3.11 to 3.13 only. Continuous integration runs on Linux; Windows is not verified.
* No external developer has yet reported on this evaluation: its only validation so far is the
  synthetic example, and your feedback is what would change that.

## 9. Feedback questions

1. Which result, if any, would you not have found with your own logs, metrics and traces?
   Which did you already know?
2. Was any failure explanation wrong, unclear or a false positive? A missed failure?
3. How long did the install, the example, and wiring your own agent take?
4. Which indicator would you add first?
5. Would you act on the error-budget numbers? What would you need to trust them?
6. What blocked or confused you (install, naming, reports, documentation)?
7. Would you run this regularly, for example in CI? What would make that practical?
8. Would you keep using it? Why or why not?

A copy-and-fill template is [external-evaluation/FEEDBACK_TEMPLATE.md](external-evaluation/FEEDBACK_TEMPLATE.md);
a tick-list for the whole evaluation is
[external-evaluation/EVALUATION_CHECKLIST.md](external-evaluation/EVALUATION_CHECKLIST.md).

## 10. Report findings or ask for help

* **Feedback or a bug:** open an issue at
  <https://github.com/kamleshd07/agent-reliability/issues> (public: do not include secrets,
  customer data or real conversations), or reply to the person who invited you.
* **A security problem:** do **not** open a public issue. Use GitHub private vulnerability
  reporting: the repository's **Security** tab, then **Report a vulnerability**. See
  [SECURITY.md](../SECURITY.md).

This is an early open-source evaluation: support is best-effort, with no commitment or
response time.

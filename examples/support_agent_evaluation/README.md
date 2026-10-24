# Support-agent reliability evaluation (offline, deterministic)

**What this is.** A small, runnable evaluation that shows what `agent-reliability`
tells you about a tool-using AI agent that *looks* fine in its logs. It runs a
synthetic customer-support agent over 38 synthetic requests, measures four
reliability indicators with the SDK, and prints reliability, SLO status, error-budget
consumption, the failures behind them, and which of those failures ordinary run status
and logs would not have shown you.

**What this is not.** It is not a benchmark, not evidence about real users, and not
evidence that the SDK works for your agent. It is **synthetic validation**: the agent,
its defects and its faults are written by the SDK authors. Whether the approach is
useful *for you* is exactly what the feedback questions at the end ask.

Language: Python 3.11, 3.12 or 3.13. No network, no model call, no API key, no
cloud account and no hosted Gentlity service is needed or used. Nothing is sent
anywhere. The only runtime dependency is `agent-reliability` itself.

## Prerequisites and install

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install agent-reliability          # or: pip install -e .  from a clone
```

Copy this folder (`examples/support_agent_evaluation`) anywhere, or run it in place.

## Run it

```bash
cd examples/support_agent_evaluation
python run_evaluation.py                     # console summary for v1 and v2
python run_evaluation.py --output-dir out    # also writes out/report.json and out/report.md
python run_evaluation.py --format markdown   # the full readable report on stdout
python run_evaluation.py --version v1 --case S01   # reproduce one case
```

From a clone you can also run `python -m examples.support_agent_evaluation` in the
repository root. Runs are byte-for-byte reproducible: compare your `out/report.json`
with [`expected/report.json`](expected/report.json) (`diff` should print nothing).

### Expected console output

```text
cases: 38 (organic 26, injected 12)
[v1]
  task_success: 52.6% slo=breached budget=measured
  refund_policy: 25.0% slo=breached budget=measured
  escalation: 12.5% slo=breached budget=measured
  latency: 91.7% slo=breached budget=measured
  silent failures (no log signal): 15; runs with a failed indicator: 21/38
[v2]
  task_success: 89.5% slo=breached budget=measured
  refund_policy: 100.0% slo=met budget=measured
  escalation: 100.0% slo=met budget=measured
  latency: 100.0% slo=met budget=measured
  silent failures (no log signal): 4; runs with a failed indicator: 4/38
```

`budget=measured` means an error budget was computed; the Markdown report shows how
much of it is left (negative means overspent). Machine-readable fields are described
in [`docs/EVALUATE.md`](../../docs/EVALUATE.md) and [`docs/SLO_SEMANTICS.md`](../../docs/SLO_SEMANTICS.md).

## What is being measured

| Indicator | Evaluator (built in) | SLO | Meaning |
|---|---|---|---|
| `task_success` | `PredicateEvaluator` ("accepted phrase present") | ≥ 90% | the answer contains an accepted phrase for the request |
| `refund_policy` | `ToolNotCalledEvaluator("issue_refund")` | ≥ 99% | a refund above 100 USD was not issued without a human |
| `escalation` | `ToolCalledEvaluator("escalate_to_human")` | ≥ 95% | the agent handed off when it had to |
| `latency` | `LatencyThresholdEvaluator(3.0 s)` | ≥ 95% | the **simulated** response time is within 3 s |

* **Reliability (SLI)** is passes divided by considered observations, as an exact
  fraction. **SLO status** is `met` or `breached` against the target above.
* **Error budget** is the number of bad events the SLO tolerates; `remaining` below zero
  means the budget is overspent. Burn rate needs time windows; this dataset has none, so
  it is intentionally not reported.
* **UNKNOWN** is never treated as pass or fail silently: `latency` excludes runs that
  crashed before a duration existed (their failure is counted by `task_success`).
* **Provenance**: every observation carries its evaluator identity. The report also
  shows the SDK refusing to average two versions of one evaluator (`evaluator_version_mismatch`).

No score is computed outside the SDK. `harness.py` feeds observations to
`evaluate_reliability` and reads the result with `report_to_dict`.

## The workload

`agent.py` is a deterministic stand-in for a support assistant with three tools
(`search_kb`, `lookup_order`, `issue_refund`, plus `escalate_to_human`). Two versions
exist so you can see a **regression comparison**:

* **v1** (naive): ranks articles by word overlap with the article text, trusts every
  tool result, ignores superseded articles, issues refunds up to 250 USD without
  approval (policy says 100), waits for slow tools, and crashes on an empty retrieval.
* **v2** (hardened): prefers the most specific article, skips superseded ones, treats a
  tool error as "unverified, hand off", enforces the threshold in code, bounds tool waits
  and handles empty retrieval. v2 is **not perfect** (see below).

Cases are in `data/cases.json` and each is labelled by origin:

| Origin | Cases | What it is |
|---|---|---|
| organic (26) | K01-K08, R01-R04, L01-L02, O01-O04, F01-F08 | ordinary requests; failures are consequences of how v1/v2 were written, not injected |
| injected (12) | E01-E04 (order tool error), T01-T03 (slow search), S01-S03 (stale article), N01-N02 (empty retrieval) | faults the dataset injects on purpose |

**Honest labelling.** "Organic" means "no fault is injected"; the agent's defects are
still the authors' design. K06 ("When will my refund arrive after approval?") was **not**
a planned failure: both versions retrieve the refund-approval article because of the word
"approval". It is kept exactly as found. Injected failures demonstrate that detection
works; they are not independent evidence of customer value.

## What you should see (and what it means)

| What happened | Detected by | Visible without Gentlity? |
|---|---|---|
| v1 answers "Your order is on its way" after the order tool failed (E01-E04) | `task_success` and `escalation` | a WARNING line exists, but the run completes and nothing says the customer was misled |
| v1 refunds 129-240 USD without approval (F04-F06) | `refund_policy`, `escalation`, `task_success` | no: run status OK, INFO log only |
| v1 quotes the 14-day policy from a stale article (S01-S03) | `task_success` | no log line at all |
| v1 returns a returns-window answer to a final-sale question (R01-R04) | `task_success` | no log line at all |
| v1 waits 8 s for a slow search but answers correctly (T01-T03) | `latency` | no: correct and completed, just late |
| v1 crashes on an empty retrieval (N01-N02) | `task_success` (empty answer), `latency` UNKNOWN | yes: run fails, ERROR log |

For every failure `report.json` (`versions.<v>.failures[]`) contains: the case, the
indicator and evaluator reason code, whether it was organic or injected, the log signal
it would have produced, the request and answer, tools called, the command to reproduce
it, and a corrective action for its failure mode. The failure-mode labels and corrective
actions are written by the dataset authors in `data/cases.json`, not inferred by the SDK.

## Accuracy, false positives and limitations

* `evaluator_accuracy_vs_oracle` compares each evaluator FAIL with an independent
  oracle that reads the agent's *structured* claim, not the answer text. Differences are
  real evaluator errors: **L02** is a false positive (a correct answer that omits the
  accepted phrase "United States"); **L01 (v1 and v2)** is a false negative (a wrong
  answer that still contains the weak phrase "30 days"; v2 also answers L01 with the
  returns-window article, so its real failure is hidden by the weak phrase). K06, R02 and
  R04 show that v2 still fails `task_success` (4 detected bad events against the 3.8 its
  SLO allows), and L01 is a fifth failure that the evaluator misses.
* Text matching is a weak judge of meaning. The SDK also offers experimental LLM-judge
  and calibration tooling; this package deliberately uses only the stable, deterministic
  evaluators.
* Latency is simulated (a number the agent reports), not measured wall time.
* 38 cases is enough to show the mechanics, not to estimate a real failure rate.
* Failure patterns across many runs (correlation) are a platform capability and are not
  part of this SDK-only package.
* Burn rate is not computed (no time windows).
* The SDK records evaluations only for what you instrument; a crash is evaluated outside
  the run because the run has already failed (the evaluators need no active run).

## Use it on your own agent

Replace `SupportAgent.handle(case)` with a call to your agent that returns an
`AgentResult` (answer text, the **names** of tools called, a duration, optional structured
claims for an oracle) and edit `data/cases.json`. Keep one evaluator identity per
indicator; if you change an evaluator's behaviour, change its `version`, or the SDK will
(correctly) refuse to mix the results. The SDK never needs your prompts, tool arguments or
responses; this example passes only an answer string and tool names to the evaluators.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: agent_reliability` | install it (`pip install agent-reliability`) in the active environment |
| `ImportError: attempted relative import` | run `python run_evaluation.py` from this folder, or `python -m examples.support_agent_evaluation` from a clone |
| Output differs from `expected/report.json` | different `agent-reliability` version (this was produced with the 1.3.x stable API) or edited data; `pip show agent-reliability` |
| `no case matches` | pass an id from `data/cases.json` (for example `S01`) |

## Feedback questions for external developers

1. Which finding, if any, would you not have found with your logs and traces? Which did
   you already know?
2. Was any failure explanation wrong, unclear or a false positive?
3. How hard was it to wire your own agent into the same indicators?
4. Which indicator would you add first for your use case?
5. Would you act on the error-budget numbers? What would you need to trust them?
6. What blocked you (install, data model, reports, naming)?
7. Would you run this in CI against a fixed dataset? What would make that practical?

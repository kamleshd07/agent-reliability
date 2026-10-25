# Support-agent reliability evaluation (offline, deterministic)

**What this is.** A small, runnable evaluation that shows what `agent-reliability`
reports for a tool-using AI agent whose runs complete normally while some of its answers
are wrong. It runs a synthetic customer-support agent over 38 synthetic requests,
measures four reliability indicators with the SDK, and prints reliability, SLO status,
error-budget consumption, the failures behind them, and which of those failures a
run-status-plus-warning-logs view would not have flagged.

**What this is not.** It is not a benchmark, not evidence about real users, and not
evidence that the SDK works for your agent. It is **synthetic validation**: the agent,
its defects, its faults and its dataset are all written by the SDK authors. Whether the
approach is useful *for you* is what the feedback questions at the end ask.

Language: Python 3.11, 3.12 or 3.13. No network, no model call, no API key, no cloud
account and no hosted Gentlity service is needed or used; nothing is sent anywhere. The
only dependency is `agent-reliability` **1.2.0 or later** (verified with the published
1.3.0 wheel; 1.0.x and 1.1.x lack `LatencyThresholdEvaluator`).

## Prerequisites and install

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install "agent-reliability>=1.2.0"      # or: pip install -e .  from a clone
```

The `examples/` folder ships in the source distribution and the repository, not in the
wheel. Run it in place, or copy the folder elsewhere **keeping the folder name**
`support_agent_evaluation` (it is a Python package).

## Run it

```bash
cd examples/support_agent_evaluation
python run_evaluation.py                     # console summary for v1 and v2
python run_evaluation.py --output-dir out    # also writes out/report.json and out/report.md
python run_evaluation.py --format markdown   # the full readable report on stdout
python run_evaluation.py --version v1 --case S01   # reproduce one case
```

From a clone you can also run `python -m examples.support_agent_evaluation` in the
repository root. `--output-dir` creates the directory and overwrites existing report
files. A run with `--case` or `--version` produces a partial report that will not equal
`expected/`. A full run is byte-for-byte reproducible: `diff out/report.json
expected/report.json` should print nothing.

### Expected console output

```text
cases: 38 (organic 26, injected 12)
[v1]
  task_success: 52.6% n=38 slo=breached budget=measured
  refund_policy: 25.0% n=4 (small sample) slo=breached budget=measured
  escalation: 12.5% n=8 (small sample) slo=breached budget=measured
  latency: 91.7% n=36 slo=breached budget=measured
  confirmed failures with no WARNING/ERROR line: 14; runs with a confirmed failed indicator: 20/38
[v2]
  task_success: 89.5% n=38 slo=breached budget=measured
  refund_policy: 100.0% n=4 (small sample) slo=met budget=measured
  escalation: 100.0% n=8 (small sample) slo=met budget=measured
  latency: 100.0% n=38 slo=met budget=measured
  confirmed failures with no WARNING/ERROR line: 3; runs with a confirmed failed indicator: 3/38
```

`budget=measured` means an error budget was computed; the Markdown report shows how
much is left (negative = overspent). **Small samples:** `refund_policy` has 4 and
`escalation` 8 considered observations, so one case swings the percentage, the SLO
verdict and the (large, negative) budget figure; treat them as anecdotal. Field meanings:
[`docs/EVALUATE.md`](../../docs/EVALUATE.md), [`docs/SLO_SEMANTICS.md`](../../docs/SLO_SEMANTICS.md).

## What is being measured

| Indicator | Evaluator (built in) | SLO | Meaning |
|---|---|---|---|
| `task_success` | `PredicateEvaluator` ("accepted phrase present") | ≥ 90% | the answer contains an accepted phrase for the request |
| `refund_policy` | `ToolNotCalledEvaluator("issue_refund")` | ≥ 99% | a refund above 100 USD was not issued without a human (cases where that applies) |
| `escalation` | `ToolCalledEvaluator("escalate_to_human")` | ≥ 95% | the agent handed off when it had to (cases where that applies) |
| `latency` | `LatencyThresholdEvaluator(3.0 s)` | ≥ 95% | the **simulated** response time is within 3 s |

* **Reliability (SLI)** is passes divided by considered observations, an exact fraction.
  **SLO status** is `met` or `breached` against the target above. Which cases an indicator
  applies to is chosen by the dataset (`must_escalate`, `refund_allowed`), so those
  denominators are authored, not discovered.
* **Error budget**: the bad events the SLO tolerates; negative remaining = overspent.
  Burn rate needs time windows; the dataset has none, so it is not reported.
* **UNKNOWN** is never treated as pass or fail silently: `latency` excludes the two runs
  that crashed before a duration existed (their failure is counted by `task_success`).
* **Provenance**: every observation carries its evaluator identity; the report shows the
  SDK refusing to average two versions of one evaluator (`evaluator_version_mismatch`).

No score is computed outside the SDK. `harness.py` feeds observations to
`evaluate_reliability` and reads the result with `report_to_dict`. All evaluations,
including those of the two crashed runs, are recorded inside their SDK runs (the harness
checks that the event stream carries every observation).

## The workload

`agent.py` is a deterministic stand-in for a support assistant with tools `search_kb`,
`lookup_order`, `issue_refund` and `escalate_to_human`. Two versions exist so you can see
a **regression comparison**:

* **v1** (naive): ranks articles by word overlap with the article text, trusts every tool
  result, ignores superseded articles, issues refunds up to 250 USD without approval
  (policy says 100), waits for slow tools, crashes on an empty retrieval.
* **v2** (hardened): prefers the most specific article, skips superseded ones, treats a
  tool error as "unverified, hand off", enforces the threshold in code, bounds tool waits,
  handles empty retrieval. v2 is **not perfect** (below).

The agent reads the dataset's `fault` label to behave as faulted, and v2 is written to
handle each fault. The v1 -> v2 improvement is therefore **by construction**: the
comparison shows how the SDK reports a change, not that v2 is a good agent.

Cases are in `data/cases.json`, each labelled `organic` (no fault injected) or `injected`:

| Origin | Cases | What it is |
|---|---|---|
| organic (26) | K01-K08, R01-R04, L01-L02, O01-O04, F01-F08 | ordinary requests. Some were written to probe known weak spots (R, L, F04-F07 are bait for v1's defects); failures here are consequences of how v1/v2 were written, not injected |
| injected (12) | E01-E04 (order tool error), T01-T03 (slow search), S01-S03 (stale article), N01-N02 (empty retrieval) | faults the dataset injects on purpose |

**Honest labelling.** "Organic" means "no fault is injected", not "found in production".
K06 ("When will my refund arrive after approval?") was a failure the authors did not
intend when writing the dataset (both versions retrieve the refund-approval article
because of the word "approval"); it was discovered on the first run and is kept
unchanged. That statement is the authors' recollection, not something the repository
history can prove. Injected failures show that detection works; they are not independent
evidence of customer value.

## What you should see (and what it means)

"Ordinary view" below means **run status plus the WARNING/ERROR lines this example
agent was written to emit**. It deliberately ignores metrics, traces, dashboards and
alerts a real team may have (anyone charting latency would see the slow cases). It is an
illustration of the gap between "the run completed" and "the answer was right", not a
measurement of your tooling.

| What happened | Detected by | Flagged by the ordinary view? |
|---|---|---|
| v1 answers "Your order is on its way" after the order tool failed (E01-E04) | `task_success`, `escalation` | only a WARNING line; the run completes and nothing says the customer was misled |
| v1 refunds 129-240 USD without approval (F04-F06) | `refund_policy`, `escalation`, `task_success` | no: run OK, INFO log only |
| v1 quotes the 14-day policy from a stale article (S01-S03) | `task_success` | no log line |
| v1 returns a returns-window answer to a final-sale question (R01-R04); both versions answer K06 wrongly | `task_success` | no log line |
| v1 waits 8 s for a slow search but answers correctly (T01-T03) | `latency` | no log line (a latency metric would show it) |
| v1 crashes on an empty retrieval (N01-N02) | `task_success` (empty answer), `latency` UNKNOWN | yes: failed run, ERROR log |

For every failure `report.json` (`versions.<v>.failures[]`) records: the case, the
indicator and evaluator reason code, organic or injected, the log signal it produced,
the request and answer text, tools called, the command to reproduce it, and a corrective
action for its failure mode. Failure-mode labels and corrective actions are written by the
dataset authors in `data/cases.json`, not inferred by the SDK.

## Accuracy, false positives and limitations

* **Text matching versus the agent's own structured claim** (`task_success` only): the
  report counts cases where the text check and the agent's reported fact ids disagree.
  This is a cross-check, not an independent oracle: if the agent mis-reports its own
  facts it is wrong too, and for `refund_policy`, `escalation` and `latency` the "truth"
  would be the same value the evaluator already reads, so no accuracy is claimed for them.
* **L02** is a text-matching false positive (a correct answer that omits the accepted
  phrase "United States"); it is excluded from the "confirmed failure" counts and listed
  separately. **L01** is a false negative in both versions (a wrong returns-window answer
  that still contains the weak phrase "30 days"). v2's `task_success` SLO is breached by
  four bad events (K06, R02, R04 detected, plus the false positive L02) against 3.8
  allowed, while its real failures are K06, R02, R04 and the undetected L01: the verdict
  holds only because a false positive and a false negative cancel.
* Text matching is a weak judge of meaning. The SDK also has experimental LLM-judge and
  calibration tooling; this package deliberately uses only stable, deterministic
  evaluators.
* Latency is simulated (a number the agent reports), not measured wall time.
* 38 cases show the mechanics; they cannot estimate a real failure rate.
* Correlating failure patterns across many runs is out of scope for this package.
* Burn rate is not computed (no time windows).

## Data this example writes

`report.json` and `report.md` include the synthetic request and answer text so you can
read each failure. That is this example's choice. The SDK itself does not capture
prompts, responses or tool arguments by default, and the evaluators here receive only an
answer string and tool *names*. Do not point this harness at real customer conversations
without deciding what the reports may contain.

## Use it on your own agent

Replace `SupportAgent.handle(case)` with a call to your agent returning an `AgentResult`
(answer text, the **names** of tools called, a duration, optional structured claims) and
edit `data/cases.json`. Keep one evaluator identity per indicator; if an evaluator's
behaviour changes, change its `version`, or the SDK will (correctly) refuse to mix the
results.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: agent_reliability` | install it in the active environment |
| `ImportError: cannot import name 'LatencyThresholdEvaluator'` | `agent-reliability` older than 1.2.0 |
| `ModuleNotFoundError: support_agent_evaluation` | the folder was renamed; restore the name or run it in place |
| `ImportError: attempted relative import` | run `python run_evaluation.py` from this folder, or `python -m examples.support_agent_evaluation` from a clone |
| Output differs from `expected/report.json` | partial run (`--case`/`--version`), edited data, or a different SDK serialization; check `pip show agent-reliability` |
| `error: no case matches 'XYZ'` | pass an id from `data/cases.json` (for example `S01`) |

## Feedback questions for external developers

1. Which finding, if any, would you not have found with your own logs, metrics and
   traces? Which did you already know?
2. Was any failure explanation wrong, unclear or a false positive?
3. How hard was it to wire your own agent into the same indicators?
4. Which indicator would you add first for your use case?
5. Would you act on the error-budget numbers? What would you need to trust them?
6. What blocked you (install, data model, reports, naming)?
7. Would you run this in CI against a fixed dataset? What would make that practical?

A fuller walkthrough and a feedback template: [docs/EXTERNAL_EVALUATION.md](../../docs/EXTERNAL_EVALUATION.md).

# Gentlity on an upstream open-source agent: smolagents text-to-SQL

**What this is.** A reproducible evaluation of `agent-reliability` (the Gentlity SDK) on an
agent it did not write: the open-source [`smolagents`](https://github.com/huggingface/smolagents)
`ToolCallingAgent` answering questions about a SQL table through upstream's own `sql_engine`
tool. A small local language model drives the agent. Gentlity wraps each request in a run,
evaluates four indicators and reports reliability, SLO status and error budget.

**What this is not.** It is a *local real-world integration*: a real third-party agent loop, a real
(small) model, real tool execution. It is **not** independent external validation (no outside
developer has run it yet), not hosted or production validation, and not a benchmark of
`smolagents`. Read [Limitations](#limitations) before drawing conclusions.

| Item | Value |
|---|---|
| Upstream agent | `smolagents` 1.26.0 (tag `v1.26.0`, commit `12c1bc8`), Apache-2.0 |
| Agent class | `ToolCallingAgent` (the model emits JSON tool calls; **no model-written code is executed**) |
| Upstream scenario | `examples/text_to_sql.py`: table `receipts` (4 rows) and the `sql_engine` tool |
| Model | `qwen2.5-coder:7b` through a local Ollama server, temperature 0, seed 0 |
| Gentlity SDK | `agent-reliability` 1.3.0 from PyPI (no SDK change, no new SDK dependency) |
| Cases | 36 questions: 1 is upstream's own example question, 35 are written by the Gentlity authors |
| Python | recorded on 3.12; clean install and replay verified on 3.12 and 3.13; 3.11 is supported by the SDK and `smolagents` but was not run for this example |

## Run it (about 5 minutes, no model, no network after install)

```bash
git clone https://github.com/kamleshd07/agent-reliability.git && cd agent-reliability
python -m venv .venv && . .venv/bin/activate
python -m pip install -r examples/smolagents_text_to_sql_evaluation/requirements.txt
cd examples/smolagents_text_to_sql_evaluation
python run_evaluation.py                       # replay the recorded model responses
python run_evaluation.py --output-dir out      # also writes out/report.json and out/report.md
diff out/report.json expected/report.json      # prints nothing: byte-for-byte reproducible
python run_evaluation.py --case Q33            # reproduce one case (partial report)
```

The replay runs the **real** upstream agent loop and the **real** SQL tool; only the model's
responses come from `transcripts/qwen2.5-coder-7b.json`. Replay stops with `ReplayDivergence`
if the conversation shown to the model ever differs from the recorded one, so a changed tool,
dataset or `smolagents` version cannot be mistaken for a faithful replay. The upstream agent
prints one tool-error message to the console (case Q35); that is expected.

Expected console summary:

```text
agent: smolagents 1.26.0 ToolCallingAgent; model qwen2.5-coder:7b (recorded 2026-10-24)
cases: 36
  task_success: 86.1% n=36 slo=breached budget=measured left=-39%
  tool_used: 100.0% n=36 slo=met budget=measured left=100%
  tool_execution: 97.2% n=36 slo=met budget=measured left=44%
  latency: 100.0% n=36 slo=met budget=measured left=100%
task failures: 5; with no upstream error signal (silent): 5
```

### Re-record against a live model (optional, about 1 minute on a laptop)

```bash
ollama pull qwen2.5-coder:7b && ollama serve &     # local; no account or API key
python run_evaluation.py --mode live --record --tag my-run   # --api-base defaults to localhost:11434; keep it on localhost
python run_evaluation.py --tag my-run --output-dir out-my-run
```

Two live recordings made for this evaluation gave identical final answers for all 36 cases
(`transcripts/qwen2.5-coder-7b-run2.json` is the second recording, kept only as evidence of that and not used by any report); a different machine, Ollama
version or model build may differ. `adjudication_*.json` is keyed to one recording, so copy and
edit it (or remove it) for your own run.

## What is measured

| Indicator | Evaluator (built in) | SLO | Meaning |
|---|---|---|---|
| `task_success` | `PredicateEvaluator` | at least 90% | the final answer agrees with an **independent SQL reference** (`reference_sql` in `data/cases.json`, run with `sqlite3`; the agent never sees it) |
| `tool_used` | `ToolCalledEvaluator("sql_engine")` | at least 95% | the agent queried the database instead of answering from memory |
| `tool_execution` | `PredicateEvaluator` | at least 95% | no step raised a tool or parsing error, even one the agent recovered from |
| `latency` | `LatencyThresholdEvaluator(10 s)` | at least 95% | wall-clock time of the run (recorded at recording time) |

The SLOs and the 10-second threshold were written into `harness.py` before the first full run and have not been changed since; the repository history is a single commit, so you cannot verify that order, and the question set was likewise not edited after results. Gentlity does the counting;
the harness only adapts the agent's step log (`return_full_result=True`) into evaluator inputs.
The `task_success` evaluator receives the answer text plus the case record (which includes the reference, all synthetic); the tool evaluators receive tool **names** only. The SDK itself captures no prompts, responses or tool arguments.

## Results (one recording, 36 cases)

| Indicator | Reliability | SLO | Error budget left |
|---|---|---|---|
| `task_success` | 86.1% (31 of 36) | breached | -39% (5 bad events against 3.6 allowed) |
| `tool_used` | 100% | met | 100% |
| `tool_execution` | 97.2% | met | 44% (Q35) |
| `latency` | 100% (median 1.5 s, slowest 6.0 s) | met | 100% |

### What the 5 failed answers actually were (every one read by hand)

| Case | Verdict | What happened | Visible from the upstream agent's own signals? |
|---|---|---|---|
| Q33 "How much did Bob Smith pay?" | **true failure** | the query returned no rows; the agent invented "$10.50" | no: run state `success`, no step error |
| Q36 "price of receipt number 9?" | **true failure** | no such receipt; the agent invented "12.50" | no |
| Q34 "email address on receipt 3?" | **true failure** | there is no email column; the agent answered with a customer name | no |
| Q16 "tip as a percentage of the price" | evaluator too strict | the agent said "10%"; exact value 10.16% | no |
| Q15 "How much did Alan Payne pay?" | ambiguous question | the agent answered price plus tip (13.26); the authors' reference was price only | no |

The headline therefore has two honest readings. As scored by the evaluators, `task_success` is
**breached** (86.1%, SDK-computed). After the authors' own hand adjudication removes the 2 non-failures from the bad events it is 91.7% (33 of 36) and the 90% objective is **met**; that second reading rests on the authors' judgement (Q15 and Q16 were identified as non-failures after the results were seen, and left unchanged in the data). Q15 is a flaw in a question the authors wrote and Q16 is a tolerance the authors chose; neither is an agent defect. The one finding that is about the agent:
**all 3 genuine failures are unanswerable questions** (3 of the 4 such cases failed) and the
32 answerable questions had no genuine failure beyond Q16's small rounding imprecision. The
unanswerable cases were included deliberately as negative controls, so "natural" here means
"not injected", not "unprompted". When a query returns nothing, this
model-and-agent combination invents an answer, and the upstream run still reports success.

All failures here occurred naturally with this model: nothing was injected, no tool was made to
fail, and no case was selected after seeing results. Q35 (a correct "date not available" answer
after a SQL error on a non-existent column) is the only run with a tool error.

## Does Gentlity add anything over what you already have?

`python compare_baselines.py` prints, per failing case, what ordinary signals say. In this run:

* **The agent's own outcome** (run state, step errors, empty output) flags **0 of the 3 genuine
  failures**; it only flags Q35, which was correct. A custom check for "the tool returned nothing but
  the agent answered confidently" would have flagged Q33 and Q36 (their observations are empty) but
  not Q34; the upstream agent does not ship such a check.
* **A plain assertion loop** (`expected in answer`) catches the same 3 genuine failures, but also
  fails Q04 and Q23 (`27.62` is not the text `27.615`), so it needs the same tolerance rules the
  Gentlity evaluator needed. Both use the same reference, so detection is equivalent by construction.
* **What Gentlity added beyond that**: one tally per indicator with an explicit objective and an
  error budget (`-39%` rather than a pile of assertion messages); a separation of "the run
  completed" from "the answer was wrong" per run; a refusal to mix evaluator versions; and
  `tool_execution`, which counted the recovered SQL error that the success state hid. It did **not**
  explain *why* the model invented an answer, find the empty query result, or suggest a fix: that
  needed reading the step log.
* **Cost**: wiring needed 4 evaluators, about 70 lines of adapter code (`harness._agent_step_facts`, `execute_case`,
  `_evaluate`) and no change to the upstream agent. `python measure_overhead.py` measured well under a millisecond (about 0.2 ms in a 10-pass run; the figure is within timer noise) against 1 to 6 s of model time.
* **Not compared**: framework tracing backends and hosted evaluation tools were not run.

The honest summary: for this agent, Gentlity found **no failure that a careful assertion test would
have missed**. Its value shown here is the framing and aggregation (SLI, SLO, budget, silent versus
visible), not new detection. Whether that matters to your team is the question below.

## Use it on your own agent

1. Keep your agent unchanged. Run it with `return_full_result=True` (smolagents) or collect
   the final answer, the **names** of the tools called, and any step errors from your framework.
2. Wrap each request in `with sdk.run(agent_id=..., name=..., version=...) as run:` and call
   `run.record_evaluation(indicator=..., result=...)` for each evaluator result
   (`harness.run_cases` is a worked example).
3. Write the reference independently of the agent (`checks.answer_matches`); an answer checked
   against the agent's own claim only tests that the agent is consistent.
4. Fix the SLOs before looking at results.

## Limitations

* **One agent, one table, one small model.** 4 rows, 36 questions, a 7B model. Rates say nothing about
  other models, larger data or your agent.
* **Authored questions.** 35 of 36 questions were written by the SDK authors, who also chose the
  reference answers; Q15 shows a reference can be arguable. Only Q01 comes from upstream.
* **Tool calls that raise** are not in smolagents' `tool_calls`; the adapter reads the attempted call back from the model output so `tool_used` and the SQL list still include it.
* **Replay is of one recording.** The model's responses are fixed; replay proves the pipeline is
  deterministic, not that a new run would behave identically (two live runs did).
* **Latency** is recorded wall-clock time on the recording machine, not measured at replay.
* **`absent`-case checking is keyword based** (`checks.ABSENT_PATTERN`): the answer must contain a refusal word and no number of its own; it can still pass an answer that contains "not" and a wrong non-numeric claim. All answers were read by hand (`data/adjudication_*.json`).
* **`sql_engine` runs whatever SQL the model writes.** It is upstream's tool, kept as is. Each case
  gets a fresh in-memory database so a write cannot reach the next case, but SQLite can still be asked to `ATTACH DATABASE` a file path, which creates a file on disk; a misbehaving model in `--mode live` could do that. Replay cannot (the recorded queries contain no `ATTACH`, `PRAGMA`, `DROP` or write statements). Run live mode in a scratch directory and do not point the tool at real data.
  `CodeAgent` (which executes model-written Python) was deliberately **not** used.
* No hosted service, no semantic or LLM judge, no framework tracing, no CI wiring.
* Upstream's own tests (v1.26.0, `test_agents`, `test_tools`, `test_memory`): 172 passed, 5 skipped,
  6 failed and 1 error in a minimal environment; every failure is a missing optional extra (`ddgs`,
  `gradio`, `torch`/`transformers`, `mcpadapt`) or `python` not on `PATH`, none an agent defect.

## Known integration gaps (not implemented here)

* The stable SDK does not capture a framework's tool calls; the harness reads them from the
  `smolagents` step log and passes tool names.
* No helper maps a framework run result to evaluator inputs; each team writes that adapter.
* The SDK has no concept of "the answer to an unanswerable question"; that case needed a custom rule.
* Burn rate needs timestamped windows; this offline set has none.
* Examples are not in the published wheel, so a clone is needed.

## Feedback for external developers

Please answer in your own words; short is fine. Do not include secrets or real customer data.

1. Which result, if any, would you not have found with your own tests, logs and traces?
2. Was any verdict wrong or unclear? (This evaluation already found one ambiguous question and one too-strict tolerance.)
3. How long did setup take, and where did you get stuck?
4. How hard was it to wire your own agent? How many lines of adapter code?
5. Which indicator would you add first for your agent?
6. Would you act on the error-budget numbers? What would you need to trust them?
7. Would you run this in CI? What would make that practical?
8. What would you expect Gentlity to explain that it does not?

Report feedback or bugs at <https://github.com/kamleshd07/agent-reliability/issues> (public).
Report security problems privately through GitHub's **Security, Report a vulnerability**, never
in a public issue.

## License and attribution

`scenario.py` adapts upstream's `examples/text_to_sql.py` (Apache-2.0, Copyright Hugging Face). No
`smolagents` source is copied or modified; it is installed from PyPI at the pinned version. The
recorded model output in `transcripts/` was produced by `qwen2.5-coder:7b` (Apache-2.0 weights as
published by Alibaba Cloud/Qwen); it is test data, not a claim about that model.

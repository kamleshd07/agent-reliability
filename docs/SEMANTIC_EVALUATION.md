# Semantic evaluation (EXPERIMENTAL)

Evaluate what your agent actually said, in your own environment, and send only bounded evidence to Gentlity. This page is the
developer path for `agent_reliability.experimental.judge.SemanticChecks`, a small facade over the experimental LLM-judge machinery
described in [EVALUATE.md](EVALUATE.md). It adds no wire member, no dependency and no hosted service. It is **Experimental**
([VERSIONING.md](VERSIONING.md), ADR-0010): names and defaults may change in a minor release.

## The five steps

```python
from agent_reliability.experimental.judge import SemanticChecks
from agent_reliability.adapters.http_event_sink import HTTPEventSink   # pip install "agent-reliability[http]"
from agent_reliability.sdk import AgentReliability

checks = SemanticChecks(my_provider, model_label="local-gemma",          # 2. define the evaluator: YOUR model object, no keys read by the SDK
                        checks=("groundedness", "relevance"))
sink = HTTPEventSink(...,                                                # 1. SDK + sink (HTTP_EXPORTER.md). The sink drops any indicator
                     indicator_allowlist=[checks.indicator("groundedness"),  # that is not allowlisted, so list the semantic ones
                                          checks.indicator("relevance")])
sdk = AgentReliability(sink=sink)
with sdk.run(agent_id="kettle-bot", name="Kettle bot", version="1.0") as run:
    answer = my_agent(question)                                          # 3. execute your agent
    with checks.scope(run) as scope:                                     # 4. evaluate the actual result
        verdict = scope.check("groundedness", answer, context=[doc], question=question)
print(checks.coverage())                                                 # 5. the sink sends it; read reliability AND failure/UNKNOWN rates
```

Then create an SLO on the indicator (`semantic-groundedness`) in the platform ([PLATFORM_QUICKSTART.md](PLATFORM_QUICKSTART.md)) and read
reliability, error budget and measurement health there. A runnable offline version is [`examples/semantic_quickstart.py`](../examples/semantic_quickstart.py).
A blocking provider uses `with checks.scope(run)` and `scope.check(...)`; an async provider uses `async with` and `await scope.acheck(...)`.

| Check | Rubric (reference, uncalibrated) | Inputs | Indicator |
|---|---|---|---|
| `groundedness` | `judge-groundedness` | `answer`, `context=[...]`, optional `question` | `semantic-groundedness` |
| `relevance` | `judge-answer-relevance` (new) | `answer`, `question`, optional `context` | `semantic-relevance` |
| `correctness` | `judge-answer-correctness` | `answer`, `reference` | `semantic-correctness` |
| `requirements` | `judge-instruction-adherence` | `answer`, `requirements="..."` or a list | `semantic-requirements` |
| `completion` | `judge-task-completion-evidence` | `answer` (the claim), `evidence` | `semantic-completion` |

Replace a reference rubric with your own (`rubrics={"groundedness": my_rubric}`, same dimension, change `rubric_version`). A new rubric version or
model should also get a new `indicator_prefix`, because the platform pools by indicator.

## What a verdict means

`SemanticVerdict.status` is one of:

* **determinate**: the judge returned PASS or FAIL. A model opinion about one dimension; `authoritative` is always `False`.
* **unknown**: the judge could not decide, or a required input was missing and **no model was called** (empty context, no question).
* **evaluator_failure**: the evaluator did not produce a judgment (timeout, provider error, refusal, malformed or truncated output, budget, overload).
  Recorded as an execution failure and as unavailable measurement health. **Never a FAIL, never in the reliability denominator, and
  `is_agent_failure_signal` is `False`.**
* **skipped**: sampling, admission or a non-recording run declined it; no evidence exists.

Rules that keep this honest: a judge FAIL is a flag for review, not proof of a business outcome; keep a deterministic check wherever one exists
(price equals catalogue price, tool was called, order id exists) and treat it as the authority; read the failure rate and the UNKNOWN rate **beside**
reliability, because both leave the denominator (99 failures and one PASS read as reliability 1.0). `coverage()` prints them together and offers no
single "healthy" value.

## Security and privacy

* The judge runs where your provider runs. The facade imports no network, file or environment module (tested) and reads no credential.
* Raw question, answer, context and reference go **only** to the provider object you pass. They are never retained, logged, hashed or exported.
  What can reach Gentlity is the indicator, the outcome, a closed reason code (`<dimension>.<code>`), the evaluator identity labels and, for failures,
  one of ten fixed class names. Verdict objects, reprs and `coverage()` carry no evaluated text (tested with a marker string).
* All evaluated text is untrusted data. The prompt wraps each block in nonce-delimited markers that content cannot forge, tells the model not to follow
  instructions inside them, and accepts only one strict JSON document (`gentlity.judge-output/1`), re-asking once on a malformed reply. A model that
  obeys injected text anyway is a model failure that calibration measures; the SDK cannot make a weak judge strong.
* `requirements=` and `reference=` are sent as **untrusted** by default (a user's message must never become operator-trusted instructions). Declare
  `trusted=["requirements"]` only for text you wrote. Misspelled or foreign inputs, a non-string answer and a `str` context are handled explicitly:
  a typo raises `ValueError` before any model call, and a bare `str` context is one block.
* **Admission is off by default**: the facade runs ungated and `coverage()` shows it as "ungated model-backed". To admit only calibrated judges, pass
  `admission=lambda check, judge: CalibrationGate(...)` (a factory receiving the judge it will gate); `checks.evaluator(name)` exposes the judge.
* Provider failure is explicit: it is an `evaluator_failure`, not a PASS.
* Bounds: `JudgeLimits` (per-attempt timeout, total deadline, attempts, input and output size), `JudgeBudget` (tokens and cost per window),
  `SamplingPolicy` (deterministic rate), `max_concurrency`, `max_pending`. A blocking provider runs in a bounded helper thread, so a provider that
  never returns cannot block the agent beyond the deadline (`enforce_deadline=True`, the default).

## Measured on a real agent (local, synthetic, small)

Agent: a retrieval shopping assistant on a synthetic catalogue, answering with a local `gemma4:12b` (22 recorded executions). Of these, two replies were
empty (the planted-instruction cases `q19`, `q20`: the agent's own token budget ran out) and the rest were correct or honest refusals. Two honest refusals
(`q03`, `q11`) came from a retriever miss: the retrieved documents did not contain the answer. Golden set: 53 cases = those 22 real answers + 31
constructed defective or tricky answers. Judge: the same local `gemma4:12b` through an OpenAI-compatible loopback endpoint, rubrics uncalibrated, up to 2
attempts. Data and code: [`examples/semantic_shopping_evaluation/`](../examples/semantic_shopping_evaluation/README.md).

**The labels were written by the implementing assistant, not by a human, and the same model both produced and judged the real answers.** The first
version of the labels was written before any judge ran; an independent review then found four labels that contradict the labelling policy, and they were
corrected afterwards (below). A human reviewer has not approved any label. This is a pilot measurement with wide intervals, not an accuracy claim, and not
evidence about any other model or domain.

| Run | `max_output_tokens` | Evaluator failures (of 93 evaluations) |
|---|---|---|
| example default | 512 (the SDK's `JudgeLimits` default is 256) | 5 (5.4 %), all `JudgeInvalidOutputError` |
| tuned | 1536 | 0 |

The five failures were the reasoning model spending its whole output budget thinking so that the reply was cut off. A diagnostic re-run of the five
confirmed `finish=length` on each at 512 tokens (that re-run is not part of the committed data; the committed files record only the failure class). They
were classified as evaluator failures and not as agent FAILs, which is the intended behaviour; the fix is configuration. **Set `max_output_tokens`
generously for reasoning models and watch the failure rate.**

### Label review and recomputed metrics

The original labels and the stored verdicts are preserved as measured. `golden.py` records each correction with its reason (`CORRECTIONS`) and the labels
that are defensible either way (`AMBIGUOUS`); `evaluate report FILE original|corrected|clear` recomputes the metrics:

* `q03`, `q11` relevance FAIL -> PASS: the retriever missed, so the honest refusal was responsive (the earlier text that the data "was present" was wrong).
* `c19` relevance FAIL -> PASS: a wrong but responsive answer is a relevance PASS.
* `r01` groundedness PASS -> FAIL: the delivery claim is not in the kettle-only context.
* Ambiguous, unchanged: `c12`, `c15`, `c17`, `c18` (groundedness) and `q17` (relevance).

Tuned run (judge-determinate cases; Wilson 95 % intervals):

| Label view | Groundedness agreement | Groundedness FP / FN | Relevance agreement | Relevance FP / FN |
|---|---|---|---|---|
| original (as first labelled) | 36/37 [86.2, 99.5] | 0 of 13 / 1 of 24 | 48/52 [81.8, 97.0] | 3 of 9 / 1 of 43 |
| corrected | 37/37 [90.6, 100] | 0 of 14 / 0 of 23 | 51/52 [89.9, 99.7] | 0 of 6 / 1 of 46 |
| corrected, ambiguous excluded (sensitivity only) | 35/35 [90.1, 100] | 0 of 13 / 0 of 22 | 51/51 [93.0, 100] | 0 of 6 / 0 of 45 |
| corrected, the 22 real answers only | 13/13 | n/a | 21/22 | 0 of 2 / 1 of 20 |

(FP = judge PASS where the label is FAIL, the dangerous direction; FN = judge FAIL where the label is PASS.) Do not read the corrected figures as better
performance: they changed because labels were fixed after the judge had been seen, and the "ambiguous excluded" row is a sensitivity check that removes
the cases the judge got arguably right or wrong. The original row is what was measured against the original labels.

What stands after correction:

* **The judge never returned UNKNOWN on its own.** Across 93 evaluations in each run, the only two UNKNOWN verdicts were the deterministic pre-checks (an empty
  context, an empty question; 0 ms, no model call). For the conflicting-evidence case (`c15`) it said PASS and for the truncated-evidence case (`c17`) FAIL.
  The UNKNOWN behaviour of this judge is therefore **not demonstrated**; on 3 UNKNOWN-labelled cases the only reliable UNKNOWN is the pre-check. Treat an
  absent UNKNOWN rate as a warning, not as good news.
* **Groundedness flagged all labelled unsupported or contradicted answers**, including two prompt-injection attempts (an instruction in the answer, and one
  in the context), in this set. The relevance judge accepted every honest refusal; whether it would accept a refusal that was *not* justified (the answer
  was available but the agent said it did not know) is **untested**: no such case exists in the set. That needs a correctness or completeness check against a
  reference, and a case that exercises it.
* **Self-judging.** The judge and the agent are the same model, which can inflate agreement; the 31 constructed answers were not model-generated, which limits
  but does not remove the effect. A different-model run was not completed (see the recommendation below).
* Latency is per evaluation (including any repair re-ask), not per provider call: groundedness p50 5.1 s / p95 21.6 s, relevance 4.6 s / 16.3 s, maximum 48.3 s;
  tokens (input/output) 26,089 / 13,902 and 33,993 / 17,163; cost: local model, no charge (`JudgeBudget` prices are optional and unset).

### Different-model calibration recommendation

Before any customer pilot: (1) use a judge model of a different family and at least comparable size to the agent's model (a 7B coder model was tried locally
and could not be evaluated: the local runtime was unavailable during the attempt, so no result exists and none is claimed); (2) have at least two humans label
the set independently from the policy in `golden.py`, record their agreement, and replace the assistant labels; (3) add cases that this set lacks:
unjustified refusals, conflicting and truncated evidence in several forms, and enough UNKNOWN-labelled cases (30 or more) to bound the UNKNOWN rate; (4) run each
judge at least three times with `JudgePolicy(repeats=3)` or repeated runs and report repeatability; (5) report per-source results and keep the thresholds
(for example a false-positive ceiling) fixed *before* the run, using `run_calibration` and the calibration gate so only judged-acceptable evidence is admitted.
No managed-model service or hosted key is needed or authorised for this.

## End-to-end roundtrip

SDK facade -> `HTTPEventSink` -> platform (uvicorn, OIDC mode) -> PostgreSQL 16, locally on a disposable database. `python -m tools.pilot.semantic_e2e`
in the private platform repository replays the recorded verdicts of the **tuned** run through the real facade, adds four injected real faults (a provider
that outlives its deadline, a malformed reply, a provider error, a refusal), sends deterministic evidence to a second deployment, and reads the platform back
(14 of 14 checks): 292 events committed and persisted; per-indicator PASS/FAIL/UNKNOWN equal the SDK's (groundedness 24/15/1, relevance 45/7/1); the 4
evaluator failures are execution failures and unavailable measurement health, none a FAIL; reliability equals PASS/(PASS+FAIL) (0.615 and 0.865); an SLO
evaluates; and a marker string appended to every question, answer and context is absent from all 72 tables. The script refuses any database whose name
does not end in `_test`.

## Measurement health is per deployment, not per indicator or run

One evaluator failure marks measurement health `UNAVAILABLE` for its run, and the platform counts health **per deployment and time window**. The roundtrip
shows it: `semantic-relevance` had no failure of its own, yet its summary reports `unavailable_count = 4` because four failing runs of the same deployment fall
in the window. A separate *run or scope* therefore does **not** isolate deterministic indicators from judge failures. What does (no contract change): send
judge evidence to its **own deployment** (for example a second environment or agent registration with its own `deployment_id` and sink). The roundtrip
confirms a deterministic indicator in a separate deployment shows `unavailable_count = 0`. Whether a platform-side per-indicator health attribution is wanted
is a canonical-semantics change that needs architecture review; it is recorded as a follow-up, not implemented.

## Limitations

* Experimental namespace; reference rubrics are uncalibrated; no accuracy claim. Customer pilot use stays gated by safeguards SG-1 to SG-6
  ([P29_PILOT_SAFEGUARDS.md](P29_PILOT_SAFEGUARDS.md)), all still not satisfied.
* The platform's coverage gate does not read measurement health, and one judge failure marks every indicator in that scope and window unavailable.
  Use a separate *deployment* for judge evidence where deterministic SLOs must stay readable (a separate run or scope does not help; see above).
* One evaluation per indicator per scope; a multi-turn agent needs a run per turn or distinct indicator names.
* No provider is shipped (by decision); the example adapters are copy-and-adapt code. Token and cost budgets undercount late discarded replies.
* The golden set is small, partly constructed, assistant-labelled (four labels corrected after the fact) and self-judged. Nothing here ran against a hosted service or a customer.
* A check still in flight when its scope drains is reported as an evaluator failure with class `JudgeTimeoutError`.

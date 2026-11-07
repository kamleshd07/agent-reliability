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

sdk = AgentReliability(sink=HTTPEventSink(...))                          # 1. install the SDK, point it at Gentlity (HTTP_EXPORTER.md)
checks = SemanticChecks(my_provider, model_label="local-gemma",          # 2. define the evaluator: YOUR model object, no keys read by the SDK
                        checks=("groundedness", "relevance"))
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
* Provider failure is explicit: it is an `evaluator_failure`, not a PASS.
* Bounds: `JudgeLimits` (per-attempt timeout, total deadline, attempts, input and output size), `JudgeBudget` (tokens and cost per window),
  `SamplingPolicy` (deterministic rate), `max_concurrency`, `max_pending`. A blocking provider runs in a bounded helper thread, so a provider that
  never returns cannot block the agent beyond the deadline (`enforce_deadline=True`, the default).

## Measured on a real agent (local, synthetic, small)

Agent: a retrieval shopping assistant on a synthetic catalogue, answering with a local `gemma4:12b` (22 recorded executions; 4 were genuinely poor: two
refusals although the data was present, two empty replies). Golden set: 53 cases = those 22 real answers + 31 constructed defective or tricky answers.
Judge: the same local `gemma4:12b` through an OpenAI-compatible loopback endpoint, rubrics uncalibrated, up to 2 attempts. Data and code:
[`examples/semantic_shopping_evaluation/`](../examples/semantic_shopping_evaluation/README.md). **The labels were written by the implementing assistant
before any judge ran; they are not independent human adjudication, and the same model both produced and judged the real answers.** This is a pilot
measurement with wide intervals, not an accuracy claim and not evidence about any other model or domain.

| Run | `max_output_tokens` | Evaluator failures (of 93 evaluations) | Groundedness agreement (judge-determinate) | Relevance agreement |
|---|---|---|---|---|
| default limits | 512 | 5 (5.4 %), all `JudgeInvalidOutputError` | 35/36 = 97.2 % [85.8, 99.5] | 45/48 = 93.8 % [83.2, 97.9] |
| tuned | 1536 | 0 | 36/37 = 97.3 % [86.2, 99.5] | 48/52 = 92.3 % [81.8, 97.0] |

All five failures were the reasoning model spending its whole output budget thinking, so the reply was cut off (`finish=length`, confirmed on each).
They were classified as evaluator failures and not as agent FAILs, which is the intended behaviour; the fix is configuration. **Set `max_output_tokens`
generously for reasoning models and watch the failure rate.**

Tuned run, error analysis (Wilson 95 % intervals are in the verdict reports):

| | Groundedness | Relevance |
|---|---|---|
| False positives (judge PASS, label FAIL), the dangerous direction | 0 of 13 labelled FAIL (contradictions, unsupported additions, two prompt-injection attempts, in the answer and in the context) | 3 of 9: `q03`, `q11` (the agent refused although the data was present; the judge accepted the refusal as responsive) and `c19` (see below) |
| False negatives (judge FAIL, label PASS) | 1 of 24: `r01` | 1 of 43: `q17` (an out-of-scope refusal to a joke request judged evasive) |
| UNKNOWN-labelled cases | 1 of 3 returned UNKNOWN (the empty-context case, decided by the pre-check with no model call); the conflicting-context case was judged PASS and the truncated-context case FAIL | 1 of 1 (empty question, pre-check) |
| Latency per model call, p50 / p95 | 5.1 s / 21.6 s | 4.6 s / 16.3 s |
| Tokens, input / output | 26,089 / 13,902 | 33,993 / 17,163 |
| Cost | local model, no charge (`JudgeBudget` prices are optional and unset) | same |

Two label mistakes were found by reading the disagreements afterwards and are **left as labelled** in the numbers above: `r01` (the answer is about
delivery but the context holds only the kettle, so the judge's FAIL was right) and `c19` (an answer that states a wrong price is still responsive, so
relevance PASS was arguably right). Corrected, groundedness would be 37/37 and relevance 49/52; do not read the corrected figures as a result, because
they were adjusted after seeing the judge.

What this supports: groundedness flagged every labelled unsupported or contradicted answer in this set, including the injection attempts, and a judge
failure never contaminated the reliability number. What it does not support: any statement about UNKNOWN calibration (3 cases), refusals the agent should
not have made (the relevance judge cannot see that the answer was available; that needs a correctness or completeness check against a reference), other
models, other domains, or a self-judging bias estimate (use a different judge model in production).

## End-to-end roundtrip

SDK facade -> `HTTPEventSink` -> platform (uvicorn, OIDC mode) -> PostgreSQL 16, locally on a disposable database. `python -m tools.pilot.semantic_e2e`
in the private platform repository replays the recorded verdicts through the real facade, adds four injected real faults (a provider that outlives its
deadline, a malformed reply, a provider error, a refusal) and reads the platform back: 263 events committed and persisted; per-indicator
PASS/FAIL/UNKNOWN equal the SDK's; the 4 evaluator failures are execution failures and unavailable measurement health, none a FAIL; reliability equals
PASS/(PASS+FAIL); an SLO evaluates; and a marker string appended to every answer and context is absent from all 72 tables.

## Limitations

* Experimental namespace; reference rubrics are uncalibrated; no accuracy claim. Customer pilot use stays gated by safeguards SG-1 to SG-6
  ([P29_PILOT_SAFEGUARDS.md](P29_PILOT_SAFEGUARDS.md)), all still not satisfied.
* The platform's coverage gate does not read measurement health, and one judge failure marks every indicator in that scope and window unavailable.
  Use a separate scope for judge indicators where deterministic SLOs must stay readable.
* One evaluation per indicator per scope; a multi-turn agent needs a run per turn or distinct indicator names.
* No provider is shipped (by decision); the example adapters are copy-and-adapt code. Token and cost budgets undercount late discarded replies.
* The golden set is small, partly constructed, assistant-labelled and self-judged. Nothing here ran against a hosted service or a customer.

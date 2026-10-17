# Evaluate

How to judge an indicator once you can execute your agent. See
[Instrument](../examples/basic_reliability.py) first if you have not wrapped
a run yet, and [Concepts](CONCEPTS.md) for what "evaluator," "indicator," and
"provenance" mean.

## Built-in evaluators

All built-in evaluators live in `agent_reliability.evaluation` and share the
same shape: construct one with an explicit `EvaluatorIdentity` and
configuration, then call `.evaluate(value)` directly or through
`EvaluatorRunner` (recommended — it attaches provenance and converts a raw
exception into a distinct `EvaluationExecutionFailure`, never into `FAIL` or
`UNKNOWN`).

| Evaluator | Judges | UNKNOWN case |
|---|---|---|
| `EqualityEvaluator` | `value == expected` | never |
| `PredicateEvaluator` | a trusted `Callable[[T], bool \| None]` | when the predicate returns `None` |
| `ContainsEvaluator` | substring presence in a `str`, optional case-insensitivity | never |
| `RegexMatchEvaluator` | a stdlib `re` pattern (`search` or `fullmatch`) against a `str` | never — a malformed pattern raises at construction, not evaluation |
| `LatencyThresholdEvaluator` | an explicit `duration_seconds` against a threshold | when `duration_seconds` is `None` (no measurement captured) |
| `ToolCalledEvaluator` / `ToolNotCalledEvaluator` | presence/absence of a tool name in a `frozenset[str]` you supply | never |

Run [`examples/builtin_evaluators_quickstart.py`](../examples/builtin_evaluators_quickstart.py)
to see `ContainsEvaluator` and `LatencyThresholdEvaluator` produce `PASS`,
`FAIL`, and a legitimate `UNKNOWN` in one script, and
[`examples/tool_call_evaluators.py`](../examples/tool_call_evaluators.py) for
the tool-name evaluators.

## What UNKNOWN means here

`UNKNOWN` means the evaluator ran to completion but could not reach a
definite judgment — for example, `LatencyThresholdEvaluator` receiving
`duration_seconds=None` because your timing instrumentation did not capture
a value for that run. It is never used for "the evaluator crashed" (that is
an `EvaluationExecutionFailure`, isolated by `EvaluatorRunner`) and never
silently becomes `FAIL`. See [Concepts](CONCEPTS.md#unknown) and
[GA_CONTRACT.md](GA_CONTRACT.md#frozen-outcome-and-uncertainty-semantics).

## Privacy boundary for tool evaluators

`ToolCalledEvaluator`/`ToolNotCalledEvaluator` accept only a bounded
`frozenset[str]` of tool-name identifiers you have already decided to
disclose. They never accept, inspect, or retain tool call arguments, tool
results, or framework-specific tool objects — see each class's docstring for
the exact contract, and
[`tests/security/test_m8_builtin_evaluator_privacy.py`](../tests/security/test_m8_builtin_evaluator_privacy.py)
for the adversarial tests that enforce it.

## Custom evaluators

Implement the `SyncEvaluator`/`AsyncEvaluator` protocol directly — no
inheritance or registration required. See
[EVALUATOR_FRAMEWORK.md](EVALUATOR_FRAMEWORK.md) for the full contract and
[`docs/EVALUATION_PROVENANCE.md`](EVALUATION_PROVENANCE.md) for why identity
and determinism matter to aggregation later.

## Reducing `AggregationConflict` boilerplate

`evaluate_reliability(...)` returns `ReliabilityReport | AggregationConflict`
so a genuine measurement incompatibility is never silently resolved. When a
call site has no recovery path other than failing loudly, use
`evaluate_reliability_or_raise(...)` instead — identical arguments, but it
raises `AggregationConflictError` (carrying the original conflict on
`.conflict`) instead of returning it. Keep using the explicit
`evaluate_reliability` form wherever you want to inspect or handle a
conflict programmatically.

## LLM-judge evaluators (EXPERIMENTAL)

`agent_reliability.experimental.judge` adds model-backed evaluators for semantic dimensions that equality and
predicates cannot express. It is **Experimental** ([versioning policy](VERSIONING.md)): names, defaults, the prompt template (`jp1`)
and vocabularies may change in a minor release with release notes. It is standard library only, ships no provider, reads no
credentials or environment, and adds no wire member and no runtime dependency. A judge is never deterministic
(`deterministic=False`).

### Privacy statement

Raw evaluated text (question, answer, context, reference, instructions, policy, task evidence) goes **only** to the provider object
you supply, and only the roles the rubric lists. The SDK never retains, logs, hashes, serializes, copies or exports it. What can reach
Gentlity through the existing evidence path is limited to the indicator name, the outcome, a closed reason code
(`<dimension>.<code>`), the evaluator identity labels (rubric id, rubric version, `configuration_id`) and, for failures, one of ten
fixed class names. Judge `reason` text, citations, confidence, token counts, latency, cost and the sampling rate stay local. What your
provider does with the prompt (retention, region, training) is governed by your agreement with that provider; the SDK makes no
statement about it. Labels you choose (`model_label`, indicator names) are stored by the platform and must not contain secrets,
hostnames or customer names.

### Quick start

```python
from agent_reliability.experimental.judge import (
    ContentPart,
    ContentRole,
    EvaluationRequest,
    IndicatorBinding,
    JudgeCoordinator,
    JudgeDimension,
    LLMJudge,
    load_reference_rubric,
)

judge = LLMJudge(
    rubric=load_reference_rubric("judge-groundedness"),
    provider=my_async_provider,  # any JudgeProvider; see examples/judge_providers.py
    model_label="local-llama3-8b-q4",  # non-sensitive label, chars [A-Za-z0-9._-]
)
coordinator = JudgeCoordinator([IndicatorBinding("groundedness", judge)])
async with sdk.run(agent_id="support-agent", name="Support", version="1.4.0") as run:
    answer = await agent.answer(question)
    async with coordinator.scope(run) as scope:
        await scope.evaluate(
            "groundedness",
            EvaluationRequest(
                JudgeDimension.GROUNDEDNESS,
                (
                    ContentPart(ContentRole.CONTEXT, snippet),
                    ContentPart(ContentRole.ANSWER, answer),
                ),
            ),
        )
    print(coordinator.coverage().describe())
```

A runnable offline version with scripted fake providers is `examples/judge_fake_provider.py`. Use `SyncLLMJudge` and
`scope.evaluate_sync` for blocking providers (no `asyncio.run` is used anywhere). Evaluations must finish inside the run block:
the scope drains pending work up to `drain_timeout_seconds` and records `JudgeTimeoutError` evidence for what is unfinished; a late
evaluation after the run is closed is not supported in V1.

### Meaning of PASS per dimension

The five reference rubrics (`judge-answer-correctness`, `judge-groundedness`, `judge-instruction-adherence`, `judge-safety-policy`,
`judge-task-completion-evidence`) are **uncalibrated examples**: not calibrated by Gentlity, no accuracy claim, domain thresholds are
yours. Load them with `load_reference_rubric(id)` or copy the JSON and edit it (change `rubric_version` whenever behavior changes).

| Dimension (rubric) | PASS means | PASS does not mean |
|---|---|---|
| `answer-correctness` (judge-answer-correctness) | no contradiction with the supplied reference and the required facts are present | the answer is correct in general |
| `groundedness` (judge-groundedness) | every material claim is supported by the supplied context blocks, with at least one citation | the context itself is true |
| `instruction-adherence` (judge-instruction-adherence) | the checkable items stated in the instructions were followed | unstated expectations were met (deterministic checks are better where possible) |
| `safety-policy` (judge-safety-policy) | this rubric found no violation of the supplied policy | the answer is safe |
| `task-completion-evidence` (judge-task-completion-evidence) | the evidence TEXT supports the claim of completion | the business outcome occurred (never an authoritative outcome; a fabricated confirmation passes it by construction; use an outcome expectation for critical journeys) |

### Outcomes, failures and what the platform sees

A completed judgment is PASS, FAIL or UNKNOWN (low confidence and judge disagreement are UNKNOWN). Anything else (timeout, provider
failure, refusal, invalid or oversize output, input over the limit, budget exhausted, queue shed) is an **execution failure**, recorded
with the class name as `exception_type`, never as an outcome. Failures and UNKNOWN leave the reliability denominator, so reliability must
be read **beside** the failure rate and the UNKNOWN rate: 99 failed attempts plus one PASS reads as reliability 1.0. The local
`coordinator.coverage()` report shows attempted, determinate, failed, unknown and unsampled counts together and offers no single "healthy"
value on purpose. Any failure marks the run's measurement health `UNAVAILABLE`, and the platform's health counts are not
indicator-scoped, so every indicator in that scope and window shows an unavailable `measurement_state`. Only a window with no determinate
evidence reaches a gate's `on_no_data`; a partial outage or a high UNKNOWN rate has no gate effect, so set `on_no_data` deliberately
(BLOCK where an outage must stop deployment). Failure evidence reaches the platform only when the SDK build's `record_evaluation_failure`
accepts `indicator=` and the sink supports health evidence; otherwise it is local run health only and the coordinator reports "failure
evidence not delivered".

### Timeouts, blocking providers and shutdown

* **Async (`LLMJudge`).** The per-attempt timeout and the total deadline are enforced with `asyncio.timeout`; cancellation propagates and records nothing.
* **Sync (`SyncLLMJudge`) is best effort.** A blocking call cannot be interrupted from outside. The judge passes the remaining deadline to your provider as `deadline_seconds` and
  classifies an overrun as `JudgeTimeoutError` only *after the call returns*, discarding the late reply. A provider that never returns blocks `evaluate_sync` indefinitely, and the
  scope's drain cannot help in the same thread. **The real bound is your provider's own socket/client timeout**: always set one (the example adapters pass `deadline_seconds` to the HTTP client).
  When you need the deadline enforced regardless, wrap the provider in `ExecutorSyncProvider(inner, max_threads=N)`: the call runs in a bounded daemon helper thread and is abandoned at the deadline
  (the thread itself cannot be killed and lives until the provider returns; beyond `max_threads` calls fail fast with `JudgeProviderUnavailableError`).
* **Tokens of discarded late replies are not counted.** A reply that arrives after its deadline (or after a drain timeout) is discarded together with its reported usage, so token and cost budgets
  can undercount what the provider billed. The documented overshoot bound applies; treat budgets as guard rails, not as billing.
* **`jitter` and clocks.** A custom `jitter` callable must return a number in `[0, 1]`; anything else raises `ValueError("jitter must return a number in [0, 1]")`, a programmer error that is not one of the ten failure classes.

### The recording gate: what runs inside it

Concurrent judge *execution* is never concurrent *recording*. Every call that hands evidence to the run handle is made while holding the scope's one recording gate. `RunHandle.record_*`
synchronously invokes your **sink and diagnostic handler inside that gate**, so they **must be non-blocking** (the HTTP exporter's `emit` is); a slow sink delays all recording of the scope.
A sink or diagnostic handler must not call back into the same `EvaluationScope`: such a re-entrant call raises `RuntimeError` instead of deadlocking. Application code must not record on the same
handle from another thread while a threaded scope has evaluations in flight.

"Recorded" means *handed to the run handle*. The SDK isolates a failing sink, so an evaluation reported as `RECORDED_RESULT` or `RECORDED_FAILURE` may still have been dropped by a sink that
raised; the coordinator cannot detect that. Watch your sink's own delivery status (for the HTTP exporter, its delivery snapshot) next to the coordinator's `coverage()`.

### Measurement-health safeguards

| Safeguard | What to do |
|---|---|
| Budget and overload limits | Size budgets and limits so budget exhaustion and overload do not occur (`JudgeBudget`, `JudgeLimits`, `max_pending`, `max_concurrency`); treat any `JudgeBudgetExceededError` or `JudgeOverloadedError` as an incident. Defaults are safe, not fast, and are not benchmarked |
| Run health | One judge failure sets run health `UNAVAILABLE`, which changes `measurement_state` for every indicator in the scope and window |
| Coverage monitoring | Read failure rate and UNKNOWN rate beside reliability (`coverage()`; platform reads of failure and UNKNOWN counts) |
| Scope separation | Do not interpret `measurement_state` of deterministic indicators while judge indicators share their scope and window; consider a separate scope for judge evaluation |
| Failure alerting | Wire a `JudgeObserver` (or poll `coverage()`) to your own alerting: failures by class, shed, skipped |
| No-data policy | Set `on_no_data` explicitly; partial outage is not covered |

### Identity and cohorts

The wire identity is `name=<rubric_id>`, `version=<rubric_version>`, `configuration_id=<model_label>.jp1.mc-<min_confidence>.rp<repeats>.ct<0|1>`,
all in the grammar `[A-Za-z0-9._-]` (1-128, alphanumeric ends) that both the SDK and the HTTP exporter accept. A `+`
(for example `1.0.0+build5`) is accepted by `EvaluatorIdentity` but rejected by the exporter, so evidence for such an identity is never
delivered; that hazard exists for any evaluator and is not changed here. The platform pools by indicator only: when a rubric or model
change should start a new cohort, also change the indicator name (for example `groundedness-v2`).

### Vocabulary notes

The contract lists `judge_abstained`, `low_confidence` and `judge_disagreement` as always-present unknown codes. The SDK requires `low_confidence` in every rubric and `judge_disagreement` when
`repeats > 1`; `judge_abstained` is *not* enforced (a rubric may omit it; the reference rubrics include it). `SamplingPolicy.salt` is validated more strictly than the contract's charset
(alphanumeric first and last character, 1-64 characters of `[A-Za-z0-9._-]`, or empty) so that it can never be rejected by an identity grammar if it is later folded into a label; salts such as `_pilot` are rejected.
A reply fenced with Windows line endings (`` ```json `` followed by CRLF) is rejected by the strict parser and costs one re-ask.

### Calibration

Calibration is a customer-local practice: `run_calibration` over your own labelled dataset with your own provider, producing a
content-free report. Gentlity receives no dataset, enforces no threshold and publishes no accuracy figure; see the calibration section
below. Results describe one rubric version, model label and dataset only.

### Local-model walkthrough (manual, not a CI criterion)

Prerequisites: a locally running OpenAI-compatible runtime (for example Ollama serving on `127.0.0.1:11434`), a model already pulled by
you (the SDK never downloads models), Python 3.11+, and this package. Steps: (1) copy `examples/judge_providers.py` next to your code;
(2) `provider = local_runtime_provider(model="<your model>")`; (3) build `SyncLLMJudge(rubric=load_reference_rubric(...), provider=provider,
model_label="<non-sensitive label>")`; (4) run a few requests through `JudgeCoordinator` with `evaluate_sync`; (5) read
`coordinator.coverage().describe()`. Model output is non-deterministic, so the output of this walkthrough is not an acceptance criterion
and no result of it is a claim about quality.

## Next

[Measure reliability locally](MEASURE_RELIABILITY_LOCALLY.md).

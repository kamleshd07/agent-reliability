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

## Next

[Measure reliability locally](MEASURE_RELIABILITY_LOCALLY.md).

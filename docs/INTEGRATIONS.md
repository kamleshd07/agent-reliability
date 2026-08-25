# Integration guide

Agent Reliability works at normal Python boundaries and requires no particular
agent framework.

## Basic custom agent

Wrap one logical user/task execution in `with sdk.run(...)`. Evaluate one
property of the result, record it on the run, and retain the corresponding
`ReliabilityObservation` wherever your application owns its analysis window.
See [the basic example](../examples/basic_reliability.py).

## Async application

Use `async with sdk.run(...)`. Context is isolated with `contextvars`, so
concurrent tasks retain their own current run. A synchronous deterministic
evaluator is fine for an async agent; await an `AsyncEvaluator` through
`EvaluatorRunner.evaluate_async(...)` when evaluation itself is asynchronous.

## Existing OpenTelemetry application

Install `agent-reliability[otel]` and pass
`OpenTelemetryRunContextBridge()` to `AgentReliability`. The bridge joins the
host's current context and creates/activates the agent span. The host owns the
provider, sampling, processors, propagation, exporter, and backend. The base
package does not import OpenTelemetry.

## Agent framework

Place the context manager around the framework call that represents one
logical execution. Do not monkey-patch framework internals or wrap every model
token/helper. Explicit instrumentation keeps the run and evaluation semantics
visible and continues to work when framework internals change.

## Evaluation placement

Evaluate inside the run when you want evaluation recording to share that
active run. Evaluation may also happen later: evaluators need no active SDK
run, and observations are plain immutable values. In either case, one
evaluation measures one indicator for one relevant execution/result.

The SDK never requires prompts, responses, tool arguments, credentials, or
arbitrary payloads. Only explicit identities, lifecycle fields, outcomes, and
bounded provenance are represented by these examples.

## Resolving aggregation conflicts

The engine returns structured reasons, not a partial number:

| Reason | Meaning | Resolution |
|---|---|---|
| `indicator_mismatch` | Observations measure different indicators | Calculate one report per indicator |
| `manual_evaluated_mix` | Manual and evaluated observations were mixed | Keep manual and evaluated cohorts separate |
| `evaluator_name_mismatch` | Different evaluation methods were used | Select one evaluator cohort |
| `evaluator_version_mismatch` | The evaluator behavior version changed | Report each version separately |
| `configuration_id_mismatch` | Evaluator configurations differ | Select one configuration cohort |
| `determinism_mismatch` | Deterministic and nondeterministic methods differ | Keep methodology cohorts separate |
| `window_cohort_mismatch` | Full and lookback windows use different cohorts | Build both windows from the same methodology |

See [Evaluation provenance](EVALUATION_PROVENANCE.md) for the compatibility
key and [the executable conflict example](../examples/provenance_conflict.py).

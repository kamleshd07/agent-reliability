# Evaluation Provenance

## Definition

Evaluation provenance is the immutable attribution necessary to interpret one
completed evaluation result. In M4 it answers:

```text
Which evaluator produced the judgment?
Which behavioral version?
Which caller-declared configuration identity, if any?
When did evaluation complete?
Was identical input/configuration expected to be reproducible?
```

The concrete model is:

```text
EvaluationProvenance
  identity
    name
    version
    configuration_id | None
  evaluated_at        timezone-aware UTC
  deterministic       bool
```

`deterministic=True` is a declaration about expected reproducibility for
identical relevant input and configuration. It is not a proof of correctness,
purity, thread safety, or trust. An equality evaluator can still invoke a
user-defined `__eq__`; a custom predicate can still depend on hidden state if
its author declares it inaccurately.

## Configuration responsibility

Evaluator authors/callers must change `version` or `configuration_id` whenever
a behaviorally material rule, threshold, schema, policy, prompt, model, or
other configuration changes. `configuration_id` is an opaque label, not raw
configuration and not an automatically generated hash. It must contain no
secret or customer content.

M5 local reliability analysis groups observations by:

```text
indicator
evaluator name
evaluator version
configuration identity
```

plus the evaluator's determinism declaration and manual/evaluated source. This
allows an evaluator change to be distinguished from an agent change. See
[LOCAL_RELIABILITY_ENGINE.md](LOCAL_RELIABILITY_ENGINE.md); per-observation
`evaluated_at` is deliberately not part of methodology compatibility.

## What provenance does not contain

M4 provenance never automatically contains:

- evaluation input or output;
- prompt, response, tool arguments, message history, or domain object;
- evidence or generic metadata;
- evaluator callable/class name;
- model/provider, policy, dataset, template, or reviewer fields;
- score, confidence, threshold, or free-form explanation;
- exception object, message, arguments, representation, or traceback;
- organization, workspace, deployment, or hosted-platform identifiers.

Future evaluator adapters may require richer typed provenance. They should add
narrow adapter-specific/versioned records or a reviewed contract rather than
turning this foundational value into an arbitrary metadata bag.

## Time semantics

The runner reads the existing injected `Clock` after an evaluator produces a
valid decision and normalizes the value through `EvaluationProvenance`.
Timezone-naive timestamps are rejected. A clock failure is an evaluation
execution failure at the `timestamp` stage; the framework does not invent a
timestamp or record a result without one.

## Manual outcomes and execution failures

A manual `run.record(...)` assertion has `provenance=None` on its emitted
event. Absence here is intentional, truthful information rather than a missing
fake evaluator.

`EvaluationExecutionFailure` is not provenance for an `EvaluationResult`: no
completed result exists. It is a separate, bounded failure description used
by the safe runner and diagnostic path. It must never enter reliability ratios
as `FAIL` or `UNKNOWN` automatically.

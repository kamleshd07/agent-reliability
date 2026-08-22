# Vision

## Problem

AI agents are increasingly autonomous but existing telemetry predominantly
tells operators what executed rather than whether an agent continues to
perform its intended function reliably.

A trace shows that a model was called, a tool ran, and an HTTP 200 came
back. None of that tells an operator whether the agent actually
accomplished the user's task, whether its output was correct, or whether
it stayed within policy. Traditional APM and LLM tracing both stop at
"what happened." Nothing in wide use today systematically answers "is
this agent still doing its job."

## Mission

Create vendor-neutral reliability primitives for operating autonomous
agents, using established SRE ideas — SLOs, error budgets, burn rates —
adapted carefully to probabilistic, evaluation-dependent AI systems.

"Adapted carefully" matters: agent outcomes are not binary HTTP
success/failure, evaluations can be uncertain, and evaluator behavior
itself can drift. A naive transplant of classic SRE math onto agent data
would produce numbers that look precise and mean nothing. Getting the
semantics right — see [DOMAIN_MODEL.md](DOMAIN_MODEL.md) and
[SLO_SEMANTICS.md](SLO_SEMANTICS.md) — is the actual work of this
project, not implementation volume.

## Initial wedge

- Agent SLOs (task success, correctness, policy compliance, tool
  reliability)
- Error budgets
- Burn rates
- Reliability indicators with explicit, documented eligibility and
  UNKNOWN-handling semantics
- Regression detection across agent versions

## Long-term direction

```text
Observe
   ↓
Evaluate
   ↓
Measure reliability
   ↓
Detect degradation
   ↓
Diagnose
   ↓
Recommend
   ↓
Control
```

This project starts at the top of that chain (observe → measure) and
climbs it deliberately, one milestone at a time. See
[ROADMAP.md](ROADMAP.md).

The open-source SDK must remain useful independently of any future
hosted commercial service. Nothing in the core domain, the SDK, or the
telemetry contract may require a paid backend to function. A future
hosted control plane, if it is ever built, is a consumer of this
project's contracts — not the other way around.

## What "done" looks like for the wedge

A developer can define SLOs for an agent, feed it evaluation outcomes
from their own evaluators, and get back a deterministic, mathematically
documented reliability report — with no network calls, no LLM calls, and
no framework lock-in required to do so.

# Agent Reliability

AI agents can finish successfully while still doing the wrong thing. Agent
Reliability provides vendor-neutral Python primitives for measuring whether
agents meet explicit reliability objectives.

It brings evaluations, SLOs, error budgets, burn rates, and measurement
provenance to agent applications—and refuses to produce a misleading number
when evaluation methodologies are incompatible.

**Status: GA (`1.0.0`).** Public APIs documented as stable in
[GA_CONTRACT.md](https://github.com/kamleshd07/agent-reliability/blob/v1.0.0/docs/GA_CONTRACT.md) follow Semantic Versioning.
See [compatibility](https://github.com/kamleshd07/agent-reliability/blob/v1.0.0/docs/COMPATIBILITY.md).

## Why this exists

Traces explain what an agent did. Reliability answers whether it consistently
achieved a defined outcome. Agent Reliability connects one logical execution
to an explicit evaluation method, then calculates exact local reliability
against an SLO.

The OSS package works offline and without a hosted service. It does not
automatically capture prompts, responses, tool arguments, credentials, or
arbitrary application payloads. The base install has no runtime dependencies
and sends nothing over the network.

## 30-second example

```bash
python -m pip install agent-reliability
```

This standalone example instruments four agent-like calls, evaluates
`task_success`, records attributable results, and applies a 75% SLO:

<!-- readme-quickstart-start -->
```python
from fractions import Fraction

from agent_reliability.domain import ObjectiveDirection, Slo, UnknownPolicy
from agent_reliability.evaluation import (
    EqualityEvaluator,
    EvaluationResult,
    EvaluatorIdentity,
)
from agent_reliability.reliability import (
    AggregationConflict,
    ReliabilityObservation,
    evaluate_reliability,
)
from agent_reliability.sdk import AgentReliability, EvaluatorRunner

sdk = AgentReliability()
runner = EvaluatorRunner()
evaluator = EqualityEvaluator(EvaluatorIdentity("expected-answer", "1"), "approved")
observations = []

for actual in ("approved", "approved", "needs-review", "approved"):
    with sdk.run(agent_id="approval-agent", name="Approval Agent", version="1") as run:
        result = runner.evaluate(evaluator, actual)
        if not isinstance(result, EvaluationResult):
            raise RuntimeError("evaluation did not produce an observation")
        run.record_evaluation(indicator="task_success", result=result)
        observations.append(
            ReliabilityObservation.from_evaluation(
                indicator="task_success", result=result
            )
        )

report = evaluate_reliability(
    indicator="task_success",
    observations=observations,
    slo=Slo("task-success", Fraction(3, 4), ObjectiveDirection.AT_LEAST),
    unknown_policy=UnknownPolicy.EXCLUDE,
)
if isinstance(report, AggregationConflict):
    raise RuntimeError("incompatible measurement methodologies")

print(f"Reliability: {float(report.ratio.pass_ratio):.2%}")
print(f"SLO status: {report.slo_evaluation.status.value.upper()}")
```
<!-- readme-quickstart-end -->

Output:

```text
Reliability: 75.00%
SLO status: MET
```

This block runs in CI. The [canonical example](https://github.com/kamleshd07/agent-reliability/blob/main/examples/basic_reliability.py)
also shows the error budget. Follow the [5–10 minute quickstart](https://github.com/kamleshd07/agent-reliability/blob/main/docs/QUICKSTART.md)
for interpretation and next steps.

## What it measures

- An **indicator** says what is measured, such as `task_success`.
- An **evaluator** says how it is judged and returns `PASS`, `FAIL`, or
  `UNKNOWN`.
- **Provenance** records evaluator name, behavior version, configuration, and
  determinism.
- An **SLI** is the observed ratio; an **SLO** is the desired target.
- The **error budget** is permitted unreliability; **burn rate** compares an
  observed bad-event rate with that allowance.

`UNKNOWN` means evaluation completed but was indeterminate. An
`EvaluationExecutionFailure` means the evaluator or its timestamping failed;
it is not an agent failure and creates no observation.

If evaluator v1 and v2 measured the same indicator, the engine returns an
`AggregationConflict` instead of averaging them. A changed measurement method
is not automatically comparable. See [Core concepts](https://github.com/kamleshd07/agent-reliability/blob/main/docs/CONCEPTS.md).

## Installation

Python 3.11–3.13 is supported. The distribution and import names differ:

```text
pip install agent-reliability
import agent_reliability
```

The only optional runtime extra is the OpenTelemetry API bridge:

```bash
python -m pip install "agent-reliability[otel]"
```

## Framework compatibility

Any Python agent can use the explicit sync or async context manager. Wrap one
logical task execution, evaluate the relevant output, and retain observations
for the window your application chooses. No framework adapter, monkey patch,
API key, storage layer, or network service is required. See
[Integrations](https://github.com/kamleshd07/agent-reliability/blob/main/docs/INTEGRATIONS.md) and the [async example](https://github.com/kamleshd07/agent-reliability/blob/main/examples/async_agent.py).

The local engine calculates one supplied collection at a time; it does not
retain history or select rolling windows.

## OpenTelemetry

`OpenTelemetryRunContextBridge` activates the agent span in an existing host
trace. Your application owns the `TracerProvider`, sampling, processors,
propagation, exporter, collector, and backend. Agent Reliability configures
none of them and exports nothing by itself. See the
[OTel example](https://github.com/kamleshd07/agent-reliability/blob/main/examples/opentelemetry_example.py) and
[mapping reference](https://github.com/kamleshd07/agent-reliability/blob/main/docs/OTEL_MAPPING.md).

## Project status and scope

M1–M5 established the domain, sync/async instrumentation, optional OTel
context interoperability, evaluator provenance, and local aggregation. M6 adds
the adoption path and installed-artifact verification. M7 defines the GA
contract and release gates, released as `1.0.0` after `1.0.0rc1` was
published and independently reinstalled from PyPI.

No remote ingestion, dashboard, LLM judge, persistence, auto-instrumentation,
or framework-specific adapter is included. See the [roadmap](https://github.com/kamleshd07/agent-reliability/blob/main/docs/ROADMAP.md).

## Documentation

- New developer: [Quickstart](https://github.com/kamleshd07/agent-reliability/blob/main/docs/QUICKSTART.md) → [Concepts](https://github.com/kamleshd07/agent-reliability/blob/main/docs/CONCEPTS.md)
- Integrator: [Integration guide](https://github.com/kamleshd07/agent-reliability/blob/main/docs/INTEGRATIONS.md)
- Advanced user: [Evaluator framework](https://github.com/kamleshd07/agent-reliability/blob/main/docs/EVALUATOR_FRAMEWORK.md) and
  [local engine](https://github.com/kamleshd07/agent-reliability/blob/main/docs/LOCAL_RELIABILITY_ENGINE.md)
- Architecture reader or contributor: [documentation index](https://github.com/kamleshd07/agent-reliability/blob/main/docs/README.md)

## Development and contributing

See [CONTRIBUTING.md](https://github.com/kamleshd07/agent-reliability/blob/main/CONTRIBUTING.md) for setup and quality gates. Security
vulnerabilities belong in the private process in [SECURITY.md](https://github.com/kamleshd07/agent-reliability/blob/main/SECURITY.md),
not a public issue.

## License

Apache License 2.0. See [LICENSE](https://github.com/kamleshd07/agent-reliability/blob/v1.0.0/LICENSE).

# Quickstart

Get an offline reliability result in about 5–10 minutes. This walkthrough uses
only deterministic fake data: no account, API key, network service, prompt, or
response capture is required.

## 1. Install

Agent Reliability supports Python 3.11–3.13. The distribution name uses a
hyphen; the Python import uses an underscore.

```bash
python -m pip install agent-reliability
```

For a repository checkout, use `python -m pip install -e .` instead.

## 2–5. Instrument, evaluate, define an SLO, and calculate

Run the complete, tested example:

```bash
python examples/basic_reliability.py
```

Read [the canonical source](../examples/basic_reliability.py). Its flow is:

1. `AgentReliability.run(...)` surrounds one logical agent execution.
2. `EqualityEvaluator` judges `task_success`; `EvaluatorRunner` adds the
   evaluator's identity, version, timestamp, and determinism to the result.
3. `run.record_evaluation(...)` emits the reliability outcome for the run.
4. `ReliabilityObservation.from_evaluation(...)` creates the analytical value
   without manually copying provenance.
5. `evaluate_reliability(...)` applies an explicit `UnknownPolicy` and SLO.

The deterministic output is:

```text
Indicator: task_success
Reliability: 75.00%
SLO status: MET
Budget remaining: 0.00%
```

The default event sink discards instrumentation events. The local report is
computed from the observations supplied by your code; the library does not
store history or select rolling windows.

## 6. Interpret the result

Three of four evaluated outcomes passed, so reliability is 75%. The objective
is `>= 75%`, so it is met. Every allowed failure has been used, leaving 0% of
the error budget. All calculations use exact fractions; the example converts
them to percentages only for display.

`PASS` means evaluated and satisfactory, `FAIL` means evaluated and
unsatisfactory, and `UNKNOWN` means evaluation completed but was
indeterminate. An `EvaluationExecutionFailure` instead means the evaluator or
its timestamping failed; it is not an observation and must not be counted as an
agent failure.

## 7. Optional OpenTelemetry

```bash
python -m pip install "agent-reliability[otel]"
python examples/opentelemetry_example.py
```

Agent Reliability activates its run span inside the current trace. Your host
application owns the `TracerProvider`, sampling, processors, exporter, and
collector. The integration sends nothing by itself.

## 8. Where to go next

- Learn the terminology in [Concepts](CONCEPTS.md).
- Adapt the boundaries in [Integrations](INTEGRATIONS.md).
- Try [async usage](../examples/async_agent.py) and the
  [provenance-conflict example](../examples/provenance_conflict.py).
- Consult the [documentation index](README.md) for exact semantics.

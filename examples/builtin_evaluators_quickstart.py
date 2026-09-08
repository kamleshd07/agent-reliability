"""Built-in evaluators end to end: PASS, FAIL, a legitimate UNKNOWN, a report.

Uses two M8 built-in evaluators against the same simulated agent:

- ``ContainsEvaluator`` judges whether the response mentions "refund" — a
  simple, deterministic content check with no UNKNOWN case.
- ``LatencyThresholdEvaluator`` judges whether the response was fast enough
  — and demonstrates a *legitimate* ``UNKNOWN`` when no duration was
  captured for a run (never treated as ``FAIL``).

The printed local report comes from ``agent_reliability.reporting``, which
only renders fields the M1/M5 engine already computed.
"""

from __future__ import annotations

from fractions import Fraction

from agent_reliability.domain import ObjectiveDirection, Slo, UnknownPolicy
from agent_reliability.evaluation import (
    ContainsEvaluator,
    EvaluationExecutionFailure,
    EvaluatorIdentity,
    LatencyThresholdEvaluator,
)
from agent_reliability.reliability import (
    ReliabilityObservation,
    evaluate_reliability_or_raise,
)
from agent_reliability.reporting import format_report
from agent_reliability.sdk import AgentReliability, EvaluatorRunner


def execute_agent(request: str) -> tuple[str, float | None]:
    """Stand-in for a real agent call.

    Returns ``(response_text, duration_seconds)``. ``duration_seconds`` is
    ``None`` for the "timing instrumentation failed to capture a duration"
    case — a deterministic stand-in for missing evidence, not a random
    failure.
    """
    responses: dict[str, tuple[str, float | None]] = {
        "fast": ("Your refund has been approved.", 0.8),
        "slow": ("Your refund has been approved.", 5.0),
        "untimed": ("Your refund has been approved.", None),
    }
    return responses[request]


def build_latency_report():
    sdk = AgentReliability()
    runner = EvaluatorRunner()
    content_evaluator = ContainsEvaluator(
        identity=EvaluatorIdentity("mentions-refund", "1"),
        substring="refund",
        case_sensitive=False,
    )
    latency_evaluator = LatencyThresholdEvaluator(
        identity=EvaluatorIdentity("latency-sla", "1"),
        threshold_seconds=2.0,
    )
    latency_observations: list[ReliabilityObservation] = []

    for request in ("fast", "fast", "slow", "untimed"):
        with sdk.run(
            agent_id="refund-agent", name="Refund Agent", version="1.0"
        ) as run:
            response_text, duration_seconds = execute_agent(request)

            content_result = runner.evaluate(content_evaluator, response_text)
            if isinstance(content_result, EvaluationExecutionFailure):
                raise RuntimeError("content evaluator did not produce an observation")
            run.record_evaluation(indicator="mentions_refund", result=content_result)

            latency_result = runner.evaluate(latency_evaluator, duration_seconds)
            if isinstance(latency_result, EvaluationExecutionFailure):
                raise RuntimeError("latency evaluator did not produce an observation")
            run.record_evaluation(indicator="latency_sla", result=latency_result)
            latency_observations.append(
                ReliabilityObservation.from_evaluation(
                    indicator="latency_sla", result=latency_result
                )
            )

    return evaluate_reliability_or_raise(
        indicator="latency_sla",
        observations=latency_observations,
        slo=Slo("latency-sla", Fraction(1, 2), ObjectiveDirection.AT_LEAST),
        unknown_policy=UnknownPolicy.EXCLUDE,
    )


def main() -> None:
    report = build_latency_report()
    print(format_report(report))


if __name__ == "__main__":
    main()

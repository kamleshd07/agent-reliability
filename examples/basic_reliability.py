"""Canonical offline Agent Reliability workflow."""

from __future__ import annotations

from fractions import Fraction

from agent_reliability.domain import ObjectiveDirection, Slo, UnknownPolicy
from agent_reliability.evaluation import (
    EqualityEvaluator,
    EvaluationExecutionFailure,
    EvaluatorIdentity,
)
from agent_reliability.reliability import (
    AggregationConflict,
    ReliabilityObservation,
    ReliabilityReport,
    evaluate_reliability,
)
from agent_reliability.sdk import AgentReliability, EvaluatorRunner


def execute_agent(request: str) -> str:
    """Stand-in for any agent or framework call."""
    return "approved" if request != "ambiguous" else "needs-review"


def percent(value: Fraction | None) -> str:
    """Presentation-only conversion; core calculations remain exact Fractions."""
    return "undefined" if value is None else f"{float(value):.2%}"


def build_report() -> ReliabilityReport:
    sdk = AgentReliability()
    runner = EvaluatorRunner()
    evaluator = EqualityEvaluator(
        identity=EvaluatorIdentity("expected-answer", "1"),
        expected="approved",
    )
    observations: list[ReliabilityObservation] = []

    for request in ("standard", "standard", "ambiguous", "standard"):
        with sdk.run(
            agent_id="approval-agent",
            name="Approval Agent",
            version="1.0",
        ) as run:
            result = runner.evaluate(evaluator, execute_agent(request))
            if isinstance(result, EvaluationExecutionFailure):
                raise RuntimeError("the evaluator did not produce an observation")
            run.record_evaluation(indicator="task_success", result=result)
            observations.append(
                ReliabilityObservation.from_evaluation(
                    indicator="task_success", result=result
                )
            )

    calculated = evaluate_reliability(
        indicator="task_success",
        observations=observations,
        slo=Slo(
            "task-success",
            Fraction(3, 4),
            ObjectiveDirection.AT_LEAST,
        ),
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    if isinstance(calculated, AggregationConflict):
        raise RuntimeError("observations are not one comparable measurement")
    return calculated


def main() -> None:
    report = build_report()
    print(f"Indicator: {report.indicator}")
    print(f"Reliability: {percent(report.ratio.pass_ratio)}")
    print(f"SLO status: {report.slo_evaluation.status.value.upper()}")
    print(f"Budget remaining: {percent(report.error_budget.remaining_fraction)}")


if __name__ == "__main__":
    main()

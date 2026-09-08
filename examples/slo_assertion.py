"""Aggregate reliability across runs, then assert an SLO from ordinary Python.

Uses ``agent_reliability.testing.assert_slo_met`` — usable from a plain
script (as here), ``unittest``, or ``pytest`` alike, with zero runtime
dependency. This example shows both outcomes: an SLO that is ``MET`` (the
assertion passes silently) and one that is ``BREACHED`` for the same data
(the assertion raises, and we catch it here only to print both outcomes in
one script).
"""

from __future__ import annotations

from fractions import Fraction

from agent_reliability.domain import (
    ObjectiveDirection,
    Slo,
    UnknownPolicy,
)
from agent_reliability.evaluation import (
    EqualityEvaluator,
    EvaluationExecutionFailure,
    EvaluatorIdentity,
)
from agent_reliability.reliability import ReliabilityObservation, evaluate_reliability
from agent_reliability.reporting import format_report
from agent_reliability.sdk import AgentReliability, EvaluatorRunner
from agent_reliability.testing import assert_slo_met


def execute_agent(request: str) -> str:
    """Stand-in for any agent or framework call."""
    return "approved" if request != "ambiguous" else "needs-review"


def collect_observations(requests: list[str]) -> list[ReliabilityObservation]:
    sdk = AgentReliability()
    runner = EvaluatorRunner()
    evaluator = EqualityEvaluator(
        identity=EvaluatorIdentity("expected-answer", "1"), expected="approved"
    )
    observations: list[ReliabilityObservation] = []
    for request in requests:
        with sdk.run(
            agent_id="approval-agent", name="Approval Agent", version="1.0"
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
    return observations


def main() -> None:
    observations = collect_observations(
        ["standard", "standard", "ambiguous", "standard"]
    )

    lenient_slo = Slo("task-success", Fraction(1, 2), ObjectiveDirection.AT_LEAST)
    met_report = evaluate_reliability(
        indicator="task_success",
        observations=observations,
        slo=lenient_slo,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    print(format_report(met_report))
    assert_slo_met(met_report)
    print("SLO assertion passed for the lenient target.")

    strict_slo = Slo("task-success", Fraction(99, 100), ObjectiveDirection.AT_LEAST)
    breached_report = evaluate_reliability(
        indicator="task_success",
        observations=observations,
        slo=strict_slo,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    try:
        assert_slo_met(breached_report)
    except AssertionError as error:
        print(f"SLO assertion failed for the strict target: {error}")


if __name__ == "__main__":
    main()

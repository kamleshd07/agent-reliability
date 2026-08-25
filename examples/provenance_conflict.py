"""Why evaluator versions are not silently averaged."""

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
    evaluate_reliability,
)
from agent_reliability.sdk import EvaluatorRunner


def observation(version: str) -> ReliabilityObservation:
    evaluator = EqualityEvaluator(
        identity=EvaluatorIdentity("expected-answer", version),
        expected="approved",
    )
    result = EvaluatorRunner().evaluate(evaluator, "approved")
    if isinstance(result, EvaluationExecutionFailure):
        raise RuntimeError("the evaluator did not produce an observation")
    return ReliabilityObservation.from_evaluation(
        indicator="task_success", result=result
    )


def main() -> None:
    result = evaluate_reliability(
        indicator="task_success",
        observations=[observation("1"), observation("2")],
        slo=Slo("task-success", Fraction(99, 100), ObjectiveDirection.AT_LEAST),
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    if not isinstance(result, AggregationConflict):
        raise AssertionError("different evaluator versions must not be combined")
    print("Reliability refused: incompatible measurement methodologies")
    for reason in sorted(result.reasons, key=lambda item: item.value):
        print(f"- {reason.value}")


if __name__ == "__main__":
    main()

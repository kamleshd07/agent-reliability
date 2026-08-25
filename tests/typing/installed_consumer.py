"""Representative downstream type-check using only documented public imports."""

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
evaluator = EqualityEvaluator(
    identity=EvaluatorIdentity("typed-example", "1"), expected=True
)

with sdk.run(agent_id="typed-agent", name="Typed Agent", version="1") as run:
    result = runner.evaluate(evaluator, True)
    if not isinstance(result, EvaluationResult):
        raise RuntimeError("evaluation failed")
    run.record_evaluation(indicator="task_success", result=result)
    observation = ReliabilityObservation.from_evaluation(
        indicator="task_success", result=result
    )

report = evaluate_reliability(
    indicator="task_success",
    observations=[observation],
    slo=Slo("task-success", Fraction(1), ObjectiveDirection.AT_LEAST),
    unknown_policy=UnknownPolicy.EXCLUDE,
)
if isinstance(report, AggregationConflict):
    raise RuntimeError("unexpected conflict")
reliability: Fraction | None = report.ratio.pass_ratio

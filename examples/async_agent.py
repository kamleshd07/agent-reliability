"""Concurrent async agent executions with explicit reliability evaluation."""

from __future__ import annotations

import asyncio
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
from agent_reliability.sdk import AgentReliability, EvaluatorRunner

SDK = AgentReliability()
RUNNER = EvaluatorRunner()
EVALUATOR = EqualityEvaluator(
    identity=EvaluatorIdentity("async-result", "1"), expected=True
)


async def execute_agent(succeeds: bool) -> bool:
    await asyncio.sleep(0)
    return succeeds


async def observe(index: int, succeeds: bool) -> ReliabilityObservation:
    async with SDK.run(
        agent_id="async-agent", name="Async Agent", version="1.0"
    ) as run:
        actual = await execute_agent(succeeds)
        result = RUNNER.evaluate(EVALUATOR, actual)
        if isinstance(result, EvaluationExecutionFailure):
            raise RuntimeError("the evaluator did not produce an observation")
        run.record_evaluation(indicator="task_success", result=result)
        return ReliabilityObservation.from_evaluation(
            indicator="task_success", result=result
        )


async def main() -> None:
    observations = await asyncio.gather(
        *(
            observe(index, succeeds)
            for index, succeeds in enumerate((True, True, False))
        )
    )
    report = evaluate_reliability(
        indicator="task_success",
        observations=observations,
        slo=Slo("task-success", Fraction(2, 3), ObjectiveDirection.AT_LEAST),
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    if isinstance(report, AggregationConflict):
        raise RuntimeError("observations are not one comparable measurement")
    print(
        f"Async reliability: {report.ratio.pass_ratio} "
        f"({report.slo_evaluation.status.value.upper()})"
    )


if __name__ == "__main__":
    asyncio.run(main())

from __future__ import annotations

from agent_reliability.evaluation import (
    EvaluationExecutionFailure,
    EvaluationFailureStage,
)
from agent_reliability.measurement import MeasurementHealthReason
from agent_reliability.sdk import AgentReliability
from tests.fakes.clock import FakeClock
from tests.fakes.id_generator import SequentialRunIdGenerator


def test_planted_secret_never_enters_health_repr_or_text() -> None:
    secret = "sk-health-PLANTED-SECRET"
    failure = EvaluationExecutionFailure(
        identity=None,
        stage=EvaluationFailureStage.EVALUATION,
        exception_type="RuntimeError",
    )
    sdk = AgentReliability(
        clock=FakeClock(), run_id_generator=SequentialRunIdGenerator()
    )
    with sdk.run(agent_id="a", name="A", version="1") as run:
        run.record_evaluation_failure(failure=failure)
    rendered = f"{run.measurement_health!r} {run.measurement_health}"
    assert secret not in rendered
    assert "RuntimeError" not in rendered
    assert run.measurement_health.reasons == frozenset(
        {MeasurementHealthReason.EVALUATOR_EXECUTION_FAILURE}
    )

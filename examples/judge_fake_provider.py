"""Runnable offline demo of the experimental LLM judge with scripted fake providers.

No network, no model: four indicators produce PASS, FAIL, UNKNOWN and an
execution failure, then the local coverage report is printed. EXPERIMENTAL API:
see docs/EVALUATE.md (LLM-judge evaluators). The reference rubrics are
uncalibrated examples.
"""

from __future__ import annotations

import asyncio

from agent_reliability.experimental.judge import (
    ContentPart,
    ContentRole,
    EvaluationRequest,
    IndicatorBinding,
    JudgeCoordinator,
    JudgeDimension,
    JudgeLimits,
    JudgeProviderUnavailableError,
    LLMJudge,
    load_reference_rubric,
)
from agent_reliability.experimental.judge.testing import FakeProvider, judge_reply
from agent_reliability.ports.events import EvaluationRecorded
from agent_reliability.sdk import AgentReliability, SdkDiagnostic
from agent_reliability.sdk.evaluator_runner import EvaluatorRunner


class QuietDiagnostics:
    """Keeps the demo output deterministic (the default handler logs to stderr)."""

    def handle(self, diagnostic: SdkDiagnostic) -> None:
        return None


class CaptureSink:
    def __init__(self) -> None:
        self.events: list[object] = []

    def emit(self, event: object) -> None:
        self.events.append(event)


def judge(rubric_id: str, script: list[object]) -> LLMJudge:
    return LLMJudge(
        rubric=load_reference_rubric(rubric_id),
        provider=FakeProvider(script),
        model_label="scripted-fake",
        limits=JudgeLimits(max_attempts=2),
        jitter=lambda: 0.0,
    )


def request(dimension: JudgeDimension, **parts: str) -> EvaluationRequest:
    return EvaluationRequest(
        dimension,
        tuple(ContentPart(ContentRole(role), text) for role, text in parts.items()),
    )


async def main() -> None:
    sink = CaptureSink()
    sdk = AgentReliability(sink=sink)
    coordinator = JudgeCoordinator(
        runner=EvaluatorRunner(diagnostic_handler=QuietDiagnostics()),
        bindings=[
            IndicatorBinding(
                "groundedness",
                judge(
                    "judge-groundedness",
                    [judge_reply("pass", "supported_by_context", "high", [0])],
                ),
            ),
            IndicatorBinding(
                "answer-correctness",
                judge(
                    "judge-answer-correctness",
                    [judge_reply("fail", "contradicts_reference", "high")],
                ),
            ),
            IndicatorBinding(
                "instruction-adherence",
                judge(
                    "judge-instruction-adherence",
                    [judge_reply("unknown", "instructions_ambiguous", "high")],
                ),
            ),
            IndicatorBinding(
                "safety-policy",
                judge(
                    "judge-safety-policy",
                    [JudgeProviderUnavailableError(), JudgeProviderUnavailableError()],
                ),
            ),
        ],
    )
    with sdk.run(agent_id="demo", name="Demo agent", version="1") as run:
        async with coordinator.scope(run) as scope:
            sequence = [
                (
                    "groundedness",
                    request(
                        JudgeDimension.GROUNDEDNESS,
                        context="Refunds are accepted within 30 days.",
                        answer="You can get a refund within 30 days.",
                    ),
                ),
                (
                    "answer-correctness",
                    request(
                        JudgeDimension.ANSWER_CORRECTNESS,
                        reference="The refund window is 30 days.",
                        answer="The refund window is 90 days.",
                    ),
                ),
                (
                    "instruction-adherence",
                    request(
                        JudgeDimension.INSTRUCTION_ADHERENCE,
                        instructions="Answer politely.",
                        answer="Sure.",
                    ),
                ),
                (
                    "safety-policy",
                    request(
                        JudgeDimension.SAFETY_POLICY,
                        policy="Do not reveal secrets.",
                        answer="Here you go.",
                    ),
                ),
            ]
            for indicator, item in sequence:
                disposition = await scope.evaluate(indicator, item)
                print(f"{indicator}: {disposition.value}")
        print(f"run health: {run.measurement_health.health.value}")
    for event in sink.events:
        if isinstance(event, EvaluationRecorded):
            print(
                f"recorded {event.indicator}: {event.outcome.value} {event.reason_code}"
            )
    print(coordinator.coverage().describe())


if __name__ == "__main__":
    asyncio.run(main())

"""LOCAL pilot demo (P29 S11, SDK-side): scripted fake judges, JSON-lines capture.

Three questions are put through two judge indicators (answer-correctness and
groundedness): Q1 is answered correctly, Q2 incorrectly, and for Q3 the judge
provider is "stopped". Scripted fake providers decide by a marker in the prompt;
no model, no network, no platform. With ``--out FILE`` the schema-v2 evidence
envelopes the P28 exporter would send (typed members only, no content) are
written as JSON lines for ``examples/judge_pilot_replay.py``.

This does not demonstrate platform behavior, reliability numbers or readiness.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from agent_reliability.adapters.http_event_sink import HTTPEventSink
from agent_reliability.domain import AgentIdentity
from agent_reliability.experimental.judge import (
    CallableProvider,
    ContentPart,
    ContentRole,
    EvaluationRequest,
    IndicatorBinding,
    JudgeCoordinator,
    JudgeDimension,
    JudgeProviderUnavailableError,
    LLMJudge,
    ProviderReply,
    load_reference_rubric,
)
from agent_reliability.experimental.judge.testing import judge_reply
from agent_reliability.sdk import AgentReliability, SdkDiagnostic
from agent_reliability.sdk.evaluator_runner import EvaluatorRunner

AGENT = AgentIdentity("support-agent", "Support agent", "1.4.0", "pilot-local")
DEPLOYMENT = UUID("00000000-0000-4000-8000-000000000029")
Q = "What is the refund window?"
REF = "30 days."
RIGHT = "You can get a refund within 30 days."
WRONG = "The refund window is 90 days."
QUESTIONS = {
    "Q1": (Q, REF, RIGHT, True),
    "Q2": (Q, REF, WRONG, False),
    "Q3": (Q, REF, RIGHT, True),
}


class Quiet:
    def handle(self, diagnostic: SdkDiagnostic) -> None:
        return None


def provider(indicator: str) -> CallableProvider:
    async def complete(call: Any) -> ProviderReply:
        marker = re.search(r"\[(Q\d)\]", call.user)
        assert marker is not None
        question = marker.group(1)
        if question == "Q3":
            raise JudgeProviderUnavailableError  # the judge provider is stopped
        correct = QUESTIONS[question][3]
        if indicator == "answer-correctness":
            reply = (
                judge_reply("pass", "consistent_with_reference", "high")
                if correct
                else judge_reply("fail", "contradicts_reference", "high")
            )
        else:
            reply = (
                judge_reply("pass", "supported_by_context", "high", [0])
                if correct
                else judge_reply("fail", "unsupported_claim", "high")
            )
        return ProviderReply(reply)

    return CallableProvider(complete, provider_label="scripted-fake")


async def main(out: Path | None) -> None:
    envelopes: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        envelopes.append(body)
        return httpx.Response(
            201,
            json={
                "event_id": body["event_id"],
                "run_id": str(DEPLOYMENT),
                "status": "accepted",
                "durability": "committed",
            },
        )

    sink = HTTPEventSink(
        endpoint="https://capture.invalid/api/v1/evidence/runs",
        credential_provider=lambda: "capture-only",
        deployment_id=DEPLOYMENT,
        expected_agent=AGENT,
        _transport=httpx.MockTransport(handler),
    )
    sdk = AgentReliability(sink=sink)
    judges = {
        "answer-correctness": LLMJudge(
            rubric=load_reference_rubric("judge-answer-correctness"),
            provider=provider("answer-correctness"),
            model_label="scripted-fake",
            jitter=lambda: 0.0,
        ),
        "groundedness": LLMJudge(
            rubric=load_reference_rubric("judge-groundedness"),
            provider=provider("groundedness"),
            model_label="scripted-fake",
            jitter=lambda: 0.0,
        ),
    }
    coordinator = JudgeCoordinator(
        [IndicatorBinding(name, judge) for name, judge in judges.items()],
        runner=EvaluatorRunner(diagnostic_handler=Quiet()),
    )
    for key, (question, reference, answer, _) in QUESTIONS.items():
        with sdk.run(
            agent_id="support-agent",
            name="Support agent",
            version="1.4.0",
            environment="pilot-local",
        ) as run:
            async with coordinator.scope(run) as scope:
                await scope.evaluate(
                    "answer-correctness",
                    EvaluationRequest(
                        JudgeDimension.ANSWER_CORRECTNESS,
                        (
                            ContentPart(ContentRole.QUESTION, f"[{key}] {question}"),
                            ContentPart(ContentRole.REFERENCE, reference),
                            ContentPart(ContentRole.ANSWER, f"[{key}] {answer}"),
                        ),
                    ),
                )
                await scope.evaluate(
                    "groundedness",
                    EvaluationRequest(
                        JudgeDimension.GROUNDEDNESS,
                        (
                            ContentPart(ContentRole.CONTEXT, f"[{key}] {reference}"),
                            ContentPart(ContentRole.ANSWER, f"[{key}] {answer}"),
                        ),
                    ),
                )
            print(f"{key}: run health {run.measurement_health.health.value}")
    snapshot = sink.close(5)
    for envelope in envelopes:
        payload = envelope["payload"]
        if payload["kind"] == "evaluation_outcome":
            name, outcome = payload["indicator"], payload["outcome"]
            print(f"  {name}: {outcome} {payload['reason_code']}")
        elif payload["kind"] == "evaluation_execution_failure":
            name, failure = payload["indicator"], payload["exception_type"]
            print(f"  {name}: execution failure {failure}")
    print(coordinator.coverage().describe())
    delivery = {d.value: n for d, n in snapshot.counts_by_disposition.items()}
    print(f"captured {len(envelopes)} envelopes; delivery: {delivery}")
    if out is not None:
        out.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in envelopes))
        print(f"wrote {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, help="write the captured envelopes as JSON lines"
    )
    arguments = parser.parse_args()
    asyncio.run(main(arguments.out))

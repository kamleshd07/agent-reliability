# ruff: noqa: E501 -- long strings and narrative lines read best unbroken.
"""Developer quickstart: define a semantic check, execute an agent, evaluate, send bounded evidence, inspect reliability.

Offline and deterministic: the judge provider is a scripted fake and the sink only captures events. EXPERIMENTAL API (docs/SEMANTIC_EVALUATION.md).
To use a real model, replace ``FakeSyncProvider`` with your own provider object (see examples/judge_providers.py) and
``CaptureSink`` with ``HTTPEventSink`` (docs/HTTP_EXPORTER.md).

    python examples/semantic_quickstart.py
"""

from __future__ import annotations

from agent_reliability.experimental.judge import SemanticChecks
from agent_reliability.experimental.judge.testing import FakeSyncProvider, judge_reply
from agent_reliability.ports.events import EvaluationRecorded
from agent_reliability.sdk import AgentReliability

CATALOG = "Aster kettle: price Rs 1,999; capacity 1.2 litre."


def my_agent(
    question: str,
) -> str:  # 1. your agent (here: a stub that answers wrongly on purpose for the second question)
    return (
        "The Aster kettle costs Rs 1,999."
        if "price" in question
        else "It holds 2 litres."
    )


class CaptureSink:
    def __init__(self) -> None:
        self.events: list[object] = []

    def emit(self, event: object) -> None:
        self.events.append(event)


def price_is_exact(
    answer: str,
) -> bool:  # a DETERMINISTIC check stays authoritative where one exists
    return "Rs 1,999" in answer


def main() -> None:
    provider = FakeSyncProvider(  # 2. your judge (scripted here; a real provider object in production)
        [
            judge_reply("pass", "supported_by_context", "high", [0]),
            judge_reply("fail", "contradicted_by_context", "high", [0]),
        ]
    )
    checks = SemanticChecks(
        provider, model_label="scripted-fake", checks=("groundedness",)
    )
    sink = CaptureSink()  # 3. where bounded evidence goes (HTTPEventSink in production)
    sdk = AgentReliability(sink=sink)
    for question in ("What is the kettle price?", "What is the kettle capacity?"):
        answer = my_agent(question)
        with sdk.run(agent_id="kettle-bot", name="Kettle bot", version="1.0") as run:
            with checks.scope(run) as scope:  # 4. evaluate the actual result
                verdict = scope.check(
                    "groundedness", answer, context=[CATALOG], question=question
                )
            if "price" in question:
                print("deterministic price check:", price_is_exact(answer))
        print(
            question,
            "->",
            verdict.status.value,
            verdict.outcome.value,
            verdict.reason_code,
            f"(authoritative={verdict.authoritative})",
        )
    recorded = [e for e in sink.events if isinstance(e, EvaluationRecorded)]
    print(
        "evidence events:",
        len(recorded),
        "- indicator, outcome, evaluator identity and a closed reason code only",
    )
    print(checks.coverage())  # 5. read failure/UNKNOWN rates beside reliability


if __name__ == "__main__":
    main()

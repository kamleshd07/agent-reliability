"""Observe a real LangChain agent: where time went, which tools ran, what failed.

Install: pip install 'agent-reliability[langchain,http]' langchain
The default run is offline (a scripted tool-calling model, no provider call). Set
GENTLITY_BASE_URL, GENTLITY_DEPLOYMENT_ID and GENTLITY_MACHINE_TOKEN to also deliver the
content-free execution facts and the explicit check below to a Gentlity deployment.
Prompts, answers, tool arguments and results are never sent.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool

from agent_reliability.adapters.event_sinks import InMemoryEventSink
from agent_reliability.domain import EvaluationOutcome
from agent_reliability.experimental.instrumentation import (
    ExecutionSummary,
    instrument,
)
from agent_reliability.sdk import AgentReliability, current_run

ANSWER_LOOKS_GROUNDED = "answer-uses-tool-result"


@tool
def order_status(order_id: str) -> str:
    """Return the synthetic status of an order."""
    return "shipped"


class ScriptedToolCallingModel(GenericFakeChatModel):
    """Offline stand-in for a tool-calling chat model."""

    def bind_tools(self, tools: Sequence[Any], **_: Any) -> Any:
        return self


def scripted_model() -> ScriptedToolCallingModel:
    call = {"name": "order_status", "args": {"order_id": "A-1"}, "id": "call-1"}
    usage = {"input_tokens": 21, "output_tokens": 9, "total_tokens": 30}
    return ScriptedToolCallingModel(
        messages=iter(
            [
                AIMessage(content="", tool_calls=[call], usage_metadata=usage),
                AIMessage(content="Your order has shipped.", usage_metadata=usage),
            ]
        )
    )


def main() -> ExecutionSummary:
    base_url = os.environ.get("GENTLITY_BASE_URL")
    exporter = sink = None
    if base_url:
        from agent_reliability.adapters.http_event_sink import HTTPEventSink
        from agent_reliability.adapters.http_execution_exporter import (
            ExecutionHTTPExporter,
        )
        from agent_reliability.domain import AgentIdentity

        deployment = UUID(os.environ["GENTLITY_DEPLOYMENT_ID"])
        token = lambda: os.environ["GENTLITY_MACHINE_TOKEN"]  # noqa: E731
        identity = AgentIdentity("order-agent", "order-agent", "1", "production")
        sink = HTTPEventSink(
            endpoint=f"{base_url}/api/v1/evidence/runs",
            credential_provider=token,
            deployment_id=deployment,
            expected_agent=identity,
            indicator_allowlist=[ANSWER_LOOKS_GROUNDED],
        )
        exporter = ExecutionHTTPExporter(
            base_url=base_url, credential_provider=token, deployment_id=deployment
        )
    agent = create_agent(scripted_model(), tools=[order_status])

    def run_and_check(question: str) -> dict[str, Any]:
        result = agent.invoke({"messages": [("user", question)]})
        answer = str(result["messages"][-1].content)
        run = current_run()
        if run is not None:  # explicit, deterministic, application-owned check
            run.record(
                indicator=ANSWER_LOOKS_GROUNDED,
                outcome=EvaluationOutcome.PASS
                if "shipped" in answer
                else EvaluationOutcome.FAIL,
            )
        return result

    observed = instrument(
        RunnableLambda(run_and_check),
        sdk=AgentReliability(sink=sink or InMemoryEventSink()),
        agent_id="order-agent",
        name="order-agent",
        version="1",
        environment="production",
        tool_names=("order_status",),
        tool_classes={"order_status": "data_store"},
        tool_actions={"order_status": "read"},
        model_id="scripted-model",
        exporter=exporter,
    )
    observed.invoke("Where is order A-1?")
    summary = observed.traces[-1].summary()
    for row in summary.components:
        print(
            f"{row.kind:<6} {row.component or '-':<16} calls={row.calls} "
            f"failed={row.failed} total_ms={row.total_duration_ns / 1e6:.2f}"
        )
    print(f"tokens={summary.total_tokens} complete={summary.complete}")
    if exporter is not None and sink is not None:
        print(exporter.close(10))
        print(sink.close(10))
    return summary


if __name__ == "__main__":
    main()

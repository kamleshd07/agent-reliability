"""Offline experimental LangChain example; no provider or network calls.

Install the optional extra: pip install 'agent-reliability[langchain]'
"""

from __future__ import annotations

import asyncio
from itertools import repeat

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool

from agent_reliability.adapters.event_sinks import InMemoryEventSink
from agent_reliability.evaluation import (
    EqualityEvaluator,
    EvaluationExecutionFailure,
    EvaluatorIdentity,
)
from agent_reliability.experimental.instrumentation import instrument
from agent_reliability.ports.events import EvaluationRecorded
from agent_reliability.sdk import AgentReliability, EvaluatorRunner, current_run


@tool
def lookup(query: str) -> str:
    """Return a fixed synthetic lookup result."""
    return "synthetic context"


def main() -> None:
    # A small, deliberately retained test sink; use a bounded sink for long-lived apps.
    sink = InMemoryEventSink()
    sdk = AgentReliability(sink=sink)
    model = GenericFakeChatModel(messages=repeat(AIMessage(content="approved")))
    chain = RunnableLambda(lambda value: lookup.invoke(value)) | model
    observed = instrument(
        chain,
        sdk=sdk,
        agent_id="support",
        name="Support",
        version="1",
        tool_names=("lookup",),
        model_id="offline-fake",
        provider_id="local",
    )
    observed.invoke("synthetic request")
    trace = observed.traces[-1]
    assert trace.tool_calls == 1 and trace.model_invocations == 1
    assert not any(isinstance(e, EvaluationRecorded) for e in sink.events)
    print("Execution completed; outcome reliability has not been measured.")
    asyncio.run(observed.ainvoke("synthetic async request"))

    evaluator = EqualityEvaluator(
        identity=EvaluatorIdentity("expected-answer", "1"), expected="approved"
    )

    def explicitly_evaluate(message: AIMessage) -> AIMessage:
        run = current_run()
        assert run is not None
        # The application chooses the indicator, evaluator and expected answer.
        result = EvaluatorRunner().evaluate(evaluator, message.content)
        if isinstance(result, EvaluationExecutionFailure):
            run.record_evaluation_failure(failure=result, indicator="task_success")
        else:
            run.record_evaluation(indicator="task_success", result=result)
        return message

    measured = instrument(
        chain | RunnableLambda(explicitly_evaluate),
        sdk=sdk,
        agent_id="support",
        name="Support",
        version="1",
        tool_names=("lookup",),
    )
    measured.invoke("synthetic evaluated request")
    evaluations = [e for e in sink.events if isinstance(e, EvaluationRecorded)]
    assert len(evaluations) == 1 and evaluations[0].provenance is not None
    print("One explicit outcome evaluation recorded; execution did not manufacture it.")
    observed.disable()
    observed.close()
    measured.close()


if __name__ == "__main__":
    main()

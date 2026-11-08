"""The real-agent example runs offline and exports only content-free facts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("langchain.agents")

from agent_reliability.adapters.http_execution_exporter import ExecutionHTTPExporter
from agent_reliability.experimental.instrumentation import build_requests

pytestmark = pytest.mark.integration
PATH = Path(__file__).parents[2] / "examples" / "langchain_agent_observability.py"


def load():
    spec = importlib.util.spec_from_file_location("lc_agent_example", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_example_reports_tools_models_tokens_offline(monkeypatch, capsys):
    monkeypatch.delenv("GENTLITY_BASE_URL", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    summary = load().main()
    by = {(c.kind, c.component): c for c in summary.components}
    assert by[("tool", "order_status")].calls == 1
    assert by[("model", "scripted-model")].calls == 2
    assert (
        summary.total_tokens == 60 and summary.complete and summary.state == "completed"
    )
    assert "Where is order" not in capsys.readouterr().out


def test_real_agent_export_contains_no_prompt_answer_or_tool_data():
    module = load()
    from uuid import UUID

    from langchain.agents import create_agent

    from agent_reliability.adapters.event_sinks import InMemoryEventSink
    from agent_reliability.experimental.instrumentation import instrument
    from agent_reliability.sdk import AgentReliability

    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(201, json={"status": "accepted"})

    exporter = ExecutionHTTPExporter(
        base_url="http://127.0.0.1:9",
        credential_provider=lambda: "t",
        deployment_id=UUID(int=1),
        _transport=httpx.MockTransport(handler),
    )
    agent = create_agent(module.scripted_model(), tools=[module.order_status])
    observed = instrument(
        agent,
        sdk=AgentReliability(sink=InMemoryEventSink()),
        agent_id="order-agent",
        name="order-agent",
        version="1",
        tool_names=("order_status",),
        exporter=exporter,
    )
    observed.invoke({"messages": [("user", "PRIVATE-QUESTION A-1")]})
    exporter.flush(5)
    wire = b"".join(r.content for r in sent).decode()
    for secret in ("PRIVATE-QUESTION", "A-1", "shipped", "Your order", "call-1"):
        assert secret not in wire
    assert sent and all(json.loads(r.content)["producer_run_id"] for r in sent)
    exporter.close(1)
    assert build_requests(observed.traces[0], deployment_id=str(UUID(int=1)))

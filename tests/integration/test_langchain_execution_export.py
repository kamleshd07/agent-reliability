"""LangChain execution export: real Runnables, tools, fake chat models; mock HTTP."""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
import time
from uuid import UUID

import httpx
import pytest

pytest.importorskip("langchain_core")
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool

from agent_reliability.adapters._http_delivery import ConfigurationError
from agent_reliability.adapters.event_sinks import InMemoryEventSink
from agent_reliability.adapters.http_execution_exporter import ExecutionHTTPExporter
from agent_reliability.experimental.instrumentation import CaptureLimits, instrument
from agent_reliability.sdk import AgentReliability

pytestmark = pytest.mark.integration
DEPLOYMENT = UUID("11111111-1111-4111-8111-111111111111")
SECRET = "PRIVATE-SENTINEL-4f9c"


@pytest.fixture(autouse=True)
def no_tracing(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")


class Platform:
    """In-process stand-in answering the documented acknowledgements."""

    def __init__(self, script=None):
        self.requests: list[httpx.Request] = []
        self.script = list(script or [])
        self.lock = threading.Lock()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        with self.lock:
            self.requests.append(request)
            if self.script:
                step = self.script.pop(0)
                if isinstance(step, Exception):
                    raise step
                if step is not None:
                    return step
        return httpx.Response(201, json={"status": "accepted"})

    def bodies(self, path):
        return [
            json.loads(r.content) for r in self.requests if r.url.path.endswith(path)
        ]


def exporter(platform, **kwargs):
    return ExecutionHTTPExporter(
        base_url="http://127.0.0.1:9",
        credential_provider=lambda: "token-not-printed",
        deployment_id=DEPLOYMENT,
        _transport=httpx.MockTransport(platform),
        **kwargs,
    )


def wrap(runnable, exp, **kwargs):
    return instrument(
        runnable,
        sdk=AgentReliability(sink=InMemoryEventSink()),
        agent_id="support-agent",
        name="Support",
        version="1",
        exporter=exp,
        **kwargs,
    )


@tool
def lookup(query: str) -> str:
    """Synthetic lookup."""
    return f"result for {query}"


@tool
def broken(query: str) -> str:
    """Always times out."""
    raise TimeoutError(SECRET)


def agentish(value):
    lookup.invoke(value)
    with contextlib.suppress(TimeoutError):
        broken.invoke(value)
    return value


def model():
    message = AIMessage(
        content=SECRET,
        usage_metadata={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
    )
    return GenericFakeChatModel(messages=iter([message]))


def test_sync_run_exports_structure_tools_outcomes_and_usage_without_content():
    platform = Platform()
    exp = exporter(platform)
    chain = RunnableLambda(lambda v: (model().invoke(v), agentish(v))[1])
    wrapper = wrap(
        chain,
        exp,
        tool_names=("lookup", "broken"),
        tool_classes={"lookup": "retrieval"},
        tool_actions={"lookup": "read"},
        model_id="fake-model",
    )
    assert wrapper.invoke(SECRET) == SECRET
    status = exp.flush(5)
    assert status.delivered_jobs == 1 and status.failed_jobs == 0
    (structure,) = platform.bodies("/execution-structures/batches")
    kinds = sorted(s["step_type"] for s in structure["steps"])
    assert kinds.count("tool") == 2 and kinds.count("model") == 1
    (classes,) = platform.bodies("/execution-classifications/batches")
    assert sorted(a["execution_outcome"] for a in classes["assertions"]) == [
        "success",
        "timeout",
    ]
    (usage,) = platform.bodies("/execution-model-usage/batches")
    assert usage["assertions"][0]["total_tokens"] == 10
    wire = b"".join(r.content for r in platform.requests).decode()
    assert SECRET not in wire and "token-not-printed" not in wire
    assert all(
        r.headers["authorization"] == "Bearer token-not-printed"
        for r in platform.requests
    )
    assert structure["producer_run_id"] == wrapper.traces[0].run_id
    exp.close(1)


def test_unreachable_platform_never_blocks_or_fails_the_application():
    platform = Platform([httpx.ConnectError("boom")] * 20)
    exp = exporter(platform, retry_max_attempts=2)
    wrapper = wrap(RunnableLambda(lambda v: v), exp)
    started = time.monotonic()
    assert wrapper.invoke("x") == "x"
    assert time.monotonic() - started < 1.0  # submit never performs HTTP on the caller
    status = exp.flush(15)
    assert status.failed_jobs == 1 and status.retry_exhausted == 1
    assert status.last_error == "network"
    exp.close(1)


def test_retry_after_transient_error_then_success_and_identical_bytes():
    platform = Platform([httpx.Response(503, headers={"retry-after": "0"})])
    exp = exporter(platform)
    wrapper = wrap(RunnableLambda(lambda v: v), exp)
    wrapper.invoke("x")
    status = exp.flush(10)
    assert status.delivered_jobs == 1 and status.retries == 1
    assert platform.requests[0].content == platform.requests[1].content
    exp.close(1)


def test_permanent_rejection_is_not_retried_and_skips_rest_of_job():
    platform = Platform([httpx.Response(403, json={"error": SECRET})])
    exp = exporter(platform)
    wrapper = wrap(
        RunnableLambda(lambda v: model().invoke(v)), exp, model_id="fake-model"
    )
    wrapper.invoke("x")
    status = exp.flush(5)
    assert status.failed_jobs == 1 and status.requests_rejected == 1
    assert len(platform.requests) == 1 and status.last_error == "http_403"
    assert SECRET not in repr(status)
    exp.close(1)


def test_duplicate_acknowledgement_counts_as_duplicate():
    platform = Platform([httpx.Response(200, json={"status": "duplicate"})])
    exp = exporter(platform)
    wrap(RunnableLambda(lambda v: v), exp).invoke("x")
    status = exp.flush(5)
    assert status.requests_duplicate == 1 and status.delivered_jobs == 1
    exp.close(1)


def test_unparseable_acknowledgement_is_not_success():
    platform = Platform([httpx.Response(201, content=b"<html>")])
    exp = exporter(platform)
    wrap(RunnableLambda(lambda v: v), exp).invoke("x")
    status = exp.flush(5)
    assert status.failed_jobs == 1 and status.last_error == "bad_acknowledgement"
    exp.close(1)


def test_bounded_queue_drops_new_jobs_with_visible_counter():
    gate = threading.Event()

    def slow(request):
        gate.wait(5)
        return httpx.Response(201, json={"status": "accepted"})

    exp = ExecutionHTTPExporter(
        base_url="http://127.0.0.1:9",
        credential_provider=lambda: "t",
        deployment_id=DEPLOYMENT,
        max_queue_jobs=2,
        _transport=httpx.MockTransport(slow),
    )
    wrapper = wrap(RunnableLambda(lambda v: v), exp)
    for _ in range(6):
        wrapper.invoke("x")
    status = exp.status
    assert status.dropped_queue_full >= 3
    gate.set()
    exp.close(5)


def test_close_abandons_unsent_jobs_and_counts_them():
    gate = threading.Event()
    exp = ExecutionHTTPExporter(
        base_url="http://127.0.0.1:9",
        credential_provider=lambda: "t",
        deployment_id=DEPLOYMENT,
        _transport=httpx.MockTransport(
            lambda r: (gate.wait(3), httpx.Response(201, json={"status": "accepted"}))[
                1
            ]
        ),
    )
    wrapper = wrap(RunnableLambda(lambda v: v), exp)
    for _ in range(3):
        wrapper.invoke("x")
    status = exp.close(0.2)
    assert status.closed and status.abandoned_jobs >= 1
    gate.set()
    assert exp.submit(wrapper.traces[0]) is False


def test_credential_provider_failure_is_a_fixed_label():
    def provider():
        raise RuntimeError(SECRET)

    exp = ExecutionHTTPExporter(
        base_url="http://127.0.0.1:9",
        credential_provider=provider,
        deployment_id=DEPLOYMENT,
        _transport=httpx.MockTransport(Platform()),
    )
    wrap(RunnableLambda(lambda v: v), exp).invoke("x")
    status = exp.flush(5)
    assert status.last_error == "credential_unavailable" and SECRET not in repr(status)
    exp.close(1)


def test_exporter_that_raises_is_isolated_and_counted():
    class Raising:
        def submit(self, trace):
            raise RuntimeError(SECRET)

    wrapper = wrap(RunnableLambda(lambda v: v), Raising())
    assert wrapper.invoke("x") == "x"
    assert wrapper.status.export_failures == 1
    assert len(wrapper.traces) == 1  # local trace unaffected


def test_application_exception_still_propagates_and_failed_run_is_exported():
    platform = Platform()
    exp = exporter(platform)

    def fail(_):
        raise ValueError(SECRET)

    wrapper = wrap(RunnableLambda(fail), exp)
    with pytest.raises(ValueError):
        wrapper.invoke("x")
    exp.flush(5)
    (structure,) = platform.bodies("/execution-structures/batches")
    assert structure["steps"][0]["state"] == "failed"
    assert SECRET not in b"".join(r.content for r in platform.requests).decode()
    exp.close(1)


def test_async_cancellation_exports_cancelled_state():
    platform = Platform()
    exp = exporter(platform)

    async def sleeper(_):
        await asyncio.sleep(30)

    wrapper = wrap(RunnableLambda(sleeper), exp)

    async def main():
        task = asyncio.create_task(wrapper.ainvoke("x"))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())
    exp.flush(5)
    (structure,) = platform.bodies("/execution-structures/batches")
    assert "cancelled" in {s["state"] for s in structure["steps"]}
    exp.close(1)


def test_concurrent_async_runs_have_no_cross_attribution():
    platform = Platform()
    exp = exporter(platform)

    async def work(value):
        await asyncio.sleep(0.01)
        await lookup.ainvoke(value)
        return value

    wrapper = wrap(RunnableLambda(work), exp, tool_names=("lookup",))

    async def main():
        await asyncio.gather(*(wrapper.ainvoke(f"v{i}") for i in range(25)))

    asyncio.run(main())
    exp.flush(10)
    structures = platform.bodies("/execution-structures/batches")
    assert len(structures) == 25
    assert len({b["producer_run_id"] for b in structures}) == 25
    ids = [s["step_id"] for b in structures for s in b["steps"]]
    assert len(ids) == len(set(ids))  # no span shared between runs
    for batch in structures:
        local = {s["step_id"] for s in batch["steps"]}
        assert all(s["parent_step_id"] in local | {None} for s in batch["steps"])
        assert sum(s["step_type"] == "tool" for s in batch["steps"]) == 1
    exp.close(2)


def test_threaded_concurrent_runs_have_no_cross_attribution():
    platform = Platform()
    exp = exporter(platform)
    wrapper = wrap(RunnableLambda(lambda v: lookup.invoke(v)), exp)
    threads = [
        threading.Thread(target=wrapper.invoke, args=(f"v{i}",)) for i in range(20)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    exp.flush(10)
    structures = platform.bodies("/execution-structures/batches")
    assert len({b["producer_run_id"] for b in structures}) == 20
    exp.close(2)


def test_missing_usage_is_not_exported_as_zero():
    platform = Platform()
    exp = exporter(platform)
    silent = GenericFakeChatModel(messages=iter([AIMessage(content="hi")]))
    wrap(RunnableLambda(lambda v: silent.invoke(v)), exp, model_id="m").invoke("x")
    exp.flush(5)
    assert platform.bodies("/execution-model-usage/batches") == []
    exp.close(1)


def test_unsupported_tool_classes_are_rejected_at_setup():
    base = RunnableLambda(lambda v: v)
    for kwargs in (
        {"tool_names": ("a",), "tool_classes": {"a": "not-a-class"}},
        {"tool_names": ("a",), "tool_classes": {"b": "retrieval"}},
        {"tool_names": ("a",), "tool_actions": {"a": SECRET}},
    ):
        with pytest.raises(ValueError) as exc:
            wrap(base, None, **kwargs)
        assert SECRET not in str(exc.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://example.com/api/v1",
        "https://user:pw@example.com",
        "ftp://example.com",
        "",
    ],
)
def test_exporter_refuses_unsafe_base_urls(url):
    with pytest.raises(ConfigurationError):
        ExecutionHTTPExporter(
            base_url=url,
            credential_provider=lambda: "t",
            deployment_id=DEPLOYMENT,
        )


def test_sampling_zero_exports_nothing():
    platform = Platform()
    exp = exporter(platform)
    wrap(RunnableLambda(lambda v: v), exp, sample_rate=0).invoke("x")
    assert exp.flush(1).submitted_jobs == 0 and platform.requests == []
    exp.close(1)


def test_depth_and_span_limits_hold_for_exported_nested_chains():
    platform = Platform()
    exp = exporter(platform)
    chain = RunnableLambda(lambda v: v)
    for _ in range(30):
        chain = chain | RunnableLambda(lambda v: v)
    wrap(chain, exp, limits=CaptureLimits(max_spans=40)).invoke("x")
    exp.flush(5)
    steps = [
        s for b in platform.bodies("/execution-structures/batches") for s in b["steps"]
    ]
    assert 1 <= len(steps) <= 40
    exp.close(1)

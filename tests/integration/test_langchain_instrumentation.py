from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

pytest.importorskip("langchain_core")
from langchain_core.callbacks import BaseCallbackHandler, CallbackManager
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool

from agent_reliability.adapters.event_sinks import InMemoryEventSink
from agent_reliability.adapters.langchain_instrumentation import _Handler
from agent_reliability.domain import EvaluationOutcome, RunStatus
from agent_reliability.domain.measurement_health import MeasurementHealthReason
from agent_reliability.experimental.instrumentation import CaptureLimits, instrument
from agent_reliability.ports.events import (
    EvaluationRecorded,
    RunCompleted,
    RunFailed,
    RunStarted,
)
from agent_reliability.sdk import AgentReliability, current_run

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def no_third_party_tracing(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")


def wrapped(runnable, **kwargs):
    sink = InMemoryEventSink()
    return instrument(
        runnable,
        sdk=AgentReliability(sink=sink),
        agent_id="support-agent",
        name="Support",
        version="1",
        **kwargs,
    ), sink


@tool
def lookup(query: str) -> str:
    """Synthetic offline lookup."""
    return query


class CountCallbacks(BaseCallbackHandler):
    def __init__(self):
        self.starts = []

    def on_chain_start(self, serialized, inputs, **kwargs):
        self.starts.append(kwargs["run_id"])


def test_sync_run_tools_order_privacy_and_original_result_identity():
    payload = {"private-prompt": "prompt-secret"}
    target = RunnableLambda(lambda value: lookup.invoke(json.dumps(value)) and value)
    wrapper, sink = wrapped(target)
    assert wrapper.invoke(payload) is payload
    t = wrapper.traces[0]
    assert t.complete and t.tool_calls == 1
    assert current_run() is None
    assert [type(e) for e in sink.events] == [RunStarted, RunCompleted]
    assert "prompt-secret" not in repr(t) and "lookup" not in repr(t)
    assert all(e.component is None for e in t.events)
    assert [e.sequence for e in t.events] == list(range(1, len(t.events) + 1))
    starts = {e.span_id for e in t.events if e.phase == "start"}
    assert all(e.parent_span_id is None or e.parent_span_id in starts for e in t.events)
    assert not any(isinstance(e, EvaluationRecorded) for e in sink.events)


def test_approved_tool_alias_and_preserved_existing_callback_config():
    callback = CountCallbacks()
    manager = CallbackManager([callback], inheritable_handlers=[callback])
    root = uuid4()
    config = {
        "callbacks": manager,
        "run_id": root,
        "run_name": "user-name",
        "metadata": {"private": "metadata-secret"},
        "tags": ["private-tag"],
    }
    wrapper, _ = wrapped(
        RunnableLambda(lambda x: lookup.invoke(x)), tool_names=("lookup",)
    )
    assert wrapper.invoke("tool-result-secret", config) == "tool-result-secret"
    assert callback.starts == [root]
    assert manager.handlers == [callback] and manager.inheritable_handlers == [callback]
    assert config["run_id"] is root and config["run_name"] == "user-name"
    assert config["metadata"] == {"private": "metadata-secret"}
    assert "metadata-secret" not in repr(wrapper.traces)
    assert (
        next(e for e in wrapper.traces[0].events if e.kind == "tool").component
        == "lookup"
    )


@pytest.mark.parametrize("reported", [True, False])
def test_real_fake_chat_model_token_metadata(reported):
    msg = AIMessage(
        content="model-response-secret",
        usage_metadata={"total_tokens": 5, "input_tokens": 3, "output_tokens": 2}
        if reported
        else None,
    )
    model = GenericFakeChatModel(messages=iter([msg]))
    wrapper, sink = wrapped(model, provider_id="local", model_id="fake-model")
    assert wrapper.invoke("prompt-secret").content == "model-response-secret"
    trace = wrapper.traces[0]
    assert trace.model_invocations == 1 and trace.complete
    end = next(e for e in trace.events if e.kind == "model" and e.phase == "terminal")
    assert end.provider_id == "local" and end.model_id == "fake-model"
    assert end.usage.availability == ("reported" if reported else "unknown")
    assert end.usage.total_tokens == (5 if reported else None)
    assert "model-response-secret" not in repr(trace) + repr(sink.events)


def test_explicit_evaluations_remain_explicit_and_unknown_stays_unknown():
    def business(value):
        run = current_run()
        assert run is not None
        run.record(indicator="task_success", outcome=EvaluationOutcome.UNKNOWN)
        return value

    wrapper, sink = wrapped(RunnableLambda(business))
    wrapper.invoke("response")
    evaluations = [e for e in sink.events if isinstance(e, EvaluationRecorded)]
    assert len(evaluations) == 1 and evaluations[0].outcome is EvaluationOutcome.UNKNOWN
    assert evaluations[0].run_id == wrapper.traces[0].run_id
    assert evaluations[0].provenance is None  # no manufactured evaluator identity


def test_nested_wrappers_have_separate_sdk_identity_and_no_tool_double_count():
    child, child_sink = wrapped(RunnableLambda(lambda x: lookup.invoke(x)))
    parent, _ = wrapped(RunnableLambda(lambda x: child.invoke(x)))
    assert parent.invoke("value") == "value"
    outer, inner = parent.traces[0], child.traces[0]
    assert inner.parent_run_id == outer.run_id
    assert outer.tool_calls == 0 and inner.tool_calls == 1
    assert outer.complete and inner.complete
    assert (
        next(e for e in child_sink.events if isinstance(e, RunStarted)).parent_run_id
        == outer.run_id
    )


async def test_concurrent_async_calls_keep_task_context_and_trace_isolation():
    async def business(value):
        before = current_run().run_id
        await asyncio.sleep(0)
        assert current_run().run_id == before
        await lookup.ainvoke(value)
        return value

    wrapper, _ = wrapped(
        RunnableLambda(business), limits=CaptureLimits(max_retained_runs=32)
    )
    assert await asyncio.gather(*(wrapper.ainvoke(str(i)) for i in range(16))) == [
        str(i) for i in range(16)
    ]
    assert len(wrapper.traces) == 16
    assert len({t.run_id for t in wrapper.traces}) == 16
    assert all(t.complete and t.tool_calls == 1 for t in wrapper.traces)
    assert wrapper.status.active_runs == 0 and current_run() is None


async def test_cancellation_preserves_exception_and_closes_lifecycle():
    entered = asyncio.Event()

    async def business(_):
        entered.set()
        await asyncio.Event().wait()

    wrapper, sink = wrapped(RunnableLambda(business))
    task = asyncio.create_task(wrapper.ainvoke(None))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert wrapper.status.active_runs == 0
    assert wrapper.traces[0].events[-1].state == "cancelled"
    assert (
        next(e for e in sink.events if isinstance(e, RunFailed)).status
        is RunStatus.CANCELLED
    )
    assert current_run() is None


def test_original_exception_object_is_preserved_but_class_name_not_exported(caplog):
    SecretCustomerException = type("private_customer_secret", (Exception,), {})
    original = SecretCustomerException("private-message-secret")

    def business(_):
        raise original

    wrapper, sink = wrapped(RunnableLambda(business))
    with pytest.raises(SecretCustomerException) as exc:
        wrapper.invoke("prompt-secret")
    assert exc.value is original
    assert wrapper.traces[0].events[-1].state == "failed"
    assert (
        "private_customer_secret"
        not in repr(wrapper.traces) + repr(sink.events) + caplog.text
    )
    assert (
        "private-message-secret"
        not in repr(wrapper.traces) + repr(sink.events) + caplog.text
    )


def test_framework_retry_has_one_logical_sdk_run_and_distinct_attempt_spans():
    calls = []

    def business(value):
        calls.append(value)
        if len(calls) == 1:
            raise ValueError("synthetic retry")
        return value

    target = RunnableLambda(business).with_retry(
        stop_after_attempt=2, wait_exponential_jitter=False
    )
    wrapper, sink = wrapped(target)
    assert wrapper.invoke("value") == "value" and len(calls) == 2
    assert sum(isinstance(e, RunStarted) for e in sink.events) == 1
    terminals = [
        e
        for e in wrapper.traces[0].events
        if e.kind == "step" and e.phase == "terminal"
    ]
    assert len(terminals) == 3 and sum(e.state == "failed" for e in terminals) == 1


def test_enable_disable_and_repeated_initialization_are_explicit():
    seen = []
    wrapper, sink = wrapped(RunnableLambda(lambda x: seen.append(x) or x))
    with pytest.raises(ValueError):
        instrument(wrapper, sdk=AgentReliability(), agent_id="a", name="a", version="1")
    wrapper.disable()
    wrapper.disable()
    payload = {"identity": True}
    assert wrapper.invoke(payload) is payload and sink.events == []
    wrapper.enable()
    wrapper.enable()
    wrapper.invoke(payload)
    assert len(wrapper.traces) == 1 and len(seen) == 2
    wrapper.close()
    wrapper.close()
    wrapper.invoke(payload)
    assert wrapper.traces == () and len(seen) == 3
    with pytest.raises(RuntimeError):
        wrapper.enable()


async def test_admission_bounds_and_close_during_active_call():
    entered, finish = asyncio.Event(), asyncio.Event()

    async def business(x):
        if x == "first":
            entered.set()
            await finish.wait()
        return x

    wrapper, _ = wrapped(
        RunnableLambda(business), limits=CaptureLimits(max_active_runs=1)
    )
    first = asyncio.create_task(wrapper.ainvoke("first"))
    await entered.wait()
    assert await wrapper.ainvoke("second") == "second"
    assert wrapper.status.admission_dropped == 1
    wrapper.close()
    finish.set()
    assert await first == "first" and wrapper.traces == ()
    assert wrapper.status.active_runs == 0


def test_zero_sampling_and_bounded_retention():
    wrapper, sink = wrapped(RunnableLambda(lambda x: x), sample_rate=0)
    assert (
        wrapper.invoke(42) == 42 and sink.events == [] and wrapper.status.unsampled == 1
    )
    retained, _ = wrapped(
        RunnableLambda(lambda x: x), limits=CaptureLimits(max_retained_runs=2)
    )
    for i in range(5):
        retained.invoke(i)
    assert len(retained.traces) == 2 and retained.status.completed == 5


def test_callback_fault_is_contained_before_framework_logging_and_health_is_partial(
    monkeypatch, caplog
):
    from agent_reliability.experimental.instrumentation.collector import Collector

    handles = []

    def business(value):
        handles.append(current_run())
        return value

    def broken(*args, **kwargs):
        raise ValueError("callback-secret-payload")

    monkeypatch.setattr(Collector, "start", broken)
    wrapper, _ = wrapped(RunnableLambda(business))
    assert wrapper.invoke("input-secret") == "input-secret"
    assert "callback-secret-payload" not in caplog.text + repr(wrapper.traces)
    assert wrapper.traces[0].diagnostics.callback_errors == 1
    assert (
        MeasurementHealthReason.PARTIAL_EVIDENCE
        in handles[0].measurement_health.reasons
    )


def test_callback_duplicate_and_partial_events_do_not_duplicate_counts():
    from agent_reliability.experimental.instrumentation.collector import Collector

    root = uuid4()
    c = Collector(str(uuid4()), None, root, CaptureLimits(), None, None)
    handler = _Handler(c, frozenset())
    handler.on_chat_model_start(None, object(), run_id=root)
    handler.on_chat_model_start(None, object(), run_id=root)
    handler.on_llm_end(None, run_id=root)
    handler.on_llm_end(None, run_id=root)
    handler.on_retry(object(), run_id=root)
    t = c.finish("completed")
    assert (
        t.model_invocations == 1
        and t.diagnostics.duplicates == 2
        and t.diagnostics.retry_signals == 1
    )
    assert t.complete


def test_runtime_setup_failure_does_not_retry_or_break_business(monkeypatch):
    calls, handles = [], []

    def business(value):
        calls.append(value)
        handles.append(current_run())
        return value

    wrapper, _ = wrapped(RunnableLambda(business))
    monkeypatch.setattr(
        wrapper._adapter,
        "callback_config",
        lambda *a: (_ for _ in ()).throw(ValueError("private-setup-error")),
    )
    assert wrapper.invoke(1) == 1 and calls == [1]
    assert (
        MeasurementHealthReason.PARTIAL_EVIDENCE
        in handles[0].measurement_health.reasons
    )
    assert wrapper.status.failures == 1 and wrapper.status.active_runs == 0


def test_threaded_independent_calls_do_not_leak_context():
    wrapper, _ = wrapped(
        RunnableLambda(lambda x: lookup.invoke(x)),
        limits=CaptureLimits(max_retained_runs=32),
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(wrapper.invoke, map(str, range(20)))) == list(
            map(str, range(20))
        )
    assert len(wrapper.traces) == 20 and all(t.complete for t in wrapper.traces)
    assert len({t.run_id for t in wrapper.traces}) == 20


@pytest.mark.parametrize(
    "options",
    [
        {"agent_id": "secret/path"},
        {"name": "not safe"},
        {"version": "x" * 129},
        {"provider_id": "private/key"},
        {"model_id": "a/b"},
        {"tool_names": tuple(str(i) for i in range(513))},
        {"sample_rate": True},
        {"sample_rate": float("nan")},
    ],
)
def test_bad_configuration_is_rejected_before_business(options):
    values = {"agent_id": "a", "name": "a", "version": "1", "sdk": AgentReliability()}
    values.update(options)
    with pytest.raises((TypeError, ValueError)):
        instrument(RunnableLambda(lambda x: pytest.fail("must not execute")), **values)


def test_partial_capture_health_is_submitted_through_existing_http_schema_only():
    import httpx

    from agent_reliability.adapters.http_event_sink import HTTPEventSink
    from agent_reliability.domain import AgentIdentity

    bodies = []

    def receive(request):
        body = json.loads(request.content)
        bodies.append(body)
        return httpx.Response(
            201,
            json={
                "event_id": body["event_id"],
                "run_id": str(uuid4()),
                "status": "accepted",
                "durability": "committed",
            },
        )

    agent = AgentIdentity("support-agent", "Support", "1", "test")
    sink = HTTPEventSink(
        endpoint="https://platform.example/api/v1/evidence/runs",
        credential_provider=lambda: "synthetic-credential",
        deployment_id=uuid4(),
        expected_agent=agent,
        indicator_allowlist=("task_success",),
        _transport=httpx.MockTransport(receive),
    )

    def business(value):
        lookup.invoke(value)
        current_run().record(
            indicator="task_success", outcome=EvaluationOutcome.UNKNOWN
        )
        return value

    wrapper = instrument(
        RunnableLambda(business),
        sdk=AgentReliability(sink=sink),
        agent_id="support-agent",
        name="Support",
        version="1",
        limits=CaptureLimits(max_spans=1),
        environment="test",
    )
    try:
        assert wrapper.invoke("raw-secret-content") == "raw-secret-content"
        status = sink.flush(2)
        assert status.counts_by_disposition["committed"] == 4
    finally:
        sink.close(0)
    payloads = [b["payload"] for b in bodies]
    assert {b["kind"] for b in payloads} == {
        "run_lifecycle",
        "evaluation_outcome",
        "measurement_health",
    }
    assert all(b["schema_version"] == 2 for b in bodies)
    assert "raw-secret-content" not in json.dumps(bodies)
    health = next(b for b in payloads if b["kind"] == "measurement_health")
    assert "partial_evidence" in json.dumps(health)
    evaluation = next(b for b in payloads if b["kind"] == "evaluation_outcome")
    assert evaluation["outcome"] == "unknown"
    assert not wrapper.traces[0].complete


def test_chat_start_never_uses_prompt_conversion_even_when_collector_fails(
    monkeypatch, caplog
):
    import langchain_core.callbacks.manager as manager_module

    from agent_reliability.experimental.instrumentation.collector import Collector

    def forbidden(*args, **kwargs):
        raise AssertionError("must never stringify private messages")

    monkeypatch.setattr(manager_module, "get_buffer_string", forbidden)
    root = uuid4()
    collector = Collector(str(uuid4()), None, root, CaptureLimits(), None, None)
    handler = _Handler(collector, frozenset())
    handler.on_chat_model_start(object(), object(), run_id=root)
    handler.on_llm_error(ValueError("private-exception"), run_id=root)
    trace = collector.finish("failed")
    assert trace.model_invocations == 1
    assert "private-exception" not in caplog.text + repr(trace)


def test_callback_manager_nested_wrapper_preserves_user_handlers():
    callback = CountCallbacks()
    child, _ = wrapped(RunnableLambda(lambda x: lookup.invoke(x)))
    parent, _ = wrapped(RunnableLambda(lambda x: child.invoke(x)))
    config = {
        "callbacks": [callback],
        "tags": ["tag"],
        "metadata": {"private": "sentinel"},
    }
    before = (list(config["callbacks"]), list(config["tags"]), dict(config["metadata"]))
    assert parent.invoke("x", config) == "x"
    assert len(callback.starts) == 2
    assert (config["callbacks"], config["tags"], config["metadata"]) == before
    assert parent.traces[0].complete and child.traces[0].complete


@pytest.mark.parametrize(
    "usage,expected",
    [
        ({"total_tokens": 0, "input_tokens": 0, "output_tokens": 0}, 0),
        ({"total_tokens": -1}, None),
        ({"total_tokens": True}, None),
        ({"total_tokens": 2**63}, None),
        ({"input_tokens": 5}, None),
        ({"total_tokens": 5, "input_tokens": "secret"}, None),
    ],
)
def test_only_exact_bounded_reported_usage_is_accepted(usage, expected):
    from langchain_core.outputs import ChatGeneration, LLMResult

    from agent_reliability.adapters.langchain_instrumentation import _usage

    message = AIMessage.model_construct(
        content="private-response", usage_metadata=usage
    )
    response = LLMResult(generations=[[ChatGeneration(message=message)]])
    result = _usage(response)
    assert result.total_tokens == expected
    assert result.availability == ("reported" if expected is not None else "unknown")


def test_ambiguous_usage_is_unknown_and_legacy_numeric_usage_is_supported():
    from langchain_core.outputs import Generation, LLMResult

    from agent_reliability.adapters.langchain_instrumentation import _usage

    one = Generation(text="private")
    tokens = {
        "token_usage": {"total_tokens": 9, "prompt_tokens": 4, "completion_tokens": 5}
    }
    assert _usage(LLMResult(generations=[[one]], llm_output=tokens)).total_tokens == 9
    assert (
        _usage(LLMResult(generations=[[one, one]], llm_output=tokens)).total_tokens
        is None
    )


async def test_async_disable_preserves_result_and_config():
    calls = []

    async def business(value):
        calls.append(current_run())
        return value

    wrapper, sink = wrapped(RunnableLambda(business))
    wrapper.disable()
    payload = object()
    assert await wrapper.ainvoke(payload) is payload
    assert calls == [None] and sink.events == []


def test_sdk_failure_and_collector_finish_failure_preserve_application(monkeypatch):
    from agent_reliability.experimental.instrumentation.collector import Collector
    from tests.fakes.clock import BrokenClock

    sink = InMemoryEventSink()
    wrapper = instrument(
        RunnableLambda(lambda x: x),
        sdk=AgentReliability(sink=sink, clock=BrokenClock()),
        agent_id="a",
        name="a",
        version="1",
    )
    assert wrapper.invoke(1) == 1 and wrapper.status.active_runs == 0
    assert wrapper.traces == () and sink.events == []
    handles = []
    target, _ = wrapped(RunnableLambda(lambda x: handles.append(current_run()) or x))

    def broken(*args):
        raise ValueError("sensitive-finish-error")

    monkeypatch.setattr(Collector, "finish", broken)
    assert target.invoke(2) == 2 and current_run() is None
    assert (
        MeasurementHealthReason.PARTIAL_EVIDENCE
        in handles[0].measurement_health.reasons
    )
    assert target.status.failures == 1


def test_wrong_terminal_kind_closed_parent_and_conflicting_starts_are_partial():
    from agent_reliability.experimental.instrumentation.collector import Collector

    root, child = uuid4(), uuid4()
    c = Collector(str(uuid4()), None, root, CaptureLimits(), None, None)
    handler = _Handler(c, frozenset())
    handler.on_tool_start(None, object(), run_id=root)
    handler.on_llm_end(None, run_id=root)
    assert c._spans[root].closed is False
    handler.on_chain_start(None, object(), run_id=root)  # conflicting duplicate kind
    handler.on_tool_end(object(), run_id=root)
    handler.on_tool_start(None, object(), run_id=child, parent_run_id=root)
    t = c.finish("completed")
    assert (
        not t.complete
        and t.diagnostics.callback_errors == 2
        and t.diagnostics.orphans == 1
    )
    assert t.tool_calls == 1 and t.model_invocations == 0


def test_setup_enable_disable_never_patch_framework_or_change_tracing_environment(
    monkeypatch,
):
    import os

    from langchain_core.runnables import Runnable

    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    before = dict(os.environ)
    invoke = RunnableLambda.invoke
    ainvoke = RunnableLambda.ainvoke
    base_invoke = Runnable.invoke
    runnable = RunnableLambda(lambda x: x)
    wrapper, _ = wrapped(runnable)
    wrapper.disable()
    wrapper.enable()
    wrapper.close()
    assert RunnableLambda.invoke is invoke and RunnableLambda.ainvoke is ainvoke
    assert Runnable.invoke is base_invoke and dict(os.environ) == before


@pytest.mark.parametrize("signal", [SystemExit(37), KeyboardInterrupt()])
def test_application_exit_signals_are_preserved_without_context_leak(signal):
    def business(_):
        raise signal

    wrapper, sink = wrapped(RunnableLambda(business))
    with pytest.raises(type(signal)) as raised:
        wrapper.invoke(None)
    assert raised.value is signal
    assert wrapper.status.active_runs == 0 and current_run() is None
    assert wrapper.traces[-1].events[-1].state == "failed"
    assert isinstance(sink.events[-1], RunFailed)


def test_abrupt_process_termination_does_not_fabricate_terminal_evidence():
    import subprocess
    import sys

    probe = """
import os, signal
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
from langchain_core.runnables import RunnableLambda
from agent_reliability.experimental.instrumentation import instrument
from agent_reliability.sdk import AgentReliability
class Sink:
    def emit(self, event):
        print(type(event).__name__, flush=True)
def terminated(_):
    os.kill(os.getpid(), signal.SIGTERM)
instrument(RunnableLambda(terminated), sdk=AgentReliability(sink=Sink()),
           agent_id="a", name="a", version="1").invoke(None)
"""
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=10
    )
    assert result.returncode != 0
    assert result.stdout.splitlines() == ["RunStarted"]


def test_intermediate_sampling_is_reproducible_and_outcome_independent():
    first, first_sink = wrapped(RunnableLambda(lambda x: x), sample_rate=0.5)
    second, second_sink = wrapped(RunnableLambda(lambda x: x), sample_rate=0.5)
    for i in range(30):
        first.invoke(i)
        second.invoke(30 - i)
    assert 0 < first.status.admitted < 30
    assert first.status.admitted == second.status.admitted
    assert first.status.unsampled == second.status.unsampled
    assert (
        len(first_sink.events) == len(second_sink.events) == 2 * first.status.admitted
    )

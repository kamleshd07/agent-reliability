"""P20c M3 local detection spike: explicit retry links from a verified RunnableRetry.

Local-only evidence (no wire contract). Tags are untrusted: only the exact framework
marker is parsed, only from direct children of a verified retry wrapper.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest

pytest.importorskip("langchain_core")
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.retry import RunnableRetry
from langchain_core.tools import tool

from agent_reliability.adapters import langchain_instrumentation as adapter
from agent_reliability.adapters.event_sinks import InMemoryEventSink
from agent_reliability.experimental.instrumentation import CaptureLimits, instrument
from agent_reliability.experimental.instrumentation.collector import Collector
from agent_reliability.experimental.instrumentation.export import build_requests
from agent_reliability.sdk import AgentReliability

pytestmark = pytest.mark.integration
SENTINEL = "PRIVATE-SENTINEL-7c1e"
DEPLOYMENT = "11111111-1111-4111-8111-111111111111"
FAST = {"wait_exponential_jitter": False}


@pytest.fixture(autouse=True)
def no_tracing(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")


def wrapped(runnable, **kwargs):
    sink = InMemoryEventSink()
    return (
        instrument(
            runnable,
            sdk=AgentReliability(sink=sink),
            agent_id="support-agent",
            name="Support",
            version="1",
            **kwargs,
        ),
        sink,
    )


def failing(times, counter=None):
    state = {"n": 0}

    def business(value):
        state["n"] += 1
        if state["n"] <= times:
            raise ValueError(SENTINEL)
        return value

    return business, state


def children(trace):
    """Attempt span ids in start order under the root wrapper span."""
    root = next(e for e in trace.events if e.kind == "step").span_id
    return [
        e.span_id
        for e in trace.events
        if e.phase == "start" and e.parent_span_id == root
    ]


def test_recovered_after_two_failures_links_2_to_1_and_3_to_2():
    business, state = failing(2)
    w, _ = wrapped(RunnableLambda(business).with_retry(stop_after_attempt=4, **FAST))
    assert w.invoke("v") == "v" and state["n"] == 3
    t = w.traces[0]
    a1, a2, a3 = children(t)
    assert t.retry_observation == "observed" and t.retry_attempts == 3
    assert t.retry_links == ((a2, a1), (a3, a2))
    assert t.summary().retry_observation == "observed"
    assert t.summary().retry_link_count == 2


def test_exhausted_retries_still_link_attempts_and_propagate_error():
    business, state = failing(99)
    w, _ = wrapped(RunnableLambda(business).with_retry(stop_after_attempt=3, **FAST))
    with pytest.raises(ValueError):
        w.invoke("v")
    t = w.traces[0]
    a1, a2, a3 = children(t)
    assert t.retry_observation == "observed" and state["n"] == 3
    assert t.retry_links == ((a2, a1), (a3, a2))


def test_success_without_retry_is_observed_with_no_links():
    w, _ = wrapped(RunnableLambda(lambda v: v).with_retry(**FAST))
    w.invoke("v")
    t = w.traces[0]
    assert (t.retry_observation, t.retry_links, t.retry_attempts) == ("observed", (), 1)


def test_tool_with_retry_with_approved_alias():
    state = {"n": 0}

    @tool
    def lookup(x: int) -> int:
        """Look up."""
        state["n"] += 1
        if state["n"] < 3:
            raise ConnectionError(SENTINEL)
        return x

    w, _ = wrapped(
        lookup.with_retry(stop_after_attempt=3, **FAST), tool_names=["lookup"]
    )
    assert w.invoke({"x": 1}) == 1
    t = w.traces[0]
    a1, a2, a3 = children(t)
    assert t.retry_links == ((a2, a1), (a3, a2))
    assert {
        e.component for e in t.events if e.kind == "tool" and e.phase == "start"
    } == {"lookup"}


def test_tool_with_retry_unapproved_alias_cannot_corroborate_component():
    state = {"n": 0}

    @tool
    def lookup(x: int) -> int:
        """Look up."""
        state["n"] += 1
        if state["n"] < 2:
            raise ConnectionError("x")
        return x

    w, _ = wrapped(lookup.with_retry(stop_after_attempt=3, **FAST))
    w.invoke({"x": 1})
    t = w.traces[0]
    assert (t.retry_observation, t.retry_links) == ("unknown", ())


def test_async_retry_links():
    business, _state = failing(1)

    async def run():
        w, _ = wrapped(
            RunnableLambda(business).with_retry(stop_after_attempt=3, **FAST)
        )
        assert await w.ainvoke("v") == "v"
        return w.traces[0]

    t = asyncio.run(run())
    a1, a2 = children(t)
    assert t.retry_links == ((a2, a1),) and t.retry_observation == "observed"


def test_concurrent_threads_and_tasks_do_not_cross_attribute():
    lock = threading.Lock()
    seen: dict[str, int] = {}

    def business(value):
        with lock:
            seen[value] = seen.get(value, 0) + 1
            n = seen[value]
        if n <= int(value):
            raise ValueError("x")
        return value

    w, _ = wrapped(
        RunnableLambda(business).with_retry(stop_after_attempt=5, **FAST),
        limits=CaptureLimits(max_retained_runs=32),
    )
    with ThreadPoolExecutor(6) as pool:
        list(pool.map(w.invoke, ["0", "1", "2", "3"] * 2))

    async def many():
        await asyncio.gather(*(w.ainvoke(v) for v in ["0", "1", "2", "3"]))

    seen.clear()
    asyncio.run(many())
    traces = w.traces
    assert len(traces) == 12
    for t in traces:
        spans = {e.span_id for e in t.events}
        kids = children(t)
        assert t.retry_observation == "observed"
        assert len(t.retry_links) == len(kids) - 1
        assert all(a in spans and b in spans for a, b in t.retry_links)
        assert [b for _, b in t.retry_links] == kids[:-1]
    assert sorted(len(t.retry_links) for t in traces[-4:]) == [0, 1, 2, 3]


# -- spoofing and non-corroborated contexts -------------------------------------------


def spy_on_tags(monkeypatch):
    calls = []
    real = adapter.retry_attempt

    def spy(tags):
        calls.append(1)
        return real(tags)

    monkeypatch.setattr(adapter, "retry_attempt", spy)
    return calls


def test_spoofed_tag_on_standalone_runnable_is_not_a_retry_and_never_read(monkeypatch):
    calls = spy_on_tags(monkeypatch)
    target = RunnableLambda(lambda v: v).with_config(tags=["retry:attempt:2"])
    w, _ = wrapped(target)
    w.invoke("v")
    t = w.traces[0]
    assert (t.retry_observation, t.retry_links, t.retry_attempts) == (
        "not_collected",
        (),
        0,
    )
    assert calls == []


def test_spoofed_tag_under_non_retry_parent_and_nested_retry_not_collected(
    monkeypatch,
):
    calls = spy_on_tags(monkeypatch)
    inner = RunnableLambda(lambda v: v).with_config(tags=["retry:attempt:2"])
    seq = inner | RunnableLambda(lambda v: v)
    nested = RunnableLambda(lambda v: v).with_retry(**FAST) | RunnableLambda(
        lambda v: v
    )
    for target in (seq, nested):
        w, _ = wrapped(target)
        w.invoke("v")
        t = w.traces[0]
        assert (t.retry_observation, t.retry_links) == ("not_collected", ())
    assert calls == []


def test_user_tag_on_first_attempt_inside_verified_wrapper_is_unknown():
    inner = RunnableLambda(lambda v: v).with_config(tags=["retry:attempt:2"])
    w, _ = wrapped(RunnableRetry(bound=inner, **FAST))
    w.invoke("v")
    t = w.traces[0]
    assert (t.retry_observation, t.retry_links) == ("unknown", ())


def test_binding_wrapped_retry_is_not_a_verified_wrapper():
    # with_config() on the input makes RunnableBinding(RunnableRetry): not trusted.
    inner = RunnableLambda(lambda v: v)
    w, _ = wrapped(inner.with_retry(**FAST).with_config(tags=["x"]))
    w.invoke("v")
    assert w.traces[0].retry_observation == "not_collected"


def test_user_tag_colliding_with_framework_tag_is_unknown():
    business, _ = failing(1)
    inner = RunnableLambda(business).with_config(tags=["retry:attempt:7"])
    w, _ = wrapped(RunnableRetry(bound=inner, max_attempt_number=3, **FAST))
    w.invoke("v")
    t = w.traces[0]
    assert (t.retry_observation, t.retry_links) == ("unknown", ())


def test_tag_lookalikes_in_metadata_only_are_not_read():
    business, _ = failing(1)
    meta = {"metadata": {"k": "retry:attempt:2", "retry:attempt:2": "retry:attempt:2"}}
    w, _ = wrapped(RunnableLambda(business).with_retry(stop_after_attempt=3, **FAST))
    w.invoke("v", config=meta)
    # Framework tag is still honored (it is a tag); metadata plays no part.
    assert w.traces[0].retry_observation == "observed"
    plain, _ = wrapped(
        RunnableLambda(lambda v: v).with_config(metadata=meta["metadata"])
    )
    plain.invoke("v")
    assert plain.traces[0].retry_observation == "not_collected"


@pytest.mark.parametrize("n", [2, 3, 10, 100])
def test_retry_attempt_accepts_only_bounded_index(n):
    assert adapter.retry_attempt([f"retry:attempt:{n}"]) == n


@pytest.mark.parametrize(
    "tag",
    [
        "retry:attempt:0",
        "retry:attempt:1",  # the framework never tags the first attempt
        "retry:attempt:101",
        "retry:attempt:999",
        "retry:attempt:99999",
        "retry:attempt:2 ",
        " retry:attempt:2",
        "retry:attempt:2\n",
        "retry:attempt:02",
        "retry:attempt:٢",  # Arabic-indic digit
        "retry:attempt:\uff12",  # full-width digit
        "retry:attempt:-2",
        "retry:attempt:2.0",
        "retry:attempt:2:x",
        "RETRY:ATTEMPT:2",
        "retry:attempt:",
        "x" * 5000,
        b"retry:attempt:2",
        7,
        None,
    ],
)
def test_retry_attempt_rejects_every_out_of_range_or_lookalike_tag(tag):
    result = adapter.retry_attempt([tag])
    assert result is None or result == 0
    assert not (isinstance(result, int) and result >= 1)


def test_retry_attempt_rejects_ambiguous_or_huge_tag_collections():
    assert adapter.retry_attempt(["retry:attempt:2", "retry:attempt:3"]) == 0
    assert adapter.retry_attempt(["retry:attempt:2", "retry:attempt:2"]) == 0
    assert adapter.retry_attempt(("retry:attempt:2",)) == 0
    assert adapter.retry_attempt(["a"] * 100 + ["retry:attempt:2"]) == 0
    assert adapter.retry_attempt(["seq:step:1", "retry:attempt:5"]) == 5
    assert adapter.retry_attempt([]) is None and adapter.retry_attempt(None) is None


def test_malformed_markers_under_verified_wrapper_become_unknown():
    for bad in ("retry:attempt:02", "retry:attempt:٢", "retry:attempt:101"):
        c = Collector("r", None, UUID(int=1), CaptureLimits(), None, None, None, True)
        _simulate(c, [(None, "failed"), (0 if bad else None, "completed")])
        t = c.finish("completed")
        assert (t.retry_observation, t.retry_links) == ("unknown", ())


# -- corroboration rules at collector level (synthetic callback sequences) ------------


ROOT = UUID(int=1)


def _simulate(c, plan, kind="step", components=None, overlap=False):
    """plan: [(attempt, final_state)] for direct children of the root wrapper."""
    c.start(ROOT, None, "step")
    keys = []
    for i, (attempt, state) in enumerate(plan):
        key = uuid4()
        keys.append(key)
        comp = components[i] if components else None
        c.start(key, ROOT, kind, comp, attempt)
        if not overlap:
            c.end(key, state)
    if overlap:
        for key, (_, state) in zip(keys, plan, strict=True):
            c.end(key, state)
    c.end(ROOT, "completed")
    return keys


def collect(plan, **kw):
    c = Collector("r", None, ROOT, CaptureLimits(), None, None, None, True)
    _simulate(c, plan, **kw)
    return c.finish("completed")


def test_collector_good_sequence():
    t = collect([(None, "failed"), (2, "failed"), (3, "completed")])
    assert t.retry_observation == "observed" and len(t.retry_links) == 2


@pytest.mark.parametrize(
    "plan",
    [
        [(None, "failed"), (3, "completed")],  # missing predecessor / gap
        [(None, "failed"), (2, "failed"), (2, "completed")],  # duplicate
        [(None, "failed"), (3, "failed"), (2, "completed")],  # not increasing
        [(2, "failed"), (3, "completed")],  # first attempt carries a marker
        [(None, "failed"), (None, "completed")],  # later attempt without marker
        [(None, "completed"), (2, "completed")],  # previous did not fail
        [(None, "cancelled"), (2, "completed")],  # previous cancelled
        [(None, "failed"), (0, "completed")],  # unusable marker
        [],  # no attempts
    ],
)
def test_collector_rejects_uncorroborated_sequences(plan):
    t = collect(plan)
    assert (t.retry_observation, t.retry_links) == ("unknown", ())


def test_collector_rejects_overlapping_attempts():
    t = collect([(None, "failed"), (2, "completed")], overlap=True)
    assert (t.retry_observation, t.retry_links) == ("unknown", ())


def test_collector_rejects_mismatching_components_and_unnamed_tools():
    t = collect(
        [(None, "failed"), (2, "completed")], kind="tool", components=["a", "b"]
    )
    assert (t.retry_observation, t.retry_links) == ("unknown", ())
    t = collect(
        [(None, "failed"), (2, "completed")], kind="tool", components=[None, None]
    )
    assert t.retry_observation == "unknown"
    t = collect(
        [(None, "failed"), (2, "completed")], kind="tool", components=["a", "a"]
    )
    assert t.retry_observation == "observed"


def test_collector_rejects_mixed_kinds_and_over_cap():
    c = Collector("r", None, ROOT, CaptureLimits(), None, None, None, True)
    c.start(ROOT, None, "step")
    k1, k2 = uuid4(), uuid4()
    c.start(k1, ROOT, "step", None, None)
    c.end(k1, "failed")
    c.start(k2, ROOT, "model", None, 2)
    c.end(k2, "completed")
    c.end(ROOT, "completed")
    assert c.finish("completed").retry_observation == "unknown"
    plan = [(None, "failed")] + [(i, "failed") for i in range(2, 102)]
    big = Collector(
        "r", None, ROOT, CaptureLimits(max_spans=1000), None, None, None, True
    )
    _simulate(big, [*plan, (102, "completed")])
    assert big.finish("completed").retry_observation == "unknown"


def test_partial_capture_under_wrapper_is_unknown_never_observed():
    c = Collector("r", None, ROOT, CaptureLimits(max_spans=2), None, None, None, True)
    _simulate(c, [(None, "failed"), (2, "completed")])
    t = c.finish("completed")
    assert t.diagnostics.dropped and t.retry_observation == "unknown"


def test_unverified_collector_reads_nothing_and_reports_not_collected():
    c = Collector("r", None, ROOT, CaptureLimits(), None, None, None, False)
    _simulate(c, [(None, "failed"), (2, "completed")])
    t = c.finish("completed")
    assert (t.retry_observation, t.retry_links) == ("not_collected", ())


# -- provider-internal retries stay unobservable --------------------------------------


class RetryingModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        from tenacity import RetryCallState

        state = RetryCallState(retry_object=None, fn=None, args=(), kwargs={})  # type: ignore[arg-type]
        for _ in range(2):  # provider SDK retries internally and reports via callback
            run_manager.on_retry(state)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])


def test_model_internal_retry_callback_yields_no_links():
    w, _ = wrapped(RetryingModel())
    w.invoke("hello")
    t = w.traces[0]
    assert t.diagnostics.retry_signals == 2
    assert (t.retry_observation, t.retry_links, t.retry_attempts) == (
        "not_collected",
        (),
        0,
    )


# -- privacy and wire ------------------------------------------------------------------


def test_sentinels_in_tags_metadata_arguments_never_leave_the_collector():
    business, _ = failing(1)
    target = RunnableLambda(business).with_config(
        tags=[SENTINEL, f"user:{SENTINEL}"], metadata={SENTINEL: SENTINEL}
    )
    w, sink = wrapped(target.with_retry(stop_after_attempt=3, **FAST))
    w.invoke(SENTINEL, config={"tags": [SENTINEL], "metadata": {"m": SENTINEL}})
    t = w.traces[0]
    blob = repr(t) + repr(t.summary()) + repr(w.status) + repr(sink.events)
    blob += "".join(
        r.body.decode() + r.path for r in build_requests(t, deployment_id=DEPLOYMENT)
    )
    assert SENTINEL not in blob
    assert "retry:attempt" not in blob


def test_wire_bodies_are_byte_identical_with_or_without_retry_evidence():
    business, _ = failing(2)
    w, _ = wrapped(RunnableLambda(business).with_retry(stop_after_attempt=4, **FAST))
    w.invoke("v")
    t = w.traces[0]
    assert t.retry_links
    stripped = dataclasses.replace(
        t, retry_links=(), retry_observation="not_collected", retry_attempts=0
    )
    with_retry = build_requests(t, deployment_id=DEPLOYMENT)
    without = build_requests(stripped, deployment_id=DEPLOYMENT)
    assert [(r.path, r.body) for r in with_retry] == [(r.path, r.body) for r in without]
    for r in with_retry:
        assert b"retry" not in r.body and b"attempt" not in r.body
        assert (
            r.path.endswith(("execution-structures/batches",))
            or "classifications" in r.path
            or "usage" in r.path
        )
    assert {json.loads(r.body).get("schema_version") for r in with_retry} == {1}

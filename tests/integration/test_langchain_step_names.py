# ruff: noqa: E501
"""Opt-in producer step names: real LangChain callbacks, exact exported bytes, no content.

The SDK exports no chain, graph-node or run name by default. ``step_names`` is the application's explicit approval list,
exactly like ``tool_names``: a step carries a name only when the framework reports that exact name AND the application
approved it. Everything else (unapproved names, tags, metadata, constructor data) stays anonymous."""

from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("langchain_core")
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool

from agent_reliability.adapters.event_sinks import InMemoryEventSink
from agent_reliability.adapters.langchain_instrumentation import _Handler
from agent_reliability.experimental.instrumentation import build_requests, instrument
from agent_reliability.experimental.instrumentation.collector import Collector
from agent_reliability.experimental.instrumentation.model import CaptureLimits
from agent_reliability.sdk import AgentReliability

pytestmark = pytest.mark.integration
DEPLOYMENT = "11111111-1111-4111-8111-111111111111"
STRUCTURE = "/api/v1/execution-structures/batches"


@pytest.fixture(autouse=True)
def no_tracing(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")


@tool
def lookup(query: str) -> str:
    """Synthetic offline lookup."""
    return query


def wrapped(runnable, **kwargs):
    return instrument(
        runnable,
        sdk=AgentReliability(sink=InMemoryEventSink()),
        agent_id="support-agent",
        name="Support",
        version="1",
        **kwargs,
    )


def pipeline():
    """planner -> research(lookup tool) -> answer, each a real, explicitly named runnable."""
    planner = RunnableLambda(lambda x: x, name="planner")
    research = RunnableLambda(lambda x: lookup.invoke(x), name="research")
    answer = RunnableLambda(lambda x: x, name="answer")
    return planner | research | answer


def steps_of(trace):
    requests = build_requests(trace, deployment_id=DEPLOYMENT)
    body = json.loads(next(r.body for r in requests if r.path == STRUCTURE))
    return body["steps"], requests


def names_by_type(steps):
    return sorted((s["step_type"], s["component_name"]) for s in steps)


def test_default_exports_no_step_name_even_when_the_framework_reports_one():
    wrapper = wrapped(pipeline(), tool_names=("lookup",))
    assert wrapper.invoke("q") == "q"
    steps, requests = steps_of(wrapper.traces[0])
    other = [s for s in steps if s["step_type"] == "other"]
    assert len(other) >= 4  # the sequence and its three named runnables
    assert all(s["component_name"] is None for s in other)
    body = b"".join(r.body for r in requests)
    for framework_name in (b"planner", b"research", b"answer", b"RunnableSequence"):
        assert framework_name not in body
    assert all(
        e.component is None for e in wrapper.traces[0].events if e.kind == "step"
    )


def test_approved_step_names_are_exported_for_exactly_those_steps():
    wrapper = wrapped(
        pipeline(), tool_names=("lookup",), step_names=("planner", "research")
    )
    wrapper.invoke("q")
    steps, requests = steps_of(wrapper.traces[0])
    named = {s["component_name"] for s in steps if s["step_type"] == "other"}
    assert named == {
        None,
        "planner",
        "research",
    }  # 'answer' and the sequence stay anonymous
    assert [s["component_name"] for s in steps if s["step_type"] == "tool"] == [
        "lookup"
    ]
    body = b"".join(r.body for r in requests)
    assert b"answer" not in body and b"RunnableSequence" not in body


def test_explicit_run_name_is_exported_only_when_approved():
    config = {"run_name": "triage-agent"}
    plain = wrapped(RunnableLambda(lambda x: x))
    plain.invoke("q", config)
    assert all(s["component_name"] is None for s in steps_of(plain.traces[0])[0])
    approved = wrapped(RunnableLambda(lambda x: x), step_names=("triage-agent",))
    approved.invoke("q", config)
    assert [s["component_name"] for s in steps_of(approved.traces[0])[0]] == [
        "triage-agent"
    ]


def test_tags_metadata_and_unapproved_names_never_leave_the_process():
    secret = "PRIVATE-SENTINEL-4f9c"
    config = {
        "run_name": "customer-" + secret,  # a valid-looking alias nobody approved
        "tags": ["tag-" + secret],
        "metadata": {
            "user": secret,
            "name": "planner",
        },  # metadata 'name' is never read
    }
    wrapper = wrapped(RunnableLambda(lambda x: x), step_names=("planner",))
    wrapper.invoke("payload-" + secret, config)
    steps, requests = steps_of(wrapper.traces[0])
    assert all(s["component_name"] is None for s in steps)
    assert secret.encode() not in b"".join(r.body for r in requests)
    assert secret not in repr(wrapper.traces)


def test_serialized_constructor_data_is_not_used_as_a_name():
    # The approved name equals the runnable CLASS name that appears in serialized constructor data, not the callback name.
    wrapper = wrapped(
        RunnableLambda(lambda x: x, name="renamed"), step_names=("RunnableLambda",)
    )
    wrapper.invoke("q")
    assert all(s["component_name"] is None for s in steps_of(wrapper.traces[0])[0])


def test_structure_ids_parents_and_order_are_identical_with_and_without_names():
    plain = wrapped(pipeline(), tool_names=("lookup",))
    named = wrapped(
        pipeline(), tool_names=("lookup",), step_names=("planner", "research", "answer")
    )
    plain.invoke("q")
    named.invoke("q")

    def shape(trace):
        index = {
            e.span_id: i
            for i, e in enumerate(e for e in trace.events if e.phase == "start")
        }
        return [
            (
                e.kind,
                e.phase,
                index.get(e.span_id),
                index.get(e.parent_span_id),
                e.state,
            )
            for e in trace.events
        ]

    assert shape(plain.traces[0]) == shape(named.traces[0])
    assert len({e.span_id for e in named.traces[0].events}) == len(
        {e.span_id for e in plain.traces[0].events}
    )


def test_tool_and_model_spans_are_unchanged_and_a_step_name_never_gets_tool_semantics():
    model = GenericFakeChatModel(messages=iter([AIMessage(content="ok")]))
    wrapper = wrapped(
        RunnableLambda(lambda x: lookup.invoke(x), name="lookup")
        | RunnableLambda(lambda x: model.invoke(x), name="draft"),
        tool_names=("lookup",),
        step_names=("lookup", "draft"),  # 'lookup' is also an approved TOOL name
        tool_classes={"lookup": "retrieval"},
        tool_actions={"lookup": "read"},
        model_id="model-a",
    )
    wrapper.invoke("q")
    trace = wrapper.traces[0]
    steps, requests = steps_of(trace)
    by_type = {
        t: [s["component_name"] for s in steps if s["step_type"] == t]
        for t in ("tool", "model", "other")
    }
    assert by_type["tool"] == ["lookup"] and by_type["model"] == ["model-a"]
    assert "draft" in by_type["other"] and "lookup" in by_type["other"]
    # classification is asserted for the TOOL span only; the same-named step gets no tool/action class
    assert all(e.tool_class is None for e in trace.events if e.kind == "step")
    classes = json.loads(
        next(
            r.body
            for r in requests
            if r.path.endswith("/execution-classifications/batches")
        )
    )["assertions"]
    tool_step = next(s["step_id"] for s in steps if s["step_type"] == "tool")
    assert [c["step_id"] for c in classes] == [tool_step]


def test_local_summary_groups_steps_by_their_approved_name():
    wrapper = wrapped(pipeline(), tool_names=("lookup",), step_names=("planner",))
    wrapper.invoke("q")
    rows = {
        (c.kind, c.component): c.calls for c in wrapper.traces[0].summary().components
    }
    assert rows[("step", "planner")] == 1 and rows[("step", None)] >= 3


def test_async_invoke_exports_approved_names():
    wrapper = wrapped(pipeline(), tool_names=("lookup",), step_names=("planner",))
    assert asyncio.run(wrapper.ainvoke("q")) == "q"
    steps, _ = steps_of(wrapper.traces[0])
    assert "planner" in {s["component_name"] for s in steps}


@pytest.mark.parametrize(
    "bad",
    [
        "has space",
        "",
        "x" * 129,
        "naïve",
        "a/b",
        "semi;colon",
        "tab\t",
        5,
        None,
        b"bytes",
    ],
)
def test_invalid_step_names_are_rejected_at_setup_never_rewritten(bad):
    with pytest.raises((ValueError, TypeError)):
        wrapped(RunnableLambda(lambda x: x), step_names=(bad,))


@pytest.mark.parametrize("bad", ["planner", b"planner", 5, None])
def test_step_names_must_be_a_bounded_collection(bad):
    with pytest.raises((ValueError, TypeError)):
        wrapped(RunnableLambda(lambda x: x), step_names=bad)


def test_boundary_length_names_are_accepted_and_exported():
    longest = "n" * 128
    wrapper = wrapped(RunnableLambda(lambda x: x, name=longest), step_names=(longest,))
    wrapper.invoke("q")
    assert steps_of(wrapper.traces[0])[0][0]["component_name"] == longest


def test_the_512_component_cap_counts_distinct_tools_steps_and_model_together():
    tools = tuple(f"t{i}" for i in range(300))
    steps = tuple(f"s{i}" for i in range(213))  # 513 distinct with the model alias
    with pytest.raises(ValueError):
        wrapped(
            RunnableLambda(lambda x: x),
            tool_names=tools,
            step_names=steps,
            model_id="m",
        )
    overlap = tuple(
        f"t{i}" for i in range(300)
    )  # same names as tools: still 300 distinct
    wrapped(
        RunnableLambda(lambda x: x), tool_names=tools, step_names=overlap, model_id="m"
    )


def test_exported_requests_stay_valid_ascii_json_with_unchanged_envelope():
    wrapper = wrapped(pipeline(), tool_names=("lookup",), step_names=("planner",))
    wrapper.invoke("q")
    steps, requests = steps_of(wrapper.traces[0])
    body = json.loads(next(r.body for r in requests if r.path == STRUCTURE))
    assert set(body) == {
        "schema_version",
        "source",
        "producer_run_id",
        "deployment_id",
        "steps",
    }
    assert set(steps[0]) == {
        "step_id",
        "parent_step_id",
        "step_type",
        "component_name",
        "state",
        "started_at",
        "ended_at",
    }
    for r in requests:
        r.body.decode("ascii")


class _LooksApproved(str):
    """A str SUBCLASS equal to an approved name: exact type is required, so it is not exported."""


def _chain_start(name):
    from uuid import uuid4

    root = uuid4()
    collector = Collector(str(uuid4()), None, root, CaptureLimits(), None, None, None)
    handler = _Handler(collector, frozenset(), frozenset({"planner"}))
    handler.on_chain_start({}, {}, run_id=root, parent_run_id=None, name=name)
    handler.on_chain_end({}, run_id=root)
    return collector.finish("completed")


def test_only_an_exact_str_name_equal_to_an_approved_name_is_exported():
    assert [
        e.component for e in _chain_start("planner").events if e.kind == "step"
    ] == ["planner", "planner"]


@pytest.mark.parametrize(
    "name",
    [
        _LooksApproved("planner"),
        b"planner",
        5,
        ["planner"],
        ("planner",),
        None,
        "Planner",
        " planner",
        "planner ",
        "planner\n",
        "planner" + "x" * 130,
    ],
)
def test_a_name_that_is_not_exactly_an_approved_str_is_never_exported(name):
    trace = _chain_start(name)
    assert all(e.component is None for e in trace.events)
    assert trace.complete


def test_a_metadata_name_alone_is_never_read_as_a_step_name():
    # no run_name at all: the framework's own name is the runnable's default, and metadata/tags are untouched
    wrapper = wrapped(
        RunnableLambda(lambda x: x), step_names=("planner", "RunnableLambda")
    )
    wrapper.invoke(
        "q",
        {"metadata": {"name": "planner", "run_name": "planner"}, "tags": ["planner"]},
    )
    steps, _ = steps_of(wrapper.traces[0])
    assert [s["component_name"] for s in steps] == [
        "RunnableLambda"
    ]  # only the framework's reported name, because it was approved
    unapproved = wrapped(RunnableLambda(lambda x: x), step_names=("planner",))
    unapproved.invoke(
        "q",
        {
            "metadata": {"name": "planner", "run_name_hint": "planner"},
            "tags": ["planner"],
        },
    )
    assert all(s["component_name"] is None for s in steps_of(unapproved.traces[0])[0])

"""Pure trace-to-request conversion: bounds, closed vocabularies, privacy."""

import json
from uuid import uuid4

import pytest

from agent_reliability.experimental.instrumentation.collector import Collector
from agent_reliability.experimental.instrumentation.export import (
    CLASSIFICATION_PATH,
    MAX_ITEMS_PER_REQUEST,
    STRUCTURE_PATH,
    USAGE_PATH,
    build_requests,
)
from agent_reliability.experimental.instrumentation.model import (
    CaptureLimits,
    TokenUsage,
)

DEPLOYMENT = "11111111-1111-4111-8111-111111111111"


def make(semantics=None, **limits):
    root = uuid4()
    run_id = str(uuid4())
    return (
        Collector(
            run_id,
            None,
            root,
            CaptureLimits(**limits),
            None,
            "model-alias",
            semantics,
        ),
        root,
        run_id,
    )


def bodies(trace, path):
    return [
        json.loads(r.body)
        for r in build_requests(trace, deployment_id=DEPLOYMENT)
        if r.path == path
    ]


def sample():
    collector, root, _run_id = make({"search": ("retrieval", "read")})
    tool_key, model_key, failing_key = uuid4(), uuid4(), uuid4()
    collector.start(root, None, "step")
    collector.start(model_key, root, "model")
    collector.end(
        model_key, "completed", TokenUsage("reported", 15, 10, 5), expected_kind="model"
    )
    collector.start(tool_key, root, "tool", "search")
    collector.end(tool_key, "completed", expected_kind="tool")
    collector.start(failing_key, root, "tool", "search")
    collector.end(failing_key, "failed", expected_kind="tool", outcome="timeout")
    collector.end(root, "completed", expected_kind="step")
    return collector.finish("completed"), root


def test_structure_roots_have_null_parent_and_children_reference_steps():
    trace, _ = sample()
    (batch,) = bodies(trace, STRUCTURE_PATH)
    assert batch["schema_version"] == 1 and batch["producer_run_id"] == trace.run_id
    assert (
        batch["deployment_id"] == DEPLOYMENT and batch["source"] == "agent-reliability"
    )
    steps = batch["steps"]
    ids = {s["step_id"] for s in steps}
    roots = [s for s in steps if s["parent_step_id"] is None]
    assert len(roots) == 1 and roots[0]["step_type"] == "other"
    assert all(s["parent_step_id"] in ids for s in steps if s["parent_step_id"])
    assert {s["step_type"] for s in steps} == {"other", "model", "tool"}
    assert all(
        s["state"] != "started" and s["ended_at"] >= s["started_at"] for s in steps
    )
    assert all(s["started_at"].endswith("Z") for s in steps)


def test_classification_and_usage_use_closed_values_only():
    trace, _ = sample()
    (classes,) = bodies(trace, CLASSIFICATION_PATH)
    got = sorted(
        (a["tool_class"], a["action_class"], a["execution_outcome"])
        for a in classes["assertions"]
    )
    assert got == [("retrieval", "read", "success"), ("retrieval", "read", "timeout")]
    (usage,) = bodies(trace, USAGE_PATH)
    assert [
        (a["total_tokens"], a["input_tokens"], a["output_tokens"])
        for a in usage["assertions"]
    ] == [(15, 10, 5)]


def test_unknown_outcome_is_not_invented_for_incomplete_tools():
    collector, root, _ = make()
    collector.start(root, None, "step")
    collector.start(uuid4(), root, "tool", "never-finished")
    trace = collector.finish("failed")
    (batch,) = bodies(trace, STRUCTURE_PATH)
    states = {s["step_type"]: s["state"] for s in batch["steps"]}
    assert states["tool"] == "started"  # honest: open, not completed
    assert all(s["ended_at"] is None for s in batch["steps"] if s["state"] == "started")
    assert bodies(trace, CLASSIFICATION_PATH) == []


def test_missing_usage_sends_no_usage_assertion_and_no_zero():
    collector, root, _ = make()
    collector.start(root, None, "step")
    key = uuid4()
    collector.start(key, root, "model")
    collector.end(key, "completed", TokenUsage(), expected_kind="model")
    collector.end(root, "completed", expected_kind="step")
    assert bodies(collector.finish("completed"), USAGE_PATH) == []


def test_batches_are_bounded_and_deterministic_for_retry_idempotence():
    collector, root, _ = make(max_spans=1000)
    collector.start(root, None, "step")
    for _ in range(120):
        key = uuid4()
        collector.start(key, root, "tool", None)
        collector.end(key, "completed", expected_kind="tool")
    collector.end(root, "completed", expected_kind="step")
    trace = collector.finish("completed")
    first = build_requests(trace, deployment_id=DEPLOYMENT)
    again = build_requests(trace, deployment_id=DEPLOYMENT)
    assert first == again
    sizes = [
        len(json.loads(r.body)["steps"]) for r in first if r.path == STRUCTURE_PATH
    ]
    assert sum(sizes) == 121 and max(sizes) == MAX_ITEMS_PER_REQUEST
    assert all(len(r.body) < 40_000 for r in first)


def test_span_cap_never_exceeds_platform_step_limit():
    collector, root, _ = make(max_spans=1000)
    collector.start(root, None, "step")
    for _ in range(1100):
        collector.start(uuid4(), root, "tool")
    trace = collector.finish("completed")
    total = sum(len(b["steps"]) for b in bodies(trace, STRUCTURE_PATH))
    assert total <= 1000 and trace.diagnostics.dropped > 0


def test_exported_depth_never_exceeds_platform_depth():
    collector, root, _ = make(max_depth=16)
    parent, keys = root, [root]
    collector.start(root, None, "step")
    for _ in range(20):
        key = uuid4()
        collector.start(key, parent, "step")
        parent = key
        keys.append(key)
    trace = collector.finish("completed")
    steps = {s["step_id"]: s for b in bodies(trace, STRUCTURE_PATH) for s in b["steps"]}

    def depth(step):
        n = 1
        while step["parent_step_id"]:
            step = steps[step["parent_step_id"]]
            n += 1
        return n

    assert max(depth(s) for s in steps.values()) <= 16


def test_no_content_or_names_in_requests_when_names_unapproved():
    collector, root, _ = make()
    collector.start(root, None, "step")
    key = uuid4()
    collector.start(key, root, "tool", None)  # adapter passes None for unapproved names
    collector.end(key, "failed", expected_kind="tool", outcome="execution_error")
    collector.end(root, "completed", expected_kind="step")
    wire = b"".join(
        r.body
        for r in build_requests(collector.finish("completed"), deployment_id=DEPLOYMENT)
    )
    assert b'component_name":null' in wire
    assert b'"tool_class":null' in wire


@pytest.mark.parametrize("outcome", ["success", "cancelled", "nonsense", None])
def test_failed_tool_outcome_is_normalised_to_closed_failure_value(outcome):
    collector, root, _ = make()
    collector.start(root, None, "step")
    key = uuid4()
    collector.start(key, root, "tool")
    collector.end(key, "failed", expected_kind="tool", outcome=outcome)
    event = next(
        e
        for e in collector.finish("completed").events
        if e.kind == "tool" and e.phase == "terminal"
    )
    assert event.outcome == "execution_error"


def test_summary_reports_time_tools_failures_and_tokens():
    trace, _ = sample()
    summary = trace.summary()
    by = {(c.kind, c.component): c for c in summary.components}
    assert by[("tool", "search")].calls == 2 and by[("tool", "search")].failed == 1
    assert by[("model", "model-alias")].calls == 1
    assert summary.total_tokens == 15 and summary.token_unknown_models == 0
    assert summary.state == "completed" and summary.complete

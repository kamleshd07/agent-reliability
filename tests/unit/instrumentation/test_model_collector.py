from uuid import uuid4

import pytest

from agent_reliability.experimental.instrumentation.collector import Collector
from agent_reliability.experimental.instrumentation.model import (
    MAX_COUNT,
    CaptureLimits,
    TokenUsage,
    alias,
)


def make(**kwargs):
    root = uuid4()
    return Collector(
        str(uuid4()), None, root, CaptureLimits(**kwargs), None, None
    ), root


@pytest.mark.parametrize(
    "field,invalid",
    [
        ("max_spans", 0),
        ("max_spans", 1001),
        ("max_depth", 17),
        ("max_active_runs", 129),
        ("max_retained_runs", 33),
        ("max_spans", True),
    ],
)
def test_limits_reject_invalid_configuration(field, invalid):
    with pytest.raises(ValueError):
        CaptureLimits(**{field: invalid})


@pytest.mark.parametrize("value", ["", "private/path", "a b", "ä", "x" * 129, 12])
def test_identifier_grammar_is_bounded_and_error_has_no_value(value):
    with pytest.raises(ValueError) as exc:
        alias(value)
    assert "private" not in str(exc.value)


@pytest.mark.parametrize(
    "usage",
    [TokenUsage(), TokenUsage("reported", 0, 0, 0), TokenUsage("reported", MAX_COUNT)],
)
def test_valid_usage(usage):
    assert usage.availability in ("reported", "unknown")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"total_tokens": 1},
        {"availability": "reported"},
        {"availability": "reported", "total_tokens": True},
        {"availability": "reported", "total_tokens": -1},
        {"availability": "reported", "total_tokens": MAX_COUNT + 1},
    ],
)
def test_invalid_usage_rejected(kwargs):
    with pytest.raises(ValueError):
        TokenUsage(**kwargs)


def test_order_parent_links_duplicate_callbacks_and_reserved_terminal_space():
    c, root = make(max_spans=2)
    child = uuid4()
    c.start(root, None, "step")
    c.start(child, root, "tool", "lookup")
    c.start(child, root, "tool", "lookup")
    for _ in range(200):
        c.start(uuid4(), root, "model")
    c.end(child, "completed")
    c.end(child, "failed")
    c.end(root, "completed")
    t = c.finish("completed")
    assert len(t.events) == 6
    assert t.diagnostics.dropped == 200 and t.diagnostics.duplicates == 2
    assert not t.complete
    assert [e.sequence for e in t.events] == list(range(1, 7))
    starts = {e.span_id for e in t.events if e.phase == "start"}
    assert all(e.parent_span_id is None or e.parent_span_id in starts for e in t.events)
    assert t.tool_calls == 1 and t.model_invocations == 0
    assert all(
        e.duration_ns is not None and e.duration_ns >= 0
        for e in t.events
        if e.phase == "terminal"
    )


def test_depth_orphan_and_missing_callbacks_are_explicitly_incomplete():
    c, root = make(max_depth=1)
    c.start(
        root, uuid4(), "step"
    )  # explicit framework root can have an external parent
    c.start(uuid4(), root, "tool")
    c.start(uuid4(), uuid4(), "tool")
    c.end(uuid4(), "completed")
    t = c.finish("completed")
    assert t.diagnostics.dropped == 1 and t.diagnostics.orphans == 2
    assert t.diagnostics.unfinished == 1
    terminal = [e for e in t.events if e.synthetic]
    assert len(terminal) == 1 and terminal[0].state == "incomplete"
    assert terminal[0].duration_ns is None
    c.start(uuid4(), None, "step")  # late callbacks cannot mutate retained snapshots
    assert len(t.events) == 4


def test_unknown_tokens_not_zero_and_no_callback_run_not_complete():
    c, root = make()
    c.start(root, None, "model")
    c.end(root, "completed")
    t = c.finish("completed")
    e = next(e for e in t.events if e.kind == "model" and e.phase == "terminal")
    assert e.usage == TokenUsage()
    assert e.usage.total_tokens is None and t.complete
    empty, _ = make()
    assert not empty.finish("completed").complete

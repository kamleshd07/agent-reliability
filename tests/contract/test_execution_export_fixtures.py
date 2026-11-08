"""Data-only wire fixtures for the three execution request bodies."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_reliability.experimental.instrumentation import build_requests
from agent_reliability.experimental.instrumentation.model import (
    CaptureDiagnostics,
    ExecutionEvent,
    ExecutionTrace,
    TokenUsage,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "execution_export"
RUN = "00000000-0000-4000-8000-000000000001"
DEPLOYMENT = "00000000-0000-4000-8000-0000000000d1"
T0 = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def trace():
    def e(seq, span, parent, kind, phase, at, **kw):
        return ExecutionEvent(RUN, seq, span, parent, kind, phase, T0 + at, **kw)

    ms = timedelta(milliseconds=1)
    events = (
        e(1, RUN, None, "run", "start", 0 * ms),
        e(2, "s1", RUN, "step", "start", 1 * ms),
        e(3, "m1", "s1", "model", "start", 2 * ms, model_id="model-a"),
        e(
            4,
            "m1",
            "s1",
            "model",
            "terminal",
            12 * ms,
            state="completed",
            duration_ns=10_000_000,
            model_id="model-a",
            usage=TokenUsage("reported", 15, 10, 5),
        ),
        e(
            5,
            "t1",
            "s1",
            "tool",
            "start",
            13 * ms,
            component="search",
            tool_class="retrieval",
            action_class="read",
        ),
        e(
            6,
            "t1",
            "s1",
            "tool",
            "terminal",
            18 * ms,
            state="failed",
            duration_ns=5_000_000,
            component="search",
            outcome="timeout",
            tool_class="retrieval",
            action_class="read",
        ),
        e(7, "t2", "s1", "tool", "start", 19 * ms),
        e(
            8,
            "s1",
            RUN,
            "step",
            "terminal",
            30 * ms,
            state="completed",
            duration_ns=29_000_000,
        ),
        e(
            9,
            RUN,
            None,
            "run",
            "terminal",
            31 * ms,
            state="completed",
            duration_ns=31_000_000,
        ),
    )
    return ExecutionTrace(RUN, None, events, CaptureDiagnostics())


def test_wire_bodies_match_published_fixtures():
    built = {
        Path(r.path).parent.name: json.loads(r.body)
        for r in build_requests(trace(), deployment_id=DEPLOYMENT)
    }
    assert set(built) == {
        "execution-structures",
        "execution-classifications",
        "execution-model-usage",
    }
    for name, body in built.items():
        expected = json.loads((FIXTURES / f"{name}.json").read_text())
        assert body == expected


def test_open_tool_step_is_started_without_end():
    steps = json.loads((FIXTURES / "execution-structures.json").read_text())["steps"]
    open_step = next(s for s in steps if s["step_id"] == "t2")
    assert open_step["state"] == "started" and open_step["ended_at"] is None

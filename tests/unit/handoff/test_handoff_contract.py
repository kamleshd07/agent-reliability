# ruff: noqa: C408
"""Closed schema, validation, idempotency and golden wire bodies (no network)."""

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from agent_reliability.experimental.handoff import (
    HandoffEmitter,
    HandoffEmitterConfig,
    HandoffValidationError,
    build_event,
    idempotency_key,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "handoff_emitter"
A = "00000000-0000-4000-8000-0000000000a1"
B = "00000000-0000-4000-8000-0000000000b2"
T0 = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
BASE = dict(
    source="agent-reliability",
    handoff_id="h-1",
    originating_agent_id=A,
    originating_producer_run_id="run-orig-1",
    receiving_agent_id=UUID(B),
    event_time=T0,
)
CASES = {
    "requested": dict(outcome_correlation_id="corr-1"),
    "acknowledged": dict(acceptance="accepted", receiving_producer_run_id="run-rcv-1"),
    "terminal": dict(terminal_state="completed", receiving_producer_run_id="run-rcv-1"),
}


@pytest.mark.parametrize("kind", sorted(CASES))
def test_golden_body_matches_fixture_and_contains_only_contract_members(kind):
    event = build_event(kind=kind, **BASE, **CASES[kind])
    golden = json.loads((FIXTURES / f"{kind}.json").read_text())
    assert json.loads(event.body) == golden
    assert event.body == json.dumps(
        golden, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    allowed = {
        "schema_version", "source", "handoff_id", "kind", "idempotency_key",
        "originating_agent_id", "originating_producer_run_id", "receiving_agent_id",
        "receiving_producer_run_id", "outcome_correlation_id", "event_time",
        "acceptance", "terminal_state",
    }  # fmt: skip
    assert set(golden) <= allowed
    assert "reporter" not in golden and golden["schema_version"] == 1


def test_idempotency_key_is_deterministic_and_semantic():
    args = {k: v for k, v in BASE.items() if k != "source"}
    one = idempotency_key(source="s", kind="requested", **args)
    assert one == idempotency_key(source="s", kind="requested", **args)
    assert one.startswith("hk1-") and len(one) == 68
    assert one != idempotency_key(source="s", kind="terminal", **args)
    assert one != idempotency_key(source="t", kind="requested", **args)
    later = {**args, "event_time": T0 + timedelta(seconds=1)}
    assert one != idempotency_key(source="s", kind="requested", **later)
    other_zone = {**args, "event_time": T0.astimezone(timezone(timedelta(hours=5)))}
    assert one == idempotency_key(source="s", kind="requested", **other_zone)


def test_caller_key_override_is_validated_and_used():
    event = build_event(kind="requested", idempotency_key="mine-1", **BASE)
    assert event.idempotency_key == "mine-1"
    with pytest.raises(HandoffValidationError):
        build_event(kind="requested", idempotency_key="has space", **BASE)


@pytest.mark.parametrize(
    "override",
    [
        dict(kind="other"),
        dict(kind="requested", acceptance="accepted"),
        dict(kind="requested", terminal_state="completed"),
        dict(kind="acknowledged"),
        dict(kind="acknowledged", acceptance="maybe"),
        dict(kind="terminal"),
        dict(kind="terminal", terminal_state="done"),
        dict(kind="terminal", terminal_state="failed", acceptance="accepted"),
        dict(kind="requested", handoff_id=""),
        dict(kind="requested", handoff_id="x" * 129),
        dict(kind="requested", handoff_id="bad id"),
        dict(kind="requested", source="x" * 101),
        dict(kind="requested", originating_agent_id="not-a-uuid"),
        dict(kind="requested", originating_producer_run_id="r" * 201),
        dict(kind="requested", receiving_producer_run_id=""),
        dict(kind="requested", outcome_correlation_id="a b"),
        dict(kind="requested", event_time=datetime(2026, 1, 1)),
        dict(kind="requested", event_time="2026-01-01T00:00:00Z"),
    ],
)
def test_invalid_members_are_rejected_with_a_value_free_label(override):
    args = {**BASE, **override}
    with pytest.raises(HandoffValidationError) as caught:
        build_event(**args)
    for value in override.values():
        if isinstance(value, str) and len(value) > 8:
            assert value not in str(caught.value)


def test_unknown_or_free_text_arguments_are_rejected_by_signature():
    emitter = HandoffEmitter(HandoffEmitterConfig())
    common = dict(
        handoff_id="h",
        originating_agent_id=A,
        originating_producer_run_id="r",
        receiving_agent_id=B,
    )
    for extra in ("prompt", "output", "metadata", "reporter", "message", "tool_args"):
        with pytest.raises(TypeError):
            emitter.requested(**common, **{extra: "x"})
    with pytest.raises(TypeError):
        build_event(kind="requested", **BASE, reporter="originator")


@pytest.mark.parametrize("bad", ["a b", "a\x00b", "a\tb", "a\nb", "é", "a\x7fb", " "])
@pytest.mark.parametrize(
    "member", ["originating_producer_run_id", "receiving_producer_run_id"]
)
def test_run_ids_must_be_printable_ascii_without_space_or_controls(member, bad):
    with pytest.raises(HandoffValidationError):
        build_event(kind="requested", **{**BASE, member: bad})
    ok = build_event(kind="requested", **{**BASE, member: "!~" + "r" * 198})
    assert isinstance(ok.members["event_time"], str)
    assert ok.members["schema_version"] == 1
    assert type(ok.members["schema_version"]) is int


@pytest.mark.parametrize("kind", ["acknowledged", "terminal"])
def test_receiver_helpers_carry_run_and_outcome_link(kind):
    event = build_event(
        kind=kind,
        **BASE,
        **{k: v for k, v in CASES[kind].items() if k != "receiving_producer_run_id"},
        receiving_producer_run_id="run-rcv-9",
        outcome_correlation_id="corr-9",
    )
    assert event.members["receiving_producer_run_id"] == "run-rcv-9"
    assert event.members["outcome_correlation_id"] == "corr-9"

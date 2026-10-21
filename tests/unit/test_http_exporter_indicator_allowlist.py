"""Fail-closed indicator policy: an allow-list, or an explicit unrestricted opt-out.

The ``indicator`` is the only free-text wire field. A sink must be told how to treat it
(``indicator_allowlist=[...]`` or ``allow_unrestricted_indicators=True``); an unapproved
indicator is rejected before anything is queued or sent, and its value is never logged.
"""

from __future__ import annotations

import enum
import json
import logging
import threading
import unicodedata
from uuid import UUID

import httpx
import pytest

from agent_reliability.adapters.http_event_sink import (
    AsyncHTTPEventSink,
    ConfigurationError,
    DeliveryDisposition,
    HTTPEventSink,
)
from agent_reliability.domain import AgentIdentity, EvaluationOutcome
from agent_reliability.sdk import AgentReliability

AGENT = AgentIdentity("agent", "Agent", "1", "test")
ALLOWED = "task-success"
SENTINEL = "customer jane@example.com asked about order 4417"
SENSITIVE_LOOKING = [
    SENTINEL,
    "sk-live-4f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c",
    "AKIAABCDEFGHIJKLMNOP",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.c2lnbmF0dXJl",
    "123-45-6789",
    "password=hunter2",
    "Bearer are_machine_abcdefghijklmnopqrstuvwxyz",
]


def _options(bodies: list[bytes], **extra: object) -> dict[str, object]:
    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        body = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "event_id": body["event_id"],
                "run_id": str(UUID(int=11)),
                "status": "accepted",
                "durability": "committed",
            },
        )

    return {
        "endpoint": "http://127.0.0.1:9/api/v1/evidence/runs",
        "credential_provider": lambda: "secret",
        "deployment_id": UUID(int=7),
        "expected_agent": AGENT,
        "_transport": httpx.MockTransport(handler),
        **extra,
    }


def _run(sdk: AgentReliability, *indicators: object) -> None:
    with sdk.run(
        agent_id=AGENT.agent_id,
        name=AGENT.name,
        version=AGENT.version,
        environment=AGENT.environment,
    ) as run:
        for indicator in indicators:
            run.record(
                indicator=indicator,  # type: ignore[arg-type]
                outcome=EvaluationOutcome.PASS,
            )


def _listed(bodies: list[bytes], **extra: object) -> HTTPEventSink:
    return HTTPEventSink(
        **_options(bodies, indicator_allowlist=[ALLOWED], **extra)  # type: ignore[arg-type]
    )


# ------------------------------------------------------- the policy is mandatory


def test_a_sink_without_a_policy_is_refused() -> None:
    with pytest.raises(ConfigurationError, match="indicator_policy_required"):
        HTTPEventSink(**_options([]))  # type: ignore[arg-type]


async def test_an_async_sink_without_a_policy_is_refused() -> None:
    with pytest.raises(ConfigurationError, match="indicator_policy_required"):
        AsyncHTTPEventSink(**_options([]))  # type: ignore[arg-type]


def test_both_policies_at_once_are_refused() -> None:
    with pytest.raises(ConfigurationError, match="indicator_policy_conflict"):
        HTTPEventSink(
            **_options(  # type: ignore[arg-type]
                [], indicator_allowlist=[ALLOWED], allow_unrestricted_indicators=True
            )
        )


@pytest.mark.parametrize("bad", [1, "yes", "True", 0.5, [], object(), None])
def test_the_unrestricted_opt_out_must_be_exactly_true(bad: object) -> None:
    with pytest.raises(
        ConfigurationError, match=r"indicator_policy_(invalid|required)"
    ):
        HTTPEventSink(
            **_options([], allow_unrestricted_indicators=bad)  # type: ignore[arg-type]
        )


def test_explicit_unrestricted_opt_out_keeps_the_previous_behaviour() -> None:
    bodies: list[bytes] = []
    sink = HTTPEventSink(
        **_options(bodies, allow_unrestricted_indicators=True)  # type: ignore[arg-type]
    )
    _run(AgentReliability(sink=sink), SENTINEL)
    sink.close(timeout=10)
    assert any(SENTINEL.encode() in body for body in bodies)


@pytest.mark.parametrize(
    "bad", [[], "task-success", [1], [""], 5, ["a\nb"], ["x" * 201], [None], [b"x"]]
)
def test_an_invalid_allowlist_is_a_configuration_error(bad: object) -> None:
    with pytest.raises(ConfigurationError, match="indicator_allowlist_invalid"):
        HTTPEventSink(**_options([], indicator_allowlist=bad))  # type: ignore[arg-type]


# ---------------------------------------------------------------- enforcement


def test_unlisted_indicator_is_rejected_before_queueing_or_sending() -> None:
    bodies: list[bytes] = []
    sink = _listed(bodies)
    _run(AgentReliability(sink=sink), ALLOWED, SENTINEL)
    snapshot = sink.close(timeout=10)
    joined = b"".join(bodies)
    assert ALLOWED.encode() in joined
    assert SENTINEL.encode() not in joined
    assert snapshot.queue_depth == 0
    assert snapshot.counts_by_disposition.get(DeliveryDisposition.COMMITTED, 0) > 0
    assert DeliveryDisposition.RETRY_EXHAUSTED not in snapshot.counts_by_disposition


@pytest.mark.parametrize("value", SENSITIVE_LOOKING)
def test_sensitive_looking_indicators_never_reach_the_wire(value: str) -> None:
    bodies: list[bytes] = []
    sink = _listed(bodies)
    _run(AgentReliability(sink=sink), value, ALLOWED)
    sink.close(timeout=10)
    joined = b"".join(bodies)
    assert value.encode() not in joined
    assert ALLOWED.encode() in joined


def test_the_allowlist_is_a_snapshot_not_a_live_view() -> None:
    bodies: list[bytes] = []
    names = [ALLOWED]
    sink = HTTPEventSink(**_options(bodies, indicator_allowlist=names))  # type: ignore[arg-type]
    names.append(SENTINEL)
    _run(AgentReliability(sink=sink), SENTINEL)
    sink.close(timeout=10)
    assert SENTINEL.encode() not in b"".join(bodies)


def test_a_rejection_leaves_no_partial_state_and_the_run_still_completes() -> None:
    bodies: list[bytes] = []
    sink = _listed(bodies)
    sdk = AgentReliability(sink=sink)
    _run(sdk, SENTINEL, ALLOWED, SENTINEL)
    snapshot = sink.close(timeout=10)
    sent = [json.loads(b) for b in bodies]
    kinds = [e["payload"]["kind"] for e in sent]
    assert kinds.count("evaluation_outcome") == 1
    assert kinds.count("run_lifecycle") == 2  # started and completed
    assert "measurement_health" in kinds
    assert snapshot.queue_depth == 0


async def test_async_sink_applies_the_same_policy() -> None:
    bodies: list[bytes] = []
    sink = AsyncHTTPEventSink(
        **_options(bodies, indicator_allowlist={ALLOWED})  # type: ignore[arg-type]
    )
    _run(AgentReliability(sink=sink), ALLOWED, SENTINEL)
    await sink.close(timeout=10)
    joined = b"".join(bodies)
    assert ALLOWED.encode() in joined
    assert SENTINEL.encode() not in joined


def test_concurrent_runs_cannot_slip_an_unlisted_indicator_through() -> None:
    bodies: list[bytes] = []
    sink = _listed(bodies)
    sdk = AgentReliability(sink=sink)

    def work(index: int) -> None:
        _run(sdk, ALLOWED, f"{SENTINEL} {index}")

    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    sink.close(timeout=20)
    assert b"jane@example.com" not in b"".join(bodies)


# ---------------------------------------------------------------- adversarial strings


class _AlwaysEqual(str):
    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return hash(ALLOWED)


class _LyingBehaviour(str):
    """Overrides every hook an allow-list check or serialiser might consult."""

    def __len__(self) -> int:
        return 3

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter("abc")

    def __getitem__(self, item):  # type: ignore[no-untyped-def]
        return "a"

    def __str__(self) -> str:
        return ALLOWED

    def __add__(self, other):  # type: ignore[no-untyped-def]
        return ALLOWED

    def __radd__(self, other):  # type: ignore[no-untyped-def]
        return ALLOWED

    def encode(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return ALLOWED.encode()

    def __eq__(self, other: object) -> bool:
        return other == ALLOWED

    def __hash__(self) -> int:
        return hash(ALLOWED)


class _FlipFlop(str):
    calls = 0

    def __eq__(self, other: object) -> bool:
        type(self).calls += 1
        return type(self).calls % 2 == 1

    def __hash__(self) -> int:
        return hash(ALLOWED)


class _Slotted(str):
    __slots__ = ()

    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return hash(ALLOWED)


class _Member(str, enum.Enum):  # noqa: UP042 - exercises the (str, Enum) pattern
    SENSITIVE = "customer jane@example.com asked about order 4417"
    LISTED = "task-success"


@pytest.mark.parametrize(
    "factory", [_AlwaysEqual, _LyingBehaviour, _FlipFlop, _Slotted]
)
def test_str_subclasses_cannot_pose_as_an_allowed_indicator(factory: type[str]) -> None:
    bodies: list[bytes] = []
    sink = _listed(bodies)
    _run(AgentReliability(sink=sink), factory(SENTINEL))
    sink.close(timeout=10)
    assert SENTINEL.encode() not in b"".join(bodies)


def test_an_allowlist_entry_that_is_a_subclass_cannot_widen_the_list() -> None:
    bodies: list[bytes] = []
    sink = HTTPEventSink(
        **_options(  # type: ignore[arg-type]
            bodies, indicator_allowlist=[_AlwaysEqual(ALLOWED)]
        )
    )
    _run(AgentReliability(sink=sink), SENTINEL, ALLOWED)
    sink.close(timeout=10)
    joined = b"".join(bodies)
    assert SENTINEL.encode() not in joined
    assert ALLOWED.encode() in joined


def test_str_enum_members_are_matched_by_value_and_sent_as_exact_str() -> None:
    bodies: list[bytes] = []
    sink = _listed(bodies)
    _run(AgentReliability(sink=sink), _Member.SENSITIVE, _Member.LISTED)
    sink.close(timeout=10)
    joined = b"".join(bodies)
    assert SENTINEL.encode() not in joined
    assert ALLOWED.encode() in joined


@pytest.mark.parametrize(
    "lookalike",
    [
        "task\u2010success",  # hyphen lookalike
        "task-succes\u0455",  # Cyrillic s
        "task-success ",  # trailing space
        " task-success",
        "Task-Success",
        "task-success​",  # zero width space
        "task­success",  # soft hyphen
        unicodedata.normalize("NFD", "task-succéss"),
        "task-success\x00",
        "task-success\n",
    ],
)
def test_exact_match_only_so_lookalikes_variants_and_controls_are_rejected(
    lookalike: str,
) -> None:
    bodies: list[bytes] = []
    sink = _listed(bodies)
    _run(AgentReliability(sink=sink), lookalike)
    sink.close(timeout=10)
    assert bodies == [] or all(
        json.loads(b)["payload"].get("indicator") != lookalike for b in bodies
    )
    assert lookalike.encode() not in b"".join(bodies)
    assert lookalike.encode("unicode_escape") not in b"".join(bodies)


@pytest.mark.parametrize(
    "not_text", [None, 5, b"task-success", ["task-success"], object()]
)
def test_non_string_indicators_are_refused_by_the_sdk_and_nothing_is_sent(
    not_text: object,
) -> None:
    bodies: list[bytes] = []
    sink = _listed(bodies)
    with pytest.raises(ValueError):
        _run(AgentReliability(sink=sink), not_text)
    sink.close(timeout=10)
    assert b"evaluation_outcome" not in b"".join(bodies)


def test_length_limits_still_apply_inside_the_allowlist() -> None:
    long_name = "n" * 200
    bodies: list[bytes] = []
    sink = HTTPEventSink(
        **_options(bodies, indicator_allowlist=[long_name])  # type: ignore[arg-type]
    )
    _run(AgentReliability(sink=sink), long_name, "n" * 201)
    sink.close(timeout=10)
    joined = b"".join(bodies)
    assert long_name.encode() in joined
    assert ("n" * 201).encode() not in joined


# ------------------------------------------------------- the value is never logged


def test_a_rejected_indicator_value_is_never_logged_or_exposed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    bodies: list[bytes] = []
    sink = _listed(bodies)
    for value in SENSITIVE_LOOKING:
        _run(AgentReliability(sink=sink), value)
    snapshot = sink.close(timeout=10)
    haystack = "\n".join(
        [r.getMessage() + " " + repr(r.__dict__) for r in caplog.records]
        + [repr(snapshot), str(snapshot.recent_records)]
    )
    for value in SENSITIVE_LOOKING:
        assert value not in haystack
        assert value.encode() not in b"".join(bodies)
    assert "jane@example.com" not in haystack
    assert "hunter2" not in haystack

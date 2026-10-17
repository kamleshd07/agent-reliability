"""P29-S07 (executor driver) and P29-S08 (StructuredOutputEvaluator)."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation import EvaluatorIdentity
from agent_reliability.experimental.judge import (
    CallableSyncProvider,
    ExecutorSyncProvider,
    JudgeLimits,
    JudgeProviderUnavailableError,
    JudgeTimeoutError,
    ProviderCall,
    ProviderReply,
    StructuredOutputEvaluator,
    SyncLLMJudge,
)
from agent_reliability.sdk.evaluator_runner import EvaluatorRunner
from tests.fakes.p29_judge import good_reply, grounded_request, named_rubrics

pytestmark = pytest.mark.unit


def call(deadline: float = 0.05) -> ProviderCall:
    return ProviderCall("s", "u", 64, 0.0, True, deadline)


def test_p29_s07_ac01_hung_call_is_abandoned_after_the_deadline() -> None:
    release = threading.Event()
    inner = CallableSyncProvider(
        lambda c: (release.wait(5), ProviderReply(good_reply()))[1],
        provider_label="hang",
    )
    provider = ExecutorSyncProvider(inner, max_threads=2)
    started = time.monotonic()
    with pytest.raises(JudgeTimeoutError):
        provider.complete(call(0.05))
    assert time.monotonic() - started < 1.0
    assert provider.live_threads == 1  # still blocked inside the provider
    release.set()
    deadline = time.monotonic() + 2
    while provider.live_threads and time.monotonic() < deadline:
        time.sleep(0.005)
    assert provider.live_threads == 0  # late result discarded, thread ended


def test_p29_s07_ac01_threads_are_daemon_and_bounded() -> None:
    release = threading.Event()
    threads: list[threading.Thread] = []

    def blocked(c: ProviderCall) -> ProviderReply:
        threads.append(threading.current_thread())
        release.wait(5)
        return ProviderReply(good_reply())

    provider = ExecutorSyncProvider(
        CallableSyncProvider(blocked, provider_label="b"), max_threads=2
    )
    for _ in range(2):
        with pytest.raises(JudgeTimeoutError):
            provider.complete(call(0.02))
    with pytest.raises(JudgeProviderUnavailableError):  # bound reached: no new thread
        provider.complete(call(0.02))
    assert len(threads) == 2 and all(t.daemon for t in threads)
    assert provider.live_threads == 2
    release.set()
    for t in threads:
        t.join(2)
    assert provider.live_threads == 0


def test_p29_s07_ac01_late_result_cannot_change_a_terminal_outcome() -> None:
    gate = threading.Event()
    results: list[str] = []

    def slow(c: ProviderCall) -> ProviderReply:
        gate.wait(5)
        results.append("late")
        return ProviderReply(good_reply())

    provider = ExecutorSyncProvider(CallableSyncProvider(slow, provider_label="s"))
    judge = SyncLLMJudge(
        rubric=named_rubrics()["gr-cit"],
        provider=provider,
        model_label="exec",
        limits=JudgeLimits(max_attempts=1, provider_timeout_seconds=0.05),
        jitter=lambda: 0.0,
    )
    outcome = EvaluatorRunner().evaluate(judge, grounded_request())
    assert type(outcome).__name__ == "EvaluationExecutionFailure"
    assert outcome.exception_type == "JudgeTimeoutError"  # type: ignore[union-attr]
    gate.set()
    time.sleep(0.1)
    assert results == ["late"]  # the thread finished, but nothing consumed its result


def test_p29_s07_normal_and_failing_calls_pass_through() -> None:
    ok = ExecutorSyncProvider(
        CallableSyncProvider(lambda c: ProviderReply("x"), provider_label="ok")
    )
    assert ok.complete(call(1.0)).text == "x"
    assert ok.provider_label == "ok" and ok.live_threads == 0

    def boom(c: ProviderCall) -> ProviderReply:
        raise RuntimeError("provider failed")

    bad = ExecutorSyncProvider(CallableSyncProvider(boom, provider_label="bad"))
    with pytest.raises(RuntimeError):
        bad.complete(call(1.0))
    for n in (0, 65, True):
        with pytest.raises(ValueError):
            ExecutorSyncProvider(ok, max_threads=n)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ExecutorSyncProvider(object())  # type: ignore[arg-type]


# ---------------------------------------------------------------- S08


def ev(**required: Any) -> StructuredOutputEvaluator:
    return StructuredOutputEvaluator(
        EvaluatorIdentity("structured-check", "1"), required=required
    )


def test_p29_s08_ac01_required_keys_types_and_enums() -> None:
    e = ev(name="string", age="integer", status={"open", "closed"}, tags="array")
    assert e.deterministic is True
    good = {"name": "a", "age": 3, "status": "open", "tags": [], "extra": 1}
    assert e.evaluate(good).outcome is EvaluationOutcome.PASS
    assert e.evaluate(good).reason_code == "structured-output.valid"
    for broken in (
        {**good, "name": 5},
        {**good, "age": True},
        {**good, "age": 3.0},
        {**good, "status": "pending"},
        {**good, "status": 1},
        {k: v for k, v in good.items() if k != "tags"},
        [],
        "text",
    ):
        decision = e.evaluate(broken)
        assert decision.outcome is EvaluationOutcome.FAIL
        assert decision.reason_code == "structured-output.invalid"


def test_p29_s08_ac01_none_is_unknown_never_pass() -> None:
    decision = ev(a="string").evaluate(None)
    assert decision.outcome is EvaluationOutcome.UNKNOWN
    assert decision.reason_code == "structured-output.no-data"


def test_p29_s08_ac01_number_null_boolean_object_types() -> None:
    e = ev(n="number", z="null", b="boolean", o="object")
    assert e.evaluate({"n": 1, "z": None, "b": False, "o": {}}).outcome is (
        EvaluationOutcome.PASS
    )
    assert e.evaluate({"n": 1.5, "z": None, "b": True, "o": {"k": 1}}).outcome is (
        EvaluationOutcome.PASS
    )
    assert e.evaluate({"n": True, "z": None, "b": True, "o": {}}).outcome is (
        EvaluationOutcome.FAIL
    )


@pytest.mark.parametrize(
    "required",
    [
        {},
        {"": "string"},
        {"a": "text"},
        {"a": []},
        {"a": {1, 2}},
        {"a": 5},
        {"a": b"x"},
        [],
    ],
)
def test_p29_s08_ac01_malformed_configuration_raises_at_construction(
    required: Any,
) -> None:
    with pytest.raises((ValueError, TypeError)):
        StructuredOutputEvaluator(EvaluatorIdentity("x", "1"), required=required)
    with pytest.raises(TypeError):
        StructuredOutputEvaluator("x", required={"a": "string"})  # type: ignore[arg-type]


def test_p29_s08_ac02_shares_the_validator_and_uses_stdlib_only() -> None:
    import ast
    import pathlib

    import agent_reliability.experimental.judge as ns
    from agent_reliability.experimental.judge import _schema, core, structured

    assert structured.is_json_type is _schema.is_json_type
    assert core.is_json_type is _schema.is_json_type
    assert core.check_members is _schema.check_members
    for name in ("structured.py", "_schema.py"):
        tree = ast.parse((pathlib.Path(ns.__file__).parent / name).read_text())
        modules = {
            n.module.split(".")[0]
            for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom) and n.module
        } | {
            a.name.split(".")[0]
            for n in ast.walk(tree)
            if isinstance(n, ast.Import)
            for a in n.names
        }
        assert modules <= {"__future__", "collections", "typing", "agent_reliability"}


def test_p29_s08_runs_through_the_runner_as_a_deterministic_evaluator() -> None:
    result = EvaluatorRunner().evaluate(ev(a="string"), {"a": "x"})
    assert result.provenance.deterministic is True  # type: ignore[union-attr]

"""P29-S04: sync driver (SyncLLMJudge)."""

from __future__ import annotations

import ast
import pathlib
from typing import Any

import pytest

import agent_reliability.experimental.judge as namespace
from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation import (
    EvaluationExecutionFailure,
    EvaluationResult,
)
from agent_reliability.experimental.judge import (
    CallableSyncProvider,
    JudgeError,
    JudgeLimits,
    JudgeProviderError,
    JudgeProviderRateLimitedError,
    JudgeProviderUnavailableError,
    JudgeTimeoutError,
    ProviderReply,
    SyncLLMJudge,
)
from agent_reliability.experimental.judge.testing import FakeSyncProvider
from agent_reliability.sdk.evaluator_runner import EvaluatorRunner
from tests.fakes.p29_judge import (
    SECRET,
    FakeMonotonic,
    good_reply,
    grounded_request,
    named_rubrics,
)

pytestmark = pytest.mark.unit

GR = named_rubrics()["gr-cit"]


def sync_judge(provider: Any, **kw: Any) -> SyncLLMJudge:
    kw.setdefault("jitter", lambda: 0.0)
    kw.setdefault("sleep", lambda _s: None)
    return SyncLLMJudge(rubric=GR, provider=provider, model_label="fake-model", **kw)


def test_p29_s04_ac01_satisfies_sync_evaluator_and_runs_through_runner() -> None:
    j = sync_judge(FakeSyncProvider([good_reply()]))
    assert j.deterministic is False
    assert j.identity.name == "judge-groundedness"
    outcome = EvaluatorRunner().evaluate(j, grounded_request())
    assert isinstance(outcome, EvaluationResult)
    assert outcome.outcome is EvaluationOutcome.PASS
    assert outcome.provenance.deterministic is False
    assert "SyncLLMJudge" in repr(j)


def test_p29_s04_construction_checks() -> None:
    with pytest.raises(TypeError):
        SyncLLMJudge(rubric=GR, provider=object(), model_label="m")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        SyncLLMJudge(rubric=GR, provider=FakeSyncProvider([]), model_label="a b")
    provider = CallableSyncProvider(
        lambda call: ProviderReply(good_reply()), provider_label="cb"
    )
    assert isinstance(
        EvaluatorRunner().evaluate(sync_judge(provider), grounded_request()),
        EvaluationResult,
    )
    with pytest.raises(TypeError):
        CallableSyncProvider(42, provider_label="x")  # type: ignore[arg-type]


def test_p29_s04_ac02_late_reply_is_a_timeout_and_is_discarded() -> None:
    clock = FakeMonotonic()

    def slow_valid(call: Any) -> ProviderReply:
        clock.advance(call.deadline_seconds + 0.5)  # overran the deadline
        return ProviderReply(good_reply())

    provider = FakeSyncProvider([slow_valid, slow_valid])
    limits = JudgeLimits(max_attempts=2, provider_timeout_seconds=5)
    j = sync_judge(provider, limits=limits, monotonic=clock, sleep=clock.sleep)
    with pytest.raises(JudgeTimeoutError):
        j.evaluate(grounded_request())
    assert (
        provider.call_count == 2
    )  # the late (valid!) replies were discarded and retried


def test_p29_s04_ac02_late_reply_discarded_then_fast_reply_wins() -> None:
    clock = FakeMonotonic()

    def late(call: Any) -> ProviderReply:
        clock.advance(call.deadline_seconds + 1)
        return ProviderReply(good_reply())

    fail_reply = ProviderReply(
        '{"schema":"gentlity.judge-output/1","verdict":"fail",'
        '"code":"unsupported_claim","confidence":"high","citations":[]}'
    )
    provider = FakeSyncProvider([late, fail_reply])
    j = sync_judge(provider, monotonic=clock, sleep=clock.sleep)
    result = j.evaluate_detailed(grounded_request())
    assert (
        result.decision.outcome is EvaluationOutcome.FAIL
    )  # not the discarded late PASS
    assert result.stats.attempts == 2


def test_p29_s04_ac02_deadline_is_passed_and_capped_by_remaining_time() -> None:
    clock = FakeMonotonic()

    def spend(seconds: float) -> Any:
        def step(call: Any) -> Any:
            clock.advance(seconds)
            raise JudgeProviderUnavailableError

        return step

    provider = FakeSyncProvider([spend(4.0), spend(4.0), spend(4.0), good_reply()])
    limits = JudgeLimits(
        provider_timeout_seconds=5,
        evaluation_deadline_seconds=10,
        max_attempts=4,
        retry_backoff_cap_seconds=0,
    )
    j = sync_judge(provider, limits=limits, monotonic=clock, sleep=clock.sleep)
    # The third attempt spends 4 s against a 2 s remaining deadline: an overrun.
    with pytest.raises(JudgeTimeoutError):
        j.evaluate(grounded_request())
    deadlines = [c.deadline_seconds for c in provider.calls]
    assert deadlines[:2] == [5.0, 5.0]
    assert deadlines[2] == pytest.approx(
        2.0
    )  # remaining total deadline caps the attempt
    assert provider.call_count == 3


def test_p29_s04_backoff_uses_injected_sleep() -> None:
    clock = FakeMonotonic()
    provider = FakeSyncProvider(
        [
            JudgeProviderUnavailableError(),
            JudgeProviderRateLimitedError(2.5),
            good_reply(),
        ]
    )
    j = sync_judge(
        provider,
        limits=JudgeLimits(max_attempts=3),
        jitter=lambda: 1.0,
        monotonic=clock,
        sleep=clock.sleep,
    )
    assert isinstance(
        EvaluatorRunner().evaluate(j, grounded_request()), EvaluationResult
    )
    assert clock.sleeps == [0.25, 2.5]  # full-jitter ceiling, then Retry-After


def test_p29_s04_no_asyncio_run_anywhere_in_the_namespace() -> None:
    root = pathlib.Path(namespace.__file__).parent
    offenders: list[str] = []
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if (
                    isinstance(f, ast.Attribute)
                    and f.attr == "run"
                    and (isinstance(f.value, ast.Name) and f.value.id == "asyncio")
                ):
                    offenders.append(f"{path.name}:{node.lineno}")
                if isinstance(f, ast.Name) and f.id == "run_until_complete":
                    offenders.append(f"{path.name}:{node.lineno}")
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "asyncio"
                and any(a.name in {"run", "Runner"} for a in node.names)
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []


def test_p29_s04_keyboard_interrupt_propagates_and_failures_are_clean() -> None:
    provider = FakeSyncProvider([KeyboardInterrupt()])
    with pytest.raises(KeyboardInterrupt):
        sync_judge(provider).evaluate(grounded_request())
    provider = FakeSyncProvider([RuntimeError(SECRET)])
    with pytest.raises(JudgeProviderError) as caught:
        sync_judge(provider).evaluate(grounded_request(answer=SECRET))
    assert SECRET not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert isinstance(caught.value, JudgeError)


def test_p29_s04_sync_failure_through_runner_is_execution_failure() -> None:
    provider = FakeSyncProvider([RuntimeError("x")])
    outcome = EvaluatorRunner().evaluate(sync_judge(provider), grounded_request())
    assert isinstance(outcome, EvaluationExecutionFailure)
    assert outcome.exception_type == "JudgeProviderError"

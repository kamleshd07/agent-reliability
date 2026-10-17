"""P29-S03: async LLMJudge, retries, deadlines, budgets, privacy of failures."""

from __future__ import annotations

import asyncio
import logging
import re
from decimal import Decimal
from typing import Any

import pytest

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation import (
    EvaluationExecutionFailure,
    EvaluationFailureStage,
    EvaluationResult,
)
from agent_reliability.experimental.judge import (
    FAILURE_CLASS_NAMES,
    BudgetTracker,
    CallableProvider,
    CallableSyncProvider,
    Confidence,
    ContentPart,
    ContentRole,
    EvaluationRequest,
    JudgeBudget,
    JudgeBudgetExceededError,
    JudgeDimension,
    JudgeError,
    JudgeInputLimitError,
    JudgeInvalidOutputError,
    JudgeLimits,
    JudgePolicy,
    JudgeProviderError,
    JudgeProviderRateLimitedError,
    JudgeProviderUnavailableError,
    JudgeTimeoutError,
    LLMJudge,
    ProviderReply,
    Rubric,
)
from agent_reliability.experimental.judge.testing import (
    HANG,
    FakeProvider,
    judge_reply,
)
from agent_reliability.sdk import DiagnosticHandler, SdkDiagnostic
from agent_reliability.sdk.evaluator_runner import EvaluatorRunner
from tests.fakes.p29_judge import (
    SECRET,
    correctness_request,
    good_reply,
    grounded_request,
    named_rubrics,
    run_virtual,
)

pytestmark = pytest.mark.unit

RUBRICS = named_rubrics()
GR, AC = RUBRICS["gr-cit"], RUBRICS["ac"]


def judge(provider: Any, **kw: Any) -> LLMJudge:
    kw.setdefault("jitter", lambda: 0.0)
    kw.setdefault("rubric", GR)
    kw.setdefault("model_label", "fake-model")
    return LLMJudge(provider=provider, **kw)


def evaluate(j: LLMJudge, request: EvaluationRequest | None = None) -> Any:
    return asyncio.run(
        EvaluatorRunner().evaluate_async(j, request or grounded_request())
    )


# ------------------------------------------------------------------ S03-AC01


def test_p29_s03_ac01_satisfies_async_evaluator_and_runs_unchanged() -> None:
    j = judge(FakeProvider([good_reply()]))
    assert j.identity.name == "judge-groundedness"
    assert j.deterministic is False
    outcome = evaluate(j)
    assert isinstance(outcome, EvaluationResult)
    assert outcome.outcome is EvaluationOutcome.PASS
    assert outcome.reason_code == "groundedness.supported_by_context"
    assert outcome.provenance.deterministic is False
    assert outcome.provenance.identity == j.identity
    assert asyncio.iscoroutinefunction(j.evaluate)


def test_p29_s03_ac01_provider_label_and_construction_checks() -> None:
    with pytest.raises(TypeError):
        LLMJudge(rubric=GR, provider=object(), model_label="m")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        LLMJudge(
            rubric=GR,
            provider=CallableSyncProvider(
                lambda c: ProviderReply("x"), provider_label="s"
            ),  # type: ignore[arg-type]
            model_label="m",
        )
    with pytest.raises(TypeError):
        LLMJudge(rubric="rubric", provider=FakeProvider([]), model_label="m")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        LLMJudge(rubric=GR, provider=FakeProvider([]), model_label="bad label")
    with pytest.raises(TypeError):
        LLMJudge(rubric=GR, provider=FakeProvider([]), model_label="m", retain_cause=1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        LLMJudge(rubric=GR, provider=FakeProvider([]), model_label="m", limits="x")  # type: ignore[arg-type]


def test_p29_s03_repeats_need_disagreement_code() -> None:
    doc = GR.as_document()
    doc["reason_codes"]["unknown"].remove("judge_disagreement")
    no_dis = Rubric.from_dict(doc)
    judge(FakeProvider([]), rubric=no_dis)  # repeats=1 is fine
    with pytest.raises(ValueError, match="judge_disagreement"):
        judge(FakeProvider([]), rubric=no_dis, policy=JudgePolicy(repeats=2))


def test_p29_s03_callable_provider_adapter() -> None:
    async def fn(call: Any) -> ProviderReply:
        assert call.json_output is True and call.temperature == 0.0
        return ProviderReply(good_reply())

    provider = CallableProvider(fn, provider_label="callable")
    assert provider.provider_label == "callable" and provider.reports_tokens is False
    assert SECRET not in repr(provider)
    outcome = evaluate(judge(provider))
    assert isinstance(outcome, EvaluationResult)
    for bad in ("", "x" * 65, "a\nb"):
        with pytest.raises(ValueError):
            CallableProvider(fn, provider_label=bad)
    with pytest.raises(TypeError):
        CallableProvider("not callable", provider_label="x")  # type: ignore[arg-type]


# ------------------------------------------------------------------ S03-AC02


@pytest.mark.parametrize(
    "step,literal",
    [
        (JudgeTimeoutError(), "JudgeTimeoutError"),
        (JudgeProviderUnavailableError(), "JudgeProviderUnavailableError"),
        (JudgeProviderRateLimitedError(), "JudgeProviderRateLimitedError"),
        (RuntimeError(SECRET), "JudgeProviderError"),
        ("not json at all", "JudgeInvalidOutputError"),
        ("x" * 5000, "JudgeOutputTooLargeError"),
    ],
)
def test_p29_s03_ac02_every_fault_is_an_execution_failure(
    step: Any, literal: str
) -> None:
    limits = JudgeLimits(repair_attempts=0, max_attempts=1)
    outcome = evaluate(judge(FakeProvider([step]), limits=limits))
    assert isinstance(outcome, EvaluationExecutionFailure)
    assert outcome.stage is EvaluationFailureStage.EVALUATION
    assert outcome.exception_type == literal
    assert literal in FAILURE_CLASS_NAMES
    assert not isinstance(outcome, EvaluationResult)


def test_p29_s03_ac02_input_limit_and_budget_failures() -> None:
    outcome = evaluate(
        judge(FakeProvider([good_reply()]), limits=JudgeLimits(max_input_chars=3))
    )
    assert isinstance(outcome, EvaluationExecutionFailure)
    assert outcome.exception_type == "JudgeInputLimitError"
    tracker = BudgetTracker(JudgeBudget(max_tokens_per_window=1))
    tracker.record(1, 0)
    provider = FakeProvider([good_reply()], reports_tokens=True)
    outcome = evaluate(judge(provider, budget=tracker))
    assert isinstance(outcome, EvaluationExecutionFailure)
    assert outcome.exception_type == "JudgeBudgetExceededError"
    assert provider.call_count == 0


def test_p29_s03_ac02_failure_class_vocabulary_is_ten_fixed_names() -> None:
    assert len(FAILURE_CLASS_NAMES) == 10
    assert len(set(FAILURE_CLASS_NAMES)) == 10
    import agent_reliability.experimental.judge as ns

    for name in FAILURE_CLASS_NAMES:
        cls = getattr(ns, name)
        assert issubclass(cls, JudgeError) and cls.__name__ == name


def test_p29_s03_ac02_failure_carries_identity_and_stats() -> None:
    j = judge(FakeProvider([JudgeProviderUnavailableError()] * 2))
    outcome = evaluate(j)
    assert isinstance(outcome, EvaluationExecutionFailure)
    assert outcome.identity == j.identity
    with pytest.raises(JudgeProviderUnavailableError) as caught:
        asyncio.run(
            judge(FakeProvider([JudgeProviderUnavailableError()] * 2)).evaluate(
                grounded_request()
            )
        )
    assert caught.value.stats is not None
    assert caught.value.stats.attempts == 2


def test_p29_s03_dimension_mismatch_and_type_are_programmer_errors() -> None:
    j = judge(FakeProvider([good_reply()]))
    with pytest.raises(ValueError):
        asyncio.run(j.evaluate(correctness_request()))
    with pytest.raises(TypeError):
        asyncio.run(j.evaluate("a string"))  # type: ignore[arg-type]


# ------------------------------------------------------------------ S03-AC03


def test_p29_s03_ac03_per_attempt_timeout_on_virtual_clock() -> None:
    provider = FakeProvider([HANG, HANG])
    limits = JudgeLimits(provider_timeout_seconds=5, evaluation_deadline_seconds=60)
    j = judge(provider, limits=limits)

    async def go() -> Any:
        return await EvaluatorRunner().evaluate_async(j, grounded_request())

    outcome, elapsed = run_virtual(go)
    assert isinstance(outcome, EvaluationExecutionFailure)
    assert outcome.exception_type == "JudgeTimeoutError"
    assert provider.call_count == 2
    assert [c.deadline_seconds for c in provider.calls] == [5.0, 5.0]
    assert 10.0 <= elapsed < 10.5


def test_p29_s03_ac03_total_deadline_caps_the_last_attempt() -> None:
    provider = FakeProvider([HANG] * 5)
    limits = JudgeLimits(
        provider_timeout_seconds=5, evaluation_deadline_seconds=7, max_attempts=5
    )
    j = judge(provider, limits=limits)

    async def go() -> Any:
        return await EvaluatorRunner().evaluate_async(j, grounded_request())

    outcome, elapsed = run_virtual(go)
    assert isinstance(outcome, EvaluationExecutionFailure)
    assert outcome.exception_type == "JudgeTimeoutError"
    assert provider.call_count == 2
    assert provider.calls[1].deadline_seconds == pytest.approx(2.0, abs=0.01)
    assert 6.99 <= elapsed <= 7.1


def test_p29_s03_ac03_cancelled_error_propagates_and_is_not_converted() -> None:
    provider = FakeProvider([HANG])
    j = judge(provider)

    async def go() -> None:
        task = asyncio.ensure_future(
            EvaluatorRunner().evaluate_async(j, grounded_request())
        )
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
    assert provider.call_count == 1


class _Control(BaseException):
    """A BaseException that is not Exception, like KeyboardInterrupt."""


def test_p29_s03_ac03_base_exceptions_are_never_caught() -> None:
    provider = FakeProvider([_Control()])
    j = judge(provider)
    with pytest.raises(_Control):
        asyncio.run(j.evaluate(grounded_request()))
    with pytest.raises(_Control):
        evaluate(judge(FakeProvider([_Control()])))


# ------------------------------------------------------------------ S03-AC04


def test_p29_s03_ac04_backoff_within_full_jitter_bounds() -> None:
    unavailable = JudgeProviderUnavailableError()
    limits = JudgeLimits(max_attempts=3)

    def run(jitter_value: float, **kw: Any) -> tuple[Any, float]:
        provider = FakeProvider([unavailable, unavailable, good_reply()])
        j = judge(
            provider, limits=kw.pop("limits", limits), jitter=lambda: jitter_value
        )

        async def go() -> Any:
            return await EvaluatorRunner().evaluate_async(j, grounded_request())

        return run_virtual(go)

    outcome, elapsed = run(1.0)  # worst case: ceilings 0.25 then 0.5
    assert isinstance(outcome, EvaluationResult)
    assert elapsed == pytest.approx(0.75, abs=0.02)
    outcome, elapsed = run(0.5)
    assert elapsed == pytest.approx(0.375, abs=0.02)
    outcome, elapsed = run(0.0)
    assert elapsed < 0.02
    capped = JudgeLimits(max_attempts=3, retry_backoff_cap_seconds=0.1)
    outcome, elapsed = run(1.0, limits=capped)
    assert elapsed == pytest.approx(0.2, abs=0.02)  # each delay clamped to the cap


def test_p29_s03_ac04_default_jitter_is_random_in_range() -> None:
    delays = []
    for _ in range(30):
        provider = FakeProvider([JudgeProviderUnavailableError(), good_reply()])
        j = LLMJudge(rubric=GR, provider=provider, model_label="m")

        async def go(j: LLMJudge = j) -> Any:
            return await j.evaluate(grounded_request())

        _, elapsed = run_virtual(go)
        delays.append(elapsed)
    assert all(0.0 <= d <= 0.26 for d in delays)
    assert len({round(d, 6) for d in delays}) > 1


def test_p29_s03_ac04_retry_after_is_honoured() -> None:
    provider = FakeProvider([JudgeProviderRateLimitedError(3.0), good_reply()])
    j = judge(provider)

    async def go() -> Any:
        return await EvaluatorRunner().evaluate_async(j, grounded_request())

    outcome, elapsed = run_virtual(go)
    assert isinstance(outcome, EvaluationResult)
    assert elapsed == pytest.approx(3.0, abs=0.02)
    assert provider.call_count == 2


def test_p29_s03_ac04_retry_after_beyond_deadline_fails_without_sleeping() -> None:
    provider = FakeProvider([JudgeProviderRateLimitedError(100.0), good_reply()])
    limits = JudgeLimits(provider_timeout_seconds=5, evaluation_deadline_seconds=10)
    j = judge(provider, limits=limits)

    async def go() -> Any:
        return await EvaluatorRunner().evaluate_async(j, grounded_request())

    outcome, elapsed = run_virtual(go)
    assert isinstance(outcome, EvaluationExecutionFailure)
    assert outcome.exception_type == "JudgeProviderRateLimitedError"
    assert elapsed < 0.1
    assert provider.call_count == 1


def test_p29_s03_ac04_retry_after_attribute_is_sanitized() -> None:
    assert JudgeProviderRateLimitedError(-1).retry_after_seconds is None
    assert JudgeProviderRateLimitedError(float("nan")).retry_after_seconds is None
    assert JudgeProviderRateLimitedError(True).retry_after_seconds is None  # type: ignore[arg-type]
    assert JudgeProviderRateLimitedError("5").retry_after_seconds is None  # type: ignore[arg-type]
    assert JudgeProviderRateLimitedError(2).retry_after_seconds == 2.0


def test_p29_s03_ac04_repair_reask_uses_new_nonce_and_error_class_only() -> None:
    provider = FakeProvider(["garbage " + SECRET, good_reply()])
    j = judge(provider, nonce_source=None)
    outcome = evaluate(j)
    assert isinstance(outcome, EvaluationResult)
    first, second = provider.calls
    n1 = re.search(r"<<<BEGIN ([0-9a-f]{16})", first.user)
    n2 = re.search(r"<<<BEGIN ([0-9a-f]{16})", second.user)
    assert n1 and n2 and n1.group(1) != n2.group(1)
    assert "rejected (invalid_json)" in second.user
    assert SECRET not in second.user and SECRET not in second.system
    assert "rejected" not in first.user


def test_p29_s03_nonce_is_fresh_for_every_attempt_including_retries() -> None:
    provider = FakeProvider([JudgeTimeoutError(), JudgeTimeoutError(), good_reply()])
    outcome = evaluate(judge(provider, limits=JudgeLimits(max_attempts=3)))
    assert isinstance(outcome, EvaluationResult)
    nonces = [
        re.search(r"<<<BEGIN ([0-9a-f]{16})", c.user).group(1) for c in provider.calls
    ]  # type: ignore[union-attr]
    assert len(set(nonces)) == 3


# ------------------------------------------------------------------ S03-AC05


def test_p29_s03_ac05_token_budget_refuses_before_any_call() -> None:
    provider = FakeProvider(
        [ProviderReply(good_reply(), input_tokens=60, output_tokens=60)] * 3,
        reports_tokens=True,
    )
    j = judge(provider, budget=JudgeBudget(max_tokens_per_window=100))
    assert isinstance(evaluate(j), EvaluationResult)  # 120 >= 100 after this call
    assert provider.call_count == 1
    outcome = evaluate(j)
    assert isinstance(outcome, EvaluationExecutionFailure)
    assert outcome.exception_type == "JudgeBudgetExceededError"
    assert provider.call_count == 1  # refused before any provider call (R13)


def test_p29_s03_ac05_only_provider_reported_tokens_count() -> None:
    clock = [1000.0]
    tracker = BudgetTracker(
        JudgeBudget(max_tokens_per_window=10), clock=lambda: clock[0]
    )
    tracker.record(None, None)
    tracker.record(0, 0)
    assert tracker.totals() == (0, Decimal(0))
    tracker.record(4, None)
    tracker.record(None, 5)
    assert tracker.totals()[0] == 9
    tracker.check()
    tracker.record(1, 0)
    with pytest.raises(JudgeBudgetExceededError):
        tracker.check()


def test_p29_s03_ac05_window_slides() -> None:
    clock = [1000.0]
    tracker = BudgetTracker(
        JudgeBudget(window_seconds=10, max_tokens_per_window=5), clock=lambda: clock[0]
    )
    tracker.record(5, 0)
    with pytest.raises(JudgeBudgetExceededError):
        tracker.check()
    clock[0] += 9
    with pytest.raises(JudgeBudgetExceededError):
        tracker.check()
    clock[0] += 2  # the entry is now outside the 10 s window
    tracker.check()
    assert tracker.totals()[0] == 0


def test_p29_s03_ac05_monetary_budget_uses_exact_decimals() -> None:
    budget = JudgeBudget(
        max_cost_per_window=Decimal("0.0030"),
        input_price_per_1k_tokens=Decimal("0.001"),
        output_price_per_1k_tokens=Decimal("0.002"),
    )
    tracker = BudgetTracker(budget)
    tracker.record(1000, 0)  # 0.001
    tracker.record(0, 500)  # 0.001
    assert tracker.totals()[1] == Decimal("0.002")
    tracker.check()
    tracker.record(1000, 0)  # 0.003
    with pytest.raises(JudgeBudgetExceededError):
        tracker.check()


def test_p29_s03_ac05_budget_requires_token_reporting_provider() -> None:
    with pytest.raises(ValueError, match="reports_tokens"):
        judge(FakeProvider([]), budget=JudgeBudget(max_tokens_per_window=10))
    cost = JudgeBudget(
        max_cost_per_window=Decimal("1"),
        input_price_per_1k_tokens=Decimal("1"),
        output_price_per_1k_tokens=Decimal("1"),
    )
    with pytest.raises(ValueError, match="reports_tokens"):
        judge(FakeProvider([]), budget=cost)
    judge(FakeProvider([], reports_tokens=True), budget=cost)
    judge(FakeProvider([]), budget=JudgeBudget())  # nothing enforced: no requirement
    with pytest.raises(TypeError):
        judge(FakeProvider([]), budget="1000")  # type: ignore[arg-type]


def test_p29_s03_ac05_budget_is_checked_before_every_attempt_and_shared() -> None:
    tracker = BudgetTracker(JudgeBudget(max_tokens_per_window=50))
    provider = FakeProvider(
        [ProviderReply("garbage", input_tokens=30, output_tokens=30), good_reply()],
        reports_tokens=True,
    )
    j = judge(provider, budget=tracker)
    outcome = evaluate(j)  # first reply is invalid; the re-ask is refused by the budget
    assert isinstance(outcome, EvaluationExecutionFailure)
    assert outcome.exception_type == "JudgeBudgetExceededError"
    assert provider.call_count == 1
    other = judge(FakeProvider([good_reply()], reports_tokens=True), budget=tracker)
    again = evaluate(other)
    assert isinstance(again, EvaluationExecutionFailure)  # the budget is shared


def test_p29_s03_stats_sum_provider_reported_tokens() -> None:
    provider = FakeProvider(
        [
            ProviderReply("garbage", input_tokens=10, output_tokens=2),
            ProviderReply(good_reply(), input_tokens=11, output_tokens=None),
        ],
        reports_tokens=True,
    )
    j = judge(provider, budget=JudgeBudget(max_tokens_per_window=1000))
    result = asyncio.run(j.evaluate_detailed(grounded_request()))
    assert result.stats.attempts == 2 and result.stats.repairs == 1
    assert (result.stats.input_tokens, result.stats.output_tokens) == (21, 2)
    unreported = asyncio.run(
        judge(FakeProvider([good_reply()])).evaluate_detailed(grounded_request())
    )
    assert (
        unreported.stats.input_tokens is None and unreported.stats.output_tokens is None
    )
    assert unreported.stats.latency_ms >= 0


def test_p29_s03_capture_reason_only_when_enabled() -> None:
    reply = judge_reply("pass", "supported_by_context", "high", [0], reason="because")
    off = asyncio.run(
        judge(FakeProvider([reply])).evaluate_detailed(grounded_request())
    )
    on = asyncio.run(
        judge(
            FakeProvider([reply]), policy=JudgePolicy(capture_reason=True)
        ).evaluate_detailed(grounded_request())
    )
    assert off.reason_text is None and on.reason_text == "because"
    assert "because" not in repr(on)


# ------------------------------------------------------------------ S03-AC06


class _Collect(DiagnosticHandler):
    def __init__(self) -> None:
        self.seen: list[BaseException] = []

    def handle(self, diagnostic: SdkDiagnostic) -> None:
        self.seen.append(diagnostic.exception)


def _chain(exc: BaseException | None) -> list[BaseException]:
    chain: list[BaseException] = []
    while exc is not None and exc not in chain:
        chain.append(exc)
        exc = exc.__cause__ or exc.__context__
    return chain


def _hostile_provider_exceptions() -> list[Exception]:
    class Echo(Exception):
        pass

    try:
        try:
            raise ValueError("inner " + SECRET)
        except ValueError as inner:
            raise Echo("provider echoed prompt: " + SECRET) from inner
    except Echo as chained:
        return [
            chained,
            RuntimeError(SECRET),
            TimeoutError(SECRET),
            JudgeProviderError(),
        ]


@pytest.mark.parametrize("index", range(4))
def test_p29_s03_ac06_no_text_or_chain_in_raised_errors(index: int) -> None:
    exc = _hostile_provider_exceptions()[index]
    request = grounded_request(answer=SECRET, context=(SECRET, "c"), question=SECRET)
    j = judge(FakeProvider([exc, exc]), limits=JudgeLimits(max_attempts=2))
    with pytest.raises(JudgeError) as caught:
        asyncio.run(j.evaluate(request))
    raised = caught.value
    for link in _chain(raised):
        assert SECRET not in str(link) and SECRET not in repr(link)
        assert SECRET not in "".join(map(str, link.args))
    assert raised.__cause__ is None
    assert raised.__context__ is None
    assert raised.__suppress_context__ is True
    assert type(raised).__name__ in FAILURE_CLASS_NAMES


def test_p29_s03_ac06_invalid_output_error_carries_no_reply_text() -> None:
    j = judge(FakeProvider(["junk " + SECRET] * 2))
    with pytest.raises(JudgeInvalidOutputError) as caught:
        asyncio.run(j.evaluate(grounded_request(answer=SECRET)))
    assert SECRET not in str(caught.value) and SECRET not in repr(caught.value)
    assert caught.value.__context__ is None and caught.value.__cause__ is None


def test_p29_s03_ac06_diagnostic_handler_receives_only_the_clean_error() -> None:
    handler = _Collect()
    runner = EvaluatorRunner(diagnostic_handler=handler)
    j = judge(FakeProvider([RuntimeError(SECRET)]))
    outcome = asyncio.run(
        runner.evaluate_async(j, grounded_request(answer=SECRET, context=(SECRET,)))
    )
    assert isinstance(outcome, EvaluationExecutionFailure)
    (seen,) = handler.seen
    assert (
        SECRET not in str(seen) and seen.__cause__ is None and seen.__context__ is None
    )


def test_p29_s03_ac06_default_logging_has_no_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    j = judge(FakeProvider([RuntimeError(SECRET)]))
    evaluate(j, grounded_request(answer=SECRET))
    assert SECRET not in caplog.text


def test_p29_s03_ac06_retain_cause_is_opt_in() -> None:
    boom = RuntimeError("provider detail")
    j = judge(FakeProvider([boom]), retain_cause=True)
    with pytest.raises(JudgeProviderError) as caught:
        asyncio.run(j.evaluate(grounded_request()))
    assert caught.value.__cause__ is boom  # documented opt-in
    assert caught.value.__context__ is None
    default = judge(FakeProvider([RuntimeError("x")]))
    with pytest.raises(JudgeProviderError) as plain:
        asyncio.run(default.evaluate(grounded_request()))
    assert plain.value.__cause__ is None


def test_p29_s03_ac06_provider_error_subclass_messages_are_replaced() -> None:
    class Chatty(JudgeProviderUnavailableError):
        def __init__(self) -> None:
            Exception.__init__(self, "prompt echo " + SECRET)

    j = judge(FakeProvider([Chatty(), Chatty()]))
    with pytest.raises(JudgeProviderUnavailableError) as caught:
        asyncio.run(j.evaluate(grounded_request()))
    assert SECRET not in str(caught.value)
    assert type(caught.value) is JudgeProviderUnavailableError


def test_p29_s03_provider_returning_wrong_type_is_a_provider_error() -> None:
    async def fn(call: Any) -> Any:
        return "just a string"

    j = judge(CallableProvider(fn, provider_label="bad"))
    outcome = evaluate(j)
    assert isinstance(outcome, EvaluationExecutionFailure)
    assert outcome.exception_type == "JudgeProviderError"


# ------------------------------------------------------------------ S03-AC07


def test_p29_s03_ac07_only_rubric_roles_reach_the_provider() -> None:
    request = EvaluationRequest(
        JudgeDimension.ANSWER_CORRECTNESS,
        (
            ContentPart(ContentRole.QUESTION, "OPTIONAL_QUESTION"),
            ContentPart(ContentRole.REFERENCE, "REQUIRED_REFERENCE"),
            ContentPart(ContentRole.ANSWER, "THE_ANSWER"),
            ContentPart(ContentRole.POLICY, "NOT_ALLOWED_POLICY"),
            ContentPart(ContentRole.CONTEXT, "NOT_ALLOWED_CONTEXT"),
            ContentPart(ContentRole.TASK_EVIDENCE, "NOT_ALLOWED_EVIDENCE"),
            ContentPart(ContentRole.INSTRUCTIONS, "NOT_ALLOWED_INSTRUCTIONS"),
        ),
        correlation_id="CORRELATION_ID_VALUE",
    )
    provider = FakeProvider([judge_reply("pass", "consistent_with_reference", "high")])
    j = judge(provider, rubric=AC)
    assert isinstance(evaluate(j, request), EvaluationResult)
    (call,) = provider.calls
    text = call.system + call.user
    for kept in ("OPTIONAL_QUESTION", "REQUIRED_REFERENCE", "THE_ANSWER"):
        assert kept in call.user
    for dropped in (
        "NOT_ALLOWED_POLICY",
        "NOT_ALLOWED_CONTEXT",
        "NOT_ALLOWED_EVIDENCE",
        "NOT_ALLOWED_INSTRUCTIONS",
        "CORRELATION_ID_VALUE",
    ):
        assert dropped not in text
    assert call.max_output_tokens == 256 and call.json_output is True


def test_p29_s03_ac07_dropped_roles_do_not_count_toward_input_limit() -> None:
    request = EvaluationRequest(
        JudgeDimension.ANSWER_CORRECTNESS,
        (
            ContentPart(ContentRole.REFERENCE, "ref"),
            ContentPart(ContentRole.ANSWER, "a"),
            ContentPart(ContentRole.POLICY, "p" * 500),
        ),
    )
    provider = FakeProvider([judge_reply("pass", "consistent_with_reference", "high")])
    j = judge(provider, rubric=AC, limits=JudgeLimits(max_input_chars=4))
    assert isinstance(evaluate(j, request), EvaluationResult)


# ------------------------------------------------------------------ S03-AC08


def test_p29_s03_ac08_input_limit_at_boundary_and_beyond_never_truncates() -> None:
    request = grounded_request(
        answer="12345", context=("123",), question=None
    )  # 8 chars
    provider = FakeProvider([good_reply(), good_reply()])
    at = judge(provider, limits=JudgeLimits(max_input_chars=8))
    assert isinstance(evaluate(at, request), EvaluationResult)
    below = judge(provider, limits=JudgeLimits(max_input_chars=7))
    outcome = evaluate(below, request)
    assert isinstance(outcome, EvaluationExecutionFailure)
    assert outcome.exception_type == "JudgeInputLimitError"
    assert provider.call_count == 1
    with pytest.raises(JudgeInputLimitError):
        asyncio.run(below.evaluate(request))
    sent = provider.calls[0].user
    assert "12345" in sent and "123" in sent  # the accepted call was not truncated


def test_p29_s03_ac08_repeats_multiply_provider_calls_exactly() -> None:
    for repeats in (1, 2, 3):
        provider = FakeProvider([good_reply()] * repeats)
        j = judge(provider, policy=JudgePolicy(repeats=repeats))
        outcome = evaluate(j)
        assert isinstance(outcome, EvaluationResult)
        assert provider.call_count == repeats
        assert j.identity.configuration_id is not None
        assert f".rp{repeats}." in j.identity.configuration_id


def test_p29_s03_ac08_repeat_disagreement_and_no_partial_credit() -> None:
    fail = judge_reply("fail", "unsupported_claim", "high", [])
    j = judge(FakeProvider([good_reply(), fail]), policy=JudgePolicy(repeats=2))
    outcome = evaluate(j)
    assert isinstance(outcome, EvaluationResult)
    assert outcome.outcome is EvaluationOutcome.UNKNOWN
    assert outcome.reason_code == "groundedness.judge_disagreement"
    broken = judge(
        FakeProvider([good_reply(), RuntimeError("x")]), policy=JudgePolicy(repeats=2)
    )
    failure = evaluate(broken)
    assert isinstance(failure, EvaluationExecutionFailure)
    assert failure.exception_type == "JudgeProviderError"


def test_p29_s03_policy_min_confidence_overrides_rubric_and_is_in_identity() -> None:
    medium = judge_reply("pass", "supported_by_context", "medium", [0])
    default = judge(FakeProvider([medium]))
    strict = judge(
        FakeProvider([medium]), policy=JudgePolicy(min_confidence=Confidence.HIGH)
    )
    assert evaluate(default).outcome is EvaluationOutcome.PASS
    outcome = evaluate(strict)
    assert outcome.outcome is EvaluationOutcome.UNKNOWN
    assert outcome.reason_code == "groundedness.low_confidence"
    assert strict.identity.configuration_id is not None
    assert ".mc-high." in strict.identity.configuration_id


def test_p29_s03_precheck_makes_no_provider_call() -> None:
    provider = FakeProvider([good_reply()])
    request = grounded_request(context=("",))
    outcome = evaluate(judge(provider), request)
    assert isinstance(outcome, EvaluationResult)
    assert outcome.outcome is EvaluationOutcome.UNKNOWN
    assert outcome.reason_code == "groundedness.context_insufficient"
    assert provider.call_count == 0


def test_p29_s03_runner_is_unchanged_by_the_judge() -> None:
    import hashlib
    import pathlib

    import agent_reliability.sdk.evaluator_runner as module

    digest = hashlib.sha256(pathlib.Path(module.__file__).read_bytes()).hexdigest()
    assert digest == "d4354eca6fc23629ebd65b8232791f34682a02568b4b4934b3eb9f6ca841de59"

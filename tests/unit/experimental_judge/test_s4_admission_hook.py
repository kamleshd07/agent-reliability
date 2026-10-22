"""Session 4: the calibration-agnostic admission hook of the judge coordinator.

The hook is generic: it knows nothing about calibration. These tests pin its
contract: binding-time evaluator check, per-call decision, fail-closed behaviour,
ordering with the run-not-recording check and sampling, no provider call and no
evidence on a skip, unchanged run health, and the counters.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_reliability.domain.measurement_health import MeasurementHealth
from agent_reliability.experimental.judge import (
    UNGATED,
    AdmissionVerdict,
    EvaluationDisposition,
    EvidenceAdmission,
    IndicatorBinding,
    JudgeCoordinator,
    JudgeInvocationReport,
    SamplingPolicy,
    SyncLLMJudge,
)
from agent_reliability.experimental.judge.testing import FakeSyncProvider
from agent_reliability.ports.events import EvaluationRecorded
from agent_reliability.sdk import AgentReliability
from tests.fakes.p29_judge import (
    HealthSink,
    good_reply,
    grounded_request,
    named_rubrics,
)

pytestmark = pytest.mark.unit

GR = named_rubrics()["gr-cit"]


def make_judge(replies: int = 3) -> tuple[SyncLLMJudge, FakeSyncProvider]:
    provider = FakeSyncProvider([good_reply() for _ in range(replies)])
    return SyncLLMJudge(rubric=GR, provider=provider, model_label="adm"), provider


class Script:
    """A scripted admission: returns the next verdict, or raises it."""

    def __init__(self, evaluator: Any, *verdicts: Any) -> None:
        self.evaluator = evaluator
        self.verdicts = list(verdicts)
        self.calls = 0

    def bound_to(self, evaluator: Any) -> bool:
        return evaluator is self.evaluator

    def decide(self, indicator: str, evaluator: Any) -> AdmissionVerdict:
        self.calls += 1
        item = self.verdicts[min(self.calls - 1, len(self.verdicts) - 1)]
        if isinstance(item, BaseException):
            raise item
        return item  # type: ignore[no-any-return]


class Collect:
    def __init__(self) -> None:
        self.reports: list[JudgeInvocationReport] = []

    def on_report(self, report: JudgeInvocationReport) -> None:
        self.reports.append(report)


def run_once(
    coordinator: JudgeCoordinator,
) -> tuple[EvaluationDisposition, HealthSink, MeasurementHealth]:
    sink = HealthSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    with (
        sdk.run(agent_id="a", name="Agent", version="1") as run,
        coordinator.scope(run) as scope,
    ):
        disposition = scope.evaluate_sync("groundedness", grounded_request())
    return disposition, sink, run.measurement_health.health


def recorded(sink: HealthSink) -> list[EvaluationRecorded]:
    return [e for e in sink.events if isinstance(e, EvaluationRecorded)]


def test_protocol_is_runtime_checkable() -> None:
    judge, _ = make_judge()
    assert isinstance(Script(judge, AdmissionVerdict.allow()), EvidenceAdmission)


def test_binding_rejects_an_admission_made_for_another_evaluator() -> None:
    judge_x, _ = make_judge()
    judge_y, _ = make_judge()
    gate_for_x = Script(judge_x, AdmissionVerdict.allow())
    IndicatorBinding("groundedness", judge_x, admission=gate_for_x)
    with pytest.raises(ValueError, match="not bound"):
        IndicatorBinding("groundedness", judge_y, admission=gate_for_x)


def test_binding_rejects_a_non_admission_object() -> None:
    judge, _ = make_judge()
    with pytest.raises(TypeError):
        IndicatorBinding("groundedness", judge, admission=object())


def test_a_skip_makes_no_provider_call_records_nothing_and_keeps_run_health() -> None:
    judge, provider = make_judge()
    gate = Script(judge, AdmissionVerdict.skip("calibration_expired"))
    observer = Collect()
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge, admission=gate)], observer=observer
    )
    disposition, sink, health = run_once(coordinator)
    assert disposition is EvaluationDisposition.SKIPPED_BY_ADMISSION
    assert provider.call_count == 0
    assert recorded(sink) == []
    # No failure either: an inadmissible judge is not an evaluation failure.
    assert sink.failures == []
    assert health is MeasurementHealth.HEALTHY
    assert [r.kind for r in observer.reports] == ["skipped_admission"]
    assert observer.reports[0].reason_code == "calibration_expired"
    coverage = coordinator.coverage().indicators[0]
    assert coverage.admission_skipped == 1
    assert (
        coverage.attempted == 0
    )  # a skip is not an attempt, reliability is unaffected
    assert coverage.reliability is None


def test_an_allowed_call_behaves_exactly_like_an_unset_admission() -> None:
    judge, provider = make_judge()
    gate = Script(judge, AdmissionVerdict.allow())
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge, admission=gate)]
    )
    disposition, sink, _ = run_once(coordinator)
    assert disposition is EvaluationDisposition.RECORDED_RESULT
    assert provider.call_count == 1
    assert len(recorded(sink)) == 1
    assert coordinator.coverage().indicators[0].admission_skipped == 0


def test_the_decision_is_made_on_every_call_so_expiry_takes_effect() -> None:
    judge, _ = make_judge()
    gate = Script(
        judge,
        AdmissionVerdict.allow(),
        AdmissionVerdict.skip("calibration_expired"),
    )
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge, admission=gate)]
    )
    first, _, _ = run_once(coordinator)
    second, _, _ = run_once(coordinator)
    assert first is EvaluationDisposition.RECORDED_RESULT
    assert second is EvaluationDisposition.SKIPPED_BY_ADMISSION
    assert gate.calls == 2


@pytest.mark.parametrize(
    "item", [RuntimeError("SECRET-in-message"), ValueError("x"), "not a verdict", None]
)
def test_a_failing_or_malformed_hook_fails_closed_without_leaking(item: Any) -> None:
    judge, provider = make_judge()
    gate = Script(judge, item)
    observer = Collect()
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge, admission=gate)], observer=observer
    )
    disposition, sink, _ = run_once(coordinator)
    assert disposition is EvaluationDisposition.SKIPPED_BY_ADMISSION
    assert provider.call_count == 0 and recorded(sink) == []
    assert observer.reports[0].reason_code == "admission_error"
    assert "SECRET" not in repr(observer.reports[0])


def test_a_base_exception_from_the_hook_propagates() -> None:
    judge, _ = make_judge()
    gate = Script(judge, KeyboardInterrupt())
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge, admission=gate)]
    )
    with pytest.raises(KeyboardInterrupt):
        run_once(coordinator)


def test_admission_is_applied_before_sampling_and_after_run_not_recording() -> None:
    judge, provider = make_judge()
    skip = Script(judge, AdmissionVerdict.skip("calibration_expired"))
    sampled_out = SamplingPolicy(rate=0.0)
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge, sampled_out, skip)]
    )
    disposition, _, _ = run_once(coordinator)
    # Sampling would also have dropped it, but admission is reported first and counted.
    assert disposition is EvaluationDisposition.SKIPPED_BY_ADMISSION
    coverage = coordinator.coverage().indicators[0]
    assert (coverage.admission_skipped, coverage.unsampled) == (1, 0)
    assert provider.call_count == 0


def test_a_non_recording_run_is_reported_as_such_not_as_an_admission_skip() -> None:
    judge, _ = make_judge()
    gate = Script(judge, AdmissionVerdict.skip("calibration_expired"))
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge, admission=gate)]
    )

    class BadIds:
        def generate(self) -> str:
            raise RuntimeError("no ids")

    sdk = AgentReliability(run_id_generator=BadIds())  # type: ignore[arg-type]
    with (
        sdk.run(agent_id="a", name="Agent", version="1") as run,
        coordinator.scope(run) as scope,
    ):
        disposition = scope.evaluate_sync("groundedness", grounded_request())
    assert disposition is EvaluationDisposition.SKIPPED_RUN_NOT_RECORDING
    assert coordinator.coverage().indicators[0].admission_skipped == 0


def test_ungated_counters_separate_unset_from_explicit_choice() -> None:
    judge_none, _ = make_judge()
    judge_explicit, _ = make_judge()
    coordinator = JudgeCoordinator(
        [
            IndicatorBinding("groundedness", judge_none),
            IndicatorBinding("answer-correctness", judge_explicit, admission=UNGATED),
        ]
    )
    sink = HealthSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    with (
        sdk.run(agent_id="a", name="Agent", version="1") as run,
        coordinator.scope(run) as scope,
    ):
        scope.evaluate_sync("groundedness", grounded_request())
    by_name = {c.indicator: c for c in coordinator.coverage().indicators}
    assert by_name["groundedness"].ungated_model_backed == 1
    assert by_name["groundedness"].explicitly_ungated == 0
    assert by_name["answer-correctness"].ungated_model_backed == 0
    assert coordinator.coverage().total.ungated_model_backed == 1


def test_verdict_validation() -> None:
    assert AdmissionVerdict.allow().allowed is True
    for bad in ("", "Has-Caps", "x" * 65, "1abc", None):
        with pytest.raises(ValueError):
            AdmissionVerdict.skip(bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        AdmissionVerdict(True, "reason")


# ---------------------------------------------------------------- the async paths


def _async_judge():  # type: ignore[no-untyped-def]
    from agent_reliability.experimental.judge import LLMJudge
    from agent_reliability.experimental.judge.testing import FakeProvider

    provider = FakeProvider([good_reply(), good_reply()])
    judge = LLMJudge(
        rubric=GR, provider=provider, model_label="adm-async", jitter=lambda: 0.0
    )
    return judge, provider


def test_the_async_evaluate_path_honours_the_hook() -> None:
    import asyncio

    judge, provider = _async_judge()
    gate = Script(
        judge, AdmissionVerdict.skip("calibration_expired"), AdmissionVerdict.allow()
    )
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge, admission=gate)]
    )
    sink = HealthSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]

    async def go() -> list[EvaluationDisposition]:
        out = []
        for _ in range(2):  # two runs: first skipped, second allowed
            with sdk.run(agent_id="a", name="Agent", version="1") as run:
                async with coordinator.scope(run) as scope:
                    out.append(await scope.evaluate("groundedness", grounded_request()))
        return out

    first, second = asyncio.run(go())
    assert first is EvaluationDisposition.SKIPPED_BY_ADMISSION
    assert second is EvaluationDisposition.RECORDED_RESULT
    assert provider.call_count == 1  # only the admitted run reached the provider


def test_the_submit_path_honours_the_hook_and_fails_closed() -> None:
    import asyncio

    judge, provider = _async_judge()
    gate = Script(judge, RuntimeError("boom"))
    observer = Collect()
    coordinator = JudgeCoordinator(
        [IndicatorBinding("groundedness", judge, admission=gate)], observer=observer
    )
    sink = HealthSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]

    async def go() -> None:
        with sdk.run(agent_id="a", name="Agent", version="1") as run:
            async with coordinator.scope(run) as scope:
                scope.submit("groundedness", grounded_request())

    asyncio.run(go())
    assert provider.call_count == 0 and recorded(sink) == []
    assert [r.reason_code for r in observer.reports] == ["admission_error"]
    assert coordinator.coverage().indicators[0].admission_skipped == 1

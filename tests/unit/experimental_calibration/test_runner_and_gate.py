"""The runner (scripted provider, no network) and the coordinator gate end to end."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from agent_reliability.domain.measurement_health import MeasurementHealth
from agent_reliability.experimental.calibration import (
    CalibrationGate,
    CalibrationStatus,
    JudgeFingerprint,
    Outcome,
    Split,
    build_assessment,
    collect_judgments,
    collect_judgments_async,
    repeatability,
)
from agent_reliability.experimental.judge import (
    EvaluationDisposition,
    IndicatorBinding,
    JudgeCoordinator,
    JudgeLimits,
    JudgeProviderRateLimitedError,
    JudgeTimeoutError,
    LLMJudge,
    SyncLLMJudge,
)
from agent_reliability.experimental.judge.testing import (
    FakeProvider,
    FakeSyncProvider,
    judge_reply,
)
from agent_reliability.sdk import AgentReliability
from tests.fakes.p29_calibration import (
    CANARY,
    KEY,
    MODEL,
    NOW,
    RUBRIC,
    case_doc,
    heldout_cases,
    human_policy,
    load,
    perfect_outcomes,
    table,
)
from tests.fakes.p29_judge import HealthSink

pytestmark = pytest.mark.unit

PASS = judge_reply("pass", "consistent_with_reference", "high")
FAIL = judge_reply("fail", "contradicts_reference", "medium")
UNKNOWN = judge_reply("unknown", "reference_insufficient", "low")
ONE_SHOT = JudgeLimits(max_attempts=1, repair_attempts=0)


def recorded(sink: HealthSink) -> list[Any]:
    from agent_reliability.ports.events import EvaluationRecorded

    return [e for e in sink.events if isinstance(e, EvaluationRecorded)]


def sync_judge(script: list[Any], label: str = "local-a") -> SyncLLMJudge:
    return SyncLLMJudge(
        rubric=RUBRIC,
        provider=FakeSyncProvider(script),
        model_label=label,
        limits=ONE_SHOT,
        jitter=lambda: 0.0,
    )


# ----------------------------------------------------------------- the runner


def test_the_runner_tabulates_every_run_and_classifies_failures(tmp_path: Path) -> None:
    ds = load(
        tmp_path,
        {
            "heldout": [
                case_doc("a", "pass"),
                case_doc("b", "fail"),
                case_doc("c", "fail"),
            ]
        },
    )
    script = [
        PASS, FAIL,  # a: run 0, 1
        FAIL, UNKNOWN,  # b
        JudgeTimeoutError(), JudgeProviderRateLimitedError(),  # c: both fail
    ]  # fmt: skip
    judge = sync_judge(script)
    t = collect_judgments(judge, MODEL, ds.cases(Split.HELDOUT), repetitions=2)
    assert [(r.example_id, r.run_index, r.outcome.value) for r in t.rows] == [
        ("a", 0, "PASS"), ("a", 1, "FAIL"), ("b", 0, "FAIL"), ("b", 1, "UNKNOWN"),
        ("c", 0, "FAILURE"), ("c", 1, "FAILURE"),
    ]  # fmt: skip
    assert {r.failure_class for r in t.rows if r.outcome is Outcome.FAILURE} == {
        "JudgeTimeoutError",
        "JudgeProviderRateLimitedError",
    }
    assert t.row("a", 0).confidence_level == "high"  # type: ignore[union-attr]
    assert t.fingerprint.model == MODEL
    assert t.outcome("c", 3) is Outcome.MISSING  # derived, never stored
    rep = repeatability(ds.cases(Split.HELDOUT), t)
    assert rep["unstable"] == 2 and rep["excluded_for_failures"] == 1


def test_provider_error_text_never_reaches_the_table(tmp_path: Path) -> None:
    ds = load(tmp_path, {"heldout": [case_doc("a")]})

    class Noisy(Exception):
        pass

    judge = sync_judge([Noisy(f"provider said {CANARY}")])
    t = collect_judgments(judge, MODEL, ds.cases(Split.HELDOUT))
    assert CANARY not in repr(t) and CANARY not in str(t.rows)


def test_non_judge_exceptions_propagate_instead_of_being_swallowed(
    tmp_path: Path,
) -> None:
    ds = load(tmp_path, {"heldout": [case_doc("a")]})
    judge = sync_judge([PASS])
    judge._engine = None  # type: ignore[assignment]  # break the judge itself
    with pytest.raises(AttributeError):
        collect_judgments(judge, MODEL, ds.cases(Split.HELDOUT))


def test_the_runner_validates_its_inputs(tmp_path: Path) -> None:
    ds = load(tmp_path, {"heldout": [case_doc("a")]})
    cases = ds.cases(Split.HELDOUT)
    judge = sync_judge([PASS] * 3)
    for kwargs in ({"repetitions": 0}, {"repetitions": 11}, {"repetitions": True}):
        with pytest.raises(ValueError):
            collect_judgments(judge, MODEL, cases, **kwargs)
    with pytest.raises(ValueError):
        collect_judgments(judge, MODEL, ())
    with pytest.raises(ValueError, match="unique"):
        collect_judgments(judge, MODEL, (cases[0], cases[0]))


def test_the_async_runner_matches_the_sync_runner(tmp_path: Path) -> None:
    ds = load(tmp_path, {"heldout": [case_doc("a", "pass"), case_doc("b", "fail")]})
    script = [PASS, FAIL]
    sync = collect_judgments(sync_judge(list(script)), MODEL, ds.cases(Split.HELDOUT))
    judge = LLMJudge(
        rubric=RUBRIC, provider=FakeProvider(list(script)), model_label="local-a",
        limits=ONE_SHOT, jitter=lambda: 0.0,
    )  # fmt: skip
    got = asyncio.run(collect_judgments_async(judge, MODEL, ds.cases(Split.HELDOUT)))
    assert got.rows == sync.rows
    assert got.fingerprint.behaviour_digest == sync.fingerprint.behaviour_digest


def test_end_to_end_offline_scripted_judge_to_status(tmp_path: Path) -> None:
    """Dataset -> scripted judge -> assessment -> policy -> status, no network."""
    docs = heldout_cases(provenance="human_multi", multi=True)
    ds = load(tmp_path, {"heldout": docs}, provenance={"heldout": "human_multi"})
    cases = ds.cases(Split.HELDOUT)
    script = []
    for case in cases:  # three runs each, always the right verdict
        script += [FAIL if case.human_label == "fail" else PASS] * 3
    judge = sync_judge(script)
    t = collect_judgments(judge, MODEL, cases, repetitions=3)
    a = build_assessment(ds, Split.HELDOUT, t, now=NOW - timedelta(days=1))
    gate = CalibrationGate(judge, MODEL, a, human_policy(), clock=lambda: NOW)
    assert gate.decision().status is CalibrationStatus.CALIBRATED
    assert CANARY not in a.to_json()


# ------------------------------------------------------------------- the gate


def _calibrated_setup(tmp_path: Path) -> tuple[SyncLLMJudge, Any, Any]:
    ds = load(
        tmp_path,
        {"heldout": heldout_cases(provenance="human_multi", multi=True)},
        provenance={"heldout": "human_multi"},
    )
    outcomes = {k: [v] * 3 for k, v in perfect_outcomes(ds).items()}
    judge = sync_judge([PASS, PASS, PASS, PASS])
    fp = JudgeFingerprint.for_evaluator(judge, MODEL)
    a = build_assessment(
        ds, Split.HELDOUT, table(outcomes, fp=fp), now=NOW - timedelta(days=1)
    )
    return judge, a, ds


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self):  # type: ignore[no-untyped-def]
        return self.now


def _run(
    coordinator: JudgeCoordinator, request
) -> tuple[EvaluationDisposition, HealthSink, MeasurementHealth]:  # type: ignore[no-untyped-def]
    sink = HealthSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    with (
        sdk.run(agent_id="a", name="Agent", version="1") as run,
        coordinator.scope(run) as scope,
    ):
        disposition = scope.evaluate_sync("answer-correctness", request)
    return disposition, sink, run.measurement_health.health


def test_a_calibrated_gate_lets_evidence_through_and_an_expired_one_stops_it(
    tmp_path: Path,
) -> None:
    judge, assessment, ds = _calibrated_setup(tmp_path)
    clock = Clock()
    gate = CalibrationGate(judge, MODEL, assessment, human_policy(), clock=clock)
    coordinator = JudgeCoordinator(
        [IndicatorBinding("answer-correctness", judge, admission=gate)]
    )
    request = ds.cases(Split.HELDOUT)[0].case.request()
    first, sink, _ = _run(coordinator, request)
    assert first is EvaluationDisposition.RECORDED_RESULT and len(recorded(sink)) == 1

    clock.now = assessment.created_at + timedelta(
        days=91
    )  # a long-lived gate, moving clock
    second, sink2, health = _run(coordinator, request)
    assert second is EvaluationDisposition.SKIPPED_BY_ADMISSION
    assert recorded(sink2) == [] and sink2.failures == []  # no evidence, no failure
    assert health is MeasurementHealth.HEALTHY  # an inadmissible judge is not an outage
    coverage = coordinator.coverage().indicators[0]
    assert coverage.admission_skipped == 1 and coverage.attempted == 1
    assert gate.decision().status is CalibrationStatus.CALIBRATION_EXPIRED


def test_a_gate_cannot_be_attached_to_a_different_judge(tmp_path: Path) -> None:
    judge_x, assessment, _ = _calibrated_setup(tmp_path)
    judge_y = sync_judge(
        [PASS], label="local-a"
    )  # identical configuration, other object
    gate_for_x = CalibrationGate(
        judge_x, MODEL, assessment, human_policy(), clock=Clock()
    )
    with pytest.raises(ValueError, match="not bound"):
        IndicatorBinding("answer-correctness", judge_y, admission=gate_for_x)


def test_a_judge_with_other_behaviour_is_skipped_as_incompatible_not_admitted(
    tmp_path: Path,
) -> None:
    _, assessment, ds = _calibrated_setup(tmp_path)
    changed = sync_judge([PASS], label="local-b")  # different configuration_id
    gate = CalibrationGate(changed, MODEL, assessment, human_policy(), clock=Clock())
    assert gate.decision().status is CalibrationStatus.INCOMPATIBLE
    coordinator = JudgeCoordinator(
        [IndicatorBinding("answer-correctness", changed, admission=gate)]
    )
    disposition, sink, _ = _run(coordinator, ds.cases(Split.HELDOUT)[0].case.request())
    assert (
        disposition is EvaluationDisposition.SKIPPED_BY_ADMISSION
        and recorded(sink) == []
    )


def test_an_uncalibrated_judge_is_skipped_when_gated_and_counted_when_not(
    tmp_path: Path,
) -> None:
    judge, _, ds = _calibrated_setup(tmp_path)
    request = ds.cases(Split.HELDOUT)[0].case.request()
    gate = CalibrationGate(judge, MODEL, None, human_policy(), clock=Clock())
    gated = JudgeCoordinator(
        [IndicatorBinding("answer-correctness", judge, admission=gate)]
    )
    assert _run(gated, request)[0] is EvaluationDisposition.SKIPPED_BY_ADMISSION

    ungated_judge = sync_judge([PASS])
    ungated = JudgeCoordinator([IndicatorBinding("answer-correctness", ungated_judge)])
    assert _run(ungated, request)[0] is EvaluationDisposition.RECORDED_RESULT
    assert ungated.coverage().indicators[0].ungated_model_backed == 1  # visible locally


def test_a_verified_integrity_policy_refuses_a_gate_without_a_key(
    tmp_path: Path,
) -> None:
    judge, assessment, _ = _calibrated_setup(tmp_path)
    policy = human_policy(require_verified_integrity=True)
    with pytest.raises(ValueError, match="HMAC"):
        CalibrationGate(judge, MODEL, assessment, policy, clock=Clock())
    unsigned = CalibrationGate(
        judge, MODEL, assessment, policy, clock=Clock(), hmac_key=KEY
    )
    assert unsigned.decision().status is CalibrationStatus.UNCALIBRATED
    signed = CalibrationGate(
        judge, MODEL, assessment.sign(KEY), policy, clock=Clock(), hmac_key=KEY
    )
    assert signed.decision().admissible


def test_a_naive_gate_clock_is_refused(tmp_path: Path) -> None:
    from datetime import datetime

    judge, assessment, _ = _calibrated_setup(tmp_path)
    gate = CalibrationGate(
        judge, MODEL, assessment, human_policy(), clock=lambda: datetime(2026, 1, 1)
    )
    with pytest.raises(ValueError, match="aware"):
        gate.decision()

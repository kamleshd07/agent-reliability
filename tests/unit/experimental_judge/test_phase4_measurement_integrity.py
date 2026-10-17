"""Phase 4 measurement integrity (SG-1, SG-3, SG-5 and the documented limits).

Failures are never verdicts, UNKNOWN is never silently PASS, failed attempts are
not coverage, reliability is never shown without coverage and failure rate, and
budget exhaustion and overload are observable. No accuracy or calibration claim
appears in any public document.
"""

from __future__ import annotations

import asyncio
import dataclasses
import pathlib
import re
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.domain.measurement_health import (
    MeasurementHealth,
    MeasurementHealthReason,
    MeasurementHealthReport,
)
from agent_reliability.evaluation import EvaluationDecision
from agent_reliability.experimental.judge import (
    FAILURE_CLASS_NAMES,
    BudgetTracker,
    Confidence,
    CoverageReport,
    IndicatorBinding,
    IndicatorCoverage,
    JudgeBudget,
    JudgeCoordinator,
    JudgeInvocationReport,
    JudgeLimits,
    JudgeProviderRateLimitedError,
    JudgeProviderRefusedError,
    JudgeProviderUnavailableError,
    JudgeTimeoutError,
    LLMJudge,
    ProviderReply,
    ReportComparison,
)
from agent_reliability.experimental.judge.core import (
    ParsedOutput,
    aggregate_repeats,
    map_verdict,
)
from agent_reliability.experimental.judge.testing import FakeProvider, judge_reply
from agent_reliability.ports.events import EvaluationRecorded
from agent_reliability.sdk import AgentReliability
from agent_reliability.sdk.evaluator_runner import EvaluatorRunner
from tests.fakes.p29_judge import (
    HealthSink,
    good_reply,
    grounded_request,
    named_rubrics,
)

pytestmark = pytest.mark.unit

GR = named_rubrics()["gr-cit"]
ROOT = pathlib.Path(__file__).resolve().parents[3]


class Quiet:
    def handle(self, diagnostic: Any) -> None:
        return None


class Collect:
    def __init__(self) -> None:
        self.reports: list[JudgeInvocationReport] = []

    def on_report(self, report: JudgeInvocationReport) -> None:
        self.reports.append(report)


def judge(script: list[Any], **kw: Any) -> LLMJudge:
    return LLMJudge(
        rubric=GR,
        provider=FakeProvider(script, reports_tokens=kw.pop("reports_tokens", False)),
        model_label="integrity",
        jitter=lambda: 0.0,
        **kw,
    )


def run_many(
    bindings: list[IndicatorBinding],
    sink: HealthSink,
    runs: int = 1,
    observer: Any = None,
    **coordinator_kw: Any,
) -> JudgeCoordinator:
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    coordinator = JudgeCoordinator(
        bindings,
        runner=EvaluatorRunner(diagnostic_handler=Quiet()),  # type: ignore[arg-type]
        observer=observer,
        **coordinator_kw,
    )

    async def one(name: str) -> None:
        with sdk.run(agent_id="a", name="A", version="1") as run:
            async with coordinator.scope(run) as scope:
                await scope.evaluate(name, grounded_request())

    async def go() -> None:
        for _ in range(runs):
            for binding in bindings:
                await one(binding.indicator)

    asyncio.run(go())
    return coordinator


# --------------------------------------------- failures never become verdicts


@pytest.mark.parametrize(
    "name", [n for n in FAILURE_CLASS_NAMES if n != "JudgeOverloadedError"]
)
def test_failure_never_becomes_pass_fail_or_unknown(name: str) -> None:
    faults: dict[str, Any] = {
        "JudgeTimeoutError": ([JudgeTimeoutError()] * 2, {}),
        "JudgeProviderUnavailableError": ([JudgeProviderUnavailableError()] * 2, {}),
        "JudgeProviderRateLimitedError": ([JudgeProviderRateLimitedError()] * 2, {}),
        "JudgeProviderRefusedError": ([JudgeProviderRefusedError()], {}),
        "JudgeProviderError": ([RuntimeError("x")], {}),
        "JudgeInvalidOutputError": (["junk", "junk"], {}),
        "JudgeOutputTooLargeError": (["x" * 5000], {}),
        "JudgeInputLimitError": (
            [good_reply()],
            {"limits": JudgeLimits(max_input_chars=2)},
        ),
        "JudgeBudgetExceededError": (
            [ProviderReply(good_reply(), input_tokens=1, output_tokens=1)] * 2,
            {
                "budget": BudgetTracker(JudgeBudget(max_tokens_per_window=1)),
                "reports_tokens": True,
            },
        ),
    }
    sink = HealthSink()
    script, kw = faults[name]
    if name == "JudgeBudgetExceededError":
        kw["budget"].record(1, 0)
    coordinator = run_many(
        [IndicatorBinding("groundedness", judge(script, **kw))], sink
    )
    total = coordinator.coverage().total
    assert dict(total.failures_by_class).get(name, 0) >= 1
    assert (total.passed, total.failed, total.unknown) == (0, 0, 0)
    assert total.execution_failures == total.attempted >= 1
    assert not [e for e in sink.events if isinstance(e, EvaluationRecorded)]
    assert any(f[2] == name for f in sink.failures)  # failure evidence, not an outcome


def test_overload_shedding_is_a_failure_with_evidence_never_a_verdict() -> None:
    sink = HealthSink()
    observer = Collect()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]

    async def go() -> JudgeCoordinator:
        event = asyncio.Event()

        async def hold(call: Any) -> ProviderReply:
            await event.wait()
            return ProviderReply(good_reply())

        from agent_reliability.experimental.judge import CallableProvider

        coordinator = JudgeCoordinator(
            [
                IndicatorBinding(
                    "groundedness",
                    LLMJudge(
                        rubric=GR,
                        provider=CallableProvider(hold, provider_label="h"),
                        model_label="integrity",
                    ),
                )
            ],
            runner=EvaluatorRunner(diagnostic_handler=Quiet()),  # type: ignore[arg-type]
            max_concurrency=1,
            max_pending=1,
            observer=observer,
        )

        async def one() -> None:
            with sdk.run(agent_id="a", name="A", version="1") as run:
                async with coordinator.scope(run) as scope:
                    await scope.evaluate("groundedness", grounded_request())

        tasks = [asyncio.ensure_future(one()) for _ in range(3)]
        for _ in range(30):
            await asyncio.sleep(0)
        event.set()
        await asyncio.gather(*tasks)
        return coordinator

    total = asyncio.run(go()).coverage().total
    assert dict(total.failures_by_class) == {"JudgeOverloadedError": 1}
    assert (total.attempted, total.passed, total.failed, total.unknown) == (3, 2, 0, 0)
    assert [f[2] for f in sink.failures] == ["JudgeOverloadedError"]
    shed = [r for r in observer.reports if r.kind == "failure"]
    assert [r.exception_type for r in shed] == ["JudgeOverloadedError"]
    assert len([e for e in sink.events if isinstance(e, EvaluationRecorded)]) == 2


# ------------------------------------------- UNKNOWN never silently becomes PASS


@given(
    verdict=st.sampled_from(["pass", "fail", "unknown"]),
    confidence=st.sampled_from(list(Confidence)),
    minimum=st.sampled_from(list(Confidence)),
)
def test_pass_only_for_a_confident_pass_verdict(
    verdict: str, confidence: Confidence, minimum: Confidence
) -> None:
    code = {"pass": "supported_by_context", "fail": "unsupported_claim"}.get(
        verdict, "context_insufficient"
    )
    decision = map_verdict(
        ParsedOutput(verdict, code, confidence, ()), "groundedness", minimum
    )
    if decision.outcome is EvaluationOutcome.PASS:
        assert verdict == "pass" and confidence.rank >= minimum.rank
    if verdict == "unknown":
        assert decision.outcome is EvaluationOutcome.UNKNOWN
    if verdict != "unknown" and confidence.rank < minimum.rank:
        assert decision.outcome is EvaluationOutcome.UNKNOWN
        assert decision.reason_code == "groundedness.low_confidence"


@given(st.lists(st.sampled_from(list(EvaluationOutcome)), min_size=1, max_size=3))
def test_aggregate_is_pass_only_when_every_call_passed(
    outcomes: list[EvaluationOutcome],
) -> None:
    decisions = [EvaluationDecision(o, "groundedness.x") for o in outcomes]
    merged = aggregate_repeats(decisions, "groundedness")
    if merged.outcome is EvaluationOutcome.PASS:
        assert all(o is EvaluationOutcome.PASS for o in outcomes)
    if EvaluationOutcome.UNKNOWN in outcomes and EvaluationOutcome.FAIL not in outcomes:
        assert merged.outcome is EvaluationOutcome.UNKNOWN


def test_precheck_unknown_and_low_confidence_are_unknown_not_pass_end_to_end() -> None:
    sink = HealthSink()
    low = judge_reply("pass", "supported_by_context", "low", [0])
    coordinator = run_many([IndicatorBinding("groundedness", judge([low]))], sink)
    (event,) = [e for e in sink.events if isinstance(e, EvaluationRecorded)]
    assert event.outcome is EvaluationOutcome.UNKNOWN
    cov = coordinator.coverage().total
    assert (cov.passed, cov.unknown, cov.determinate) == (0, 1, 0)
    assert cov.reliability is None  # UNKNOWN does not create reliability


# ------------------------------------- coverage: attempts are not determinate evidence


def test_ninety_nine_failures_plus_one_pass_cannot_look_healthy() -> None:
    sink = HealthSink()
    scripts: list[Any] = [good_reply()] + [RuntimeError("down")] * 99
    # each run uses its own one-shot provider script position via a shared script
    provider = FakeProvider(scripts)
    binding = IndicatorBinding(
        "groundedness",
        LLMJudge(
            rubric=GR, provider=provider, model_label="integrity", jitter=lambda: 0.0
        ),
    )
    coordinator = run_many([binding], sink, runs=100)
    cov = coordinator.coverage().indicators[0]
    assert (cov.attempted, cov.passed, cov.execution_failures, cov.determinate) == (
        100,
        1,
        99,
        1,
    )
    assert cov.reliability == 1.0  # the arithmetic of the platform...
    assert (
        cov.determinate_rate == 0.01 and cov.failure_rate == 0.99
    )  # ...never shown alone
    text = cov.describe()
    assert "reliability 1.000 over 1 determinate of 100 attempted" in text
    assert "determinate 1.0%" in text and "execution failures 99.0%" in text
    assert coordinator.coverage().describe().count("reliability") == 1
    assert sum(1 for e in sink.events if isinstance(e, EvaluationRecorded)) == 1
    assert len(sink.failures) == 99


def test_attempted_counts_failures_but_determinate_does_not() -> None:
    cov = IndicatorCoverage(
        "x", attempted=10, passed=3, failed=1, unknown=2, execution_failures=4
    )
    assert cov.determinate == 4 and cov.determinate_rate == 0.4
    assert (
        cov.reliability == 0.75 and cov.failure_rate == 0.4 and cov.unknown_rate == 0.2
    )
    empty = IndicatorCoverage("x")
    assert (
        empty.reliability is None
        and empty.failure_rate is None
        and empty.determinate_rate is None
    )


def test_coverage_report_offers_no_single_healthy_boolean() -> None:
    forbidden = re.compile(
        r"healthy|health|\bok\b|is_ok|good|ready|accurate|score|verdict", re.I
    )
    for cls in (
        IndicatorCoverage,
        CoverageReport,
        ReportComparison,
        JudgeInvocationReport,
    ):
        names = [f.name for f in dataclasses.fields(cls)]
        names += [n for n in dir(cls) if not n.startswith("_")]
        assert not [n for n in names if forbidden.search(n)], cls.__name__
        for name in ("total", "describe", "reliability"):
            member = getattr(cls, name, None)
            if isinstance(member, property):
                assert "bool" not in str(member.fget.__annotations__.get("return", ""))  # type: ignore[union-attr]
    coordinator_members = [n for n in dir(JudgeCoordinator) if not n.startswith("_")]
    assert not [n for n in coordinator_members if forbidden.search(n)]


# --------------------------------- budget exhaustion and overload are observable


def test_budget_exhaustion_is_visible_in_observer_coverage_and_failure_evidence() -> (
    None
):
    sink = HealthSink()
    observer = Collect()
    tracker = BudgetTracker(JudgeBudget(max_tokens_per_window=5))
    tracker.record(5, 0)
    provider = FakeProvider([good_reply()], reports_tokens=True)
    binding = IndicatorBinding(
        "groundedness",
        LLMJudge(rubric=GR, provider=provider, model_label="integrity", budget=tracker),
    )
    coordinator = run_many([binding], sink, observer=observer)
    assert provider.call_count == 0
    (report,) = observer.reports
    assert (
        report.kind == "failure" and report.exception_type == "JudgeBudgetExceededError"
    )
    assert dict(coordinator.coverage().total.failures_by_class) == {
        "JudgeBudgetExceededError": 1
    }
    assert [f[2] for f in sink.failures] == ["JudgeBudgetExceededError"]


# ------------------ cross-indicator measurement-health limitation (SDK side)


def test_one_failure_marks_the_whole_run_unavailable_via_the_recorder() -> None:
    sink = HealthSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    coordinator = JudgeCoordinator(
        [
            IndicatorBinding("good", judge([good_reply()])),
            IndicatorBinding("bad", judge([RuntimeError("down")])),
        ],
        runner=EvaluatorRunner(diagnostic_handler=Quiet()),  # type: ignore[arg-type]
    )

    async def go() -> MeasurementHealthReport:
        with sdk.run(agent_id="a", name="A", version="1") as run:
            async with coordinator.scope(run) as scope:
                await scope.evaluate("good", grounded_request())
                await scope.evaluate("bad", grounded_request())
            return run.measurement_health

    health = asyncio.run(go())
    assert health.health is MeasurementHealth.UNAVAILABLE
    assert health.reasons == frozenset(
        {MeasurementHealthReason.EVALUATOR_EXECUTION_FAILURE}
    )
    # health has no indicator dimension: the failing indicator cannot be singled out
    assert [f.name for f in dataclasses.fields(MeasurementHealthReport)] == [
        "health",
        "reasons",
    ]
    # while the passing indicator's reliability evidence is still recorded
    assert [e.indicator for e in sink.events if isinstance(e, EvaluationRecorded)] == [
        "good"
    ]


def test_a_separate_scope_and_run_keeps_the_other_run_healthy() -> None:
    sink = HealthSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]
    healthy = JudgeCoordinator(
        [IndicatorBinding("good", judge([good_reply()]))],
        runner=EvaluatorRunner(diagnostic_handler=Quiet()),  # type: ignore[arg-type]
    )
    broken = JudgeCoordinator(
        [IndicatorBinding("bad", judge([RuntimeError("down")]))],
        runner=EvaluatorRunner(diagnostic_handler=Quiet()),  # type: ignore[arg-type]
    )

    async def go() -> tuple[MeasurementHealth, MeasurementHealth]:
        with sdk.run(agent_id="a", name="A", version="1") as run_a:
            async with healthy.scope(run_a) as scope:
                await scope.evaluate("good", grounded_request())
        with sdk.run(agent_id="a", name="A", version="1") as run_b:
            async with broken.scope(run_b) as scope:
                await scope.evaluate("bad", grounded_request())
            return run_a.measurement_health.health, run_b.measurement_health.health

    a, b = asyncio.run(go())
    assert (a, b) == (MeasurementHealth.HEALTHY, MeasurementHealth.UNAVAILABLE)


def test_sg1_defaults_are_documented_safe_not_fast_values() -> None:
    limits = JudgeLimits()
    assert (limits.provider_timeout_seconds, limits.evaluation_deadline_seconds) == (
        30.0,
        60.0,
    )
    assert (limits.max_attempts, limits.repair_attempts) == (2, 1)
    assert (
        JudgeBudget().enforces_anything is False
    )  # no budget unless the caller sets one
    import inspect

    signature = inspect.signature(JudgeCoordinator.__init__).parameters
    assert signature["max_concurrency"].default == 4
    assert signature["max_pending"].default == 64
    assert signature["max_evaluations_per_run"].default == 16
    assert signature["drain_timeout_seconds"].default == 60.0


# ---------------------------------------------- no public accuracy/calibration claims

_CLAIM_PATTERNS = [
    r"\d+(?:\.\d+)?\s*%\s*(?:accura|agreement|precision|recall|correct)",
    r"\b(?:highly|very|proven|guaranteed|state[- ]of[- ]the[- ]art)\s+accurate",
    r"accuracy\s+(?:of|is|reaches)\s+\d",
    r"(?<!not )(?<!un)calibrated\s+(?:judge|rubric|reference rubric|by gentlity)",
    r"(?<!not )(?<!no )\bproduction[- ]ready\b",
    r"\bproven\s+(?:reliable|correct|accurate)\b",
]
_DOCS = [
    "README.md",
    "docs/EVALUATE.md",
    "docs/adr/0010-experimental-judge-adapter-amends-adr-0007-decision-9.md",
    "docs/GA_CONTRACT.md",
    "docs/VERSIONING.md",
    "docs/ROADMAP.md",
]


def _public_texts() -> dict[str, str]:
    texts = {name: (ROOT / name).read_text(encoding="utf-8") for name in _DOCS}
    judge_dir = ROOT / "src/agent_reliability/experimental/judge"
    for path in sorted(judge_dir.rglob("*")):
        if path.suffix in {".py", ".json"} and "schemas" not in path.parts:
            texts[str(path.relative_to(ROOT))] = path.read_text(encoding="utf-8")
    for path in sorted((ROOT / "examples").glob("judge_*.py")):
        texts[str(path.relative_to(ROOT))] = path.read_text(encoding="utf-8")
    for extra in ("P29_JUDGE_USAGE.md", "P29_PILOT_RUNBOOK.md"):
        if (ROOT / "docs" / extra).exists():
            texts[f"docs/{extra}"] = (ROOT / "docs" / extra).read_text(encoding="utf-8")
    return texts


def test_no_public_document_or_code_makes_an_accuracy_or_calibration_claim() -> None:
    texts = _public_texts()
    assert len(texts) > 15
    hits = [
        (name, pattern)
        for name, text in texts.items()
        for pattern in _CLAIM_PATTERNS
        if re.search(pattern, text, re.IGNORECASE)
    ]
    assert hits == []


def test_the_claim_scanner_would_catch_a_claim() -> None:
    for sample in (
        "The judge reaches 95% accuracy",
        "This is a highly accurate judge",
        "a calibrated rubric ships",
        "it is production-ready",
        "92% agreement with humans",
    ):
        assert any(re.search(p, sample, re.IGNORECASE) for p in _CLAIM_PATTERNS), sample
    for sample in (
        "not calibrated by Gentlity",
        "uncalibrated reference rubric",
        "not production-ready",
    ):
        assert not any(re.search(p, sample, re.IGNORECASE) for p in _CLAIM_PATTERNS), (
            sample
        )

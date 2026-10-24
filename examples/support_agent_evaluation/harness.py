"""Run the support agent under Agent Reliability instrumentation and analyse it.

Language: Python. Everything numeric comes from the SDK (``EvaluatorRunner``,
``ReliabilityObservation``, ``evaluate_reliability``, ``report_to_dict``); this module
only (a) feeds the SDK, (b) groups results and (c) compares them with ordinary-log
signals and with the agent's structured claims. It computes no reliability score.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from agent_reliability.adapters import InMemoryEventSink
from agent_reliability.domain import (
    EvaluationOutcome,
    ObjectiveDirection,
    RunStatus,
    Slo,
    UnknownPolicy,
)
from agent_reliability.evaluation import (
    EvaluationExecutionFailure,
    EvaluationResult,
    EvaluatorIdentity,
    LatencyThresholdEvaluator,
    PredicateEvaluator,
    ToolCalledEvaluator,
    ToolNotCalledEvaluator,
)
from agent_reliability.ports.events import (
    EvaluationRecorded,
    RunCompleted,
    RunFailed,
)
from agent_reliability.reliability import (
    AggregationConflict,
    ReliabilityObservation,
    ReliabilityReport,
    evaluate_reliability,
)
from agent_reliability.reporting import report_to_dict
from agent_reliability.sdk import AgentReliability, EvaluatorRunner

from .agent import AgentResult, SupportAgent

DATA_DIR = Path(__file__).resolve().parent / "data"
LATENCY_THRESHOLD_SECONDS = 3.0
VERSIONS = ("v1", "v2")


@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    slo: Slo
    unknown_policy: UnknownPolicy
    meaning: str


# One indicator, one evaluator identity, one SLO each. UNKNOWN policies are explicit:
# latency cannot be judged for a run that crashed before producing a duration, and that
# run is already counted as a failure by ``task_success``, so it is excluded here.
INDICATORS: tuple[IndicatorSpec, ...] = (
    IndicatorSpec(
        "task_success",
        Slo("task-success", Fraction(9, 10), ObjectiveDirection.AT_LEAST),
        UnknownPolicy.TREAT_AS_BAD,
        "the answer contains an accepted phrase for the case",
    ),
    IndicatorSpec(
        "refund_policy",
        Slo("refund-policy", Fraction(99, 100), ObjectiveDirection.AT_LEAST),
        UnknownPolicy.TREAT_AS_BAD,
        "a refund above the approval threshold was not issued without a human",
    ),
    IndicatorSpec(
        "escalation",
        Slo("escalation", Fraction(95, 100), ObjectiveDirection.AT_LEAST),
        UnknownPolicy.TREAT_AS_BAD,
        "the agent handed off to a human when it had to",
    ),
    IndicatorSpec(
        "latency",
        Slo("latency", Fraction(95, 100), ObjectiveDirection.AT_LEAST),
        UnknownPolicy.EXCLUDE,
        f"the simulated response time is within {LATENCY_THRESHOLD_SECONDS:g} s",
    ),
)
_SPEC = {spec.name: spec for spec in INDICATORS}


def _accepted_phrase_present(value: tuple[str, tuple[str, ...]]) -> bool:
    answer, accepted = value
    folded = answer.casefold()
    return any(phrase.casefold() in folded for phrase in accepted)


def build_evaluators(task_version: str = "1") -> dict[str, Any]:
    """The four evaluators; ``task_version`` is only for the methodology demo."""
    return {
        "task_success": PredicateEvaluator(
            EvaluatorIdentity("accepted-phrase-present", task_version),
            _accepted_phrase_present,
            True,
        ),
        "refund_policy": ToolNotCalledEvaluator(
            EvaluatorIdentity("refund-not-issued-unsupervised", "1"), "issue_refund"
        ),
        "escalation": ToolCalledEvaluator(
            EvaluatorIdentity("escalated-to-human", "1"), "escalate_to_human"
        ),
        "latency": LatencyThresholdEvaluator(
            EvaluatorIdentity("within-3-seconds", "1"), LATENCY_THRESHOLD_SECONDS
        ),
    }


class SequentialRunIds:
    """Deterministic run ids so that two executions are identical."""

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._next = 0

    def generate(self) -> str:
        self._next += 1
        return f"{self._prefix}-{self._next:04d}"


@dataclass
class CaseRun:
    case: dict[str, Any]
    version: str
    result: AgentResult | None
    lifecycle: str  # "completed" | "failed"
    exception_type: str | None
    outcomes: dict[str, EvaluationOutcome] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    observations: dict[str, ReliabilityObservation] = field(default_factory=dict)

    @property
    def failing_indicators(self) -> list[str]:
        return [
            name for name in _SPEC if self.outcomes.get(name) is EvaluationOutcome.FAIL
        ]

    @property
    def log_signal(self) -> str:
        """What ordinary logs would show: 'error', 'warning' or 'none'."""
        levels = {line.level for line in (self.result.logs if self.result else ())}
        if self.lifecycle == "failed" or "ERROR" in levels:
            return "error"
        return "warning" if "WARNING" in levels else "none"


def load_data() -> tuple[dict[str, Any], dict[str, Any]]:
    knowledge = json.loads((DATA_DIR / "knowledge_base.json").read_text("utf-8"))
    cases = json.loads((DATA_DIR / "cases.json").read_text("utf-8"))
    return knowledge, cases


def applicable(case: dict[str, Any], indicator: str) -> bool:
    if indicator in ("task_success", "latency"):
        return True
    if indicator == "escalation":
        return bool(case["expected"]["must_escalate"])
    return case.get("refund_allowed") is False  # refund_policy


def run_version(
    version: str,
    knowledge: dict[str, Any],
    cases: list[dict[str, Any]],
    evaluators: dict[str, Any] | None = None,
) -> list[CaseRun]:
    """Execute every case once under ``sdk.run`` and record its evaluations."""
    evaluators = evaluators if evaluators is not None else build_evaluators()
    sink = InMemoryEventSink()
    sdk = AgentReliability(sink=sink, run_id_generator=SequentialRunIds(version))
    runner = EvaluatorRunner()
    agent = SupportAgent(
        version,
        knowledge["knowledge_base"],
        knowledge["superseded_articles"],
        knowledge["orders"],
    )
    runs: list[CaseRun] = []
    run_ids: list[str | None] = []
    for case in cases:
        record = CaseRun(case, version, None, "completed", None)
        run_id: str | None = None
        try:
            with sdk.run(
                agent_id="support-agent",
                name="Support Agent",
                version=version,
                environment="offline-evaluation",
            ) as run:
                run_id = run.run_id
                try:
                    record.result = agent.handle(case)
                except Exception as exc:
                    # Record what the evaluators can say about a crash (an empty
                    # answer, no duration) INSIDE the run, then let the SDK see the
                    # exception so the run is classified as failed.
                    record.exception_type = type(exc).__name__
                    _evaluate(record, evaluators, runner, run)
                    raise
                _evaluate(record, evaluators, runner, run)
        except Exception:  # the SDK re-raises; the harness keeps going
            record.lifecycle = "failed"
        runs.append(record)
        run_ids.append(run_id)
    _confirm_lifecycle(runs, run_ids, sink)
    return runs


def _evaluate(
    record: CaseRun, evaluators: dict[str, Any], runner: EvaluatorRunner, run: Any
) -> None:
    result = record.result
    inputs: dict[str, Any] = {
        "task_success": (
            result.answer if result else "",
            tuple(record.case["accept_phrases"]),
        ),
        "refund_policy": result.called_tools if result else frozenset(),
        "escalation": result.called_tools if result else frozenset(),
        "latency": result.duration_seconds if result else None,
    }
    for name in _SPEC:
        if not applicable(record.case, name):
            continue
        outcome = runner.evaluate(evaluators[name], inputs[name])
        if isinstance(outcome, EvaluationExecutionFailure):
            raise RuntimeError(f"evaluator {name} could not run")
        _store(record, name, outcome)
        if run is not None:
            run.record_evaluation(indicator=name, result=outcome)


def _store(record: CaseRun, indicator: str, outcome: EvaluationResult) -> None:
    record.outcomes[indicator] = outcome.outcome
    record.reasons[indicator] = outcome.reason_code or ""
    record.observations[indicator] = ReliabilityObservation.from_evaluation(
        indicator=indicator, result=outcome
    )


def _confirm_lifecycle(
    runs: list[CaseRun], run_ids: list[str | None], sink: InMemoryEventSink
) -> None:
    """Cross-check the harness's lifecycle against the SDK's own events."""
    statuses: dict[str, RunStatus] = {}
    recorded = 0
    for event in sink.events:
        if isinstance(event, RunCompleted):
            statuses[event.run_id] = RunStatus.COMPLETED
        elif isinstance(event, RunFailed):
            statuses[event.run_id] = event.status
        elif isinstance(event, EvaluationRecorded):
            recorded += 1
    if recorded != sum(len(r.observations) for r in runs):
        raise RuntimeError("the SDK event stream lost an evaluation")
    for record, run_id in zip(runs, run_ids, strict=True):
        if run_id is None:
            raise RuntimeError("run id missing")
        expected = (
            RunStatus.FAILED if record.lifecycle == "failed" else RunStatus.COMPLETED
        )
        if statuses.get(run_id) is not expected:
            raise RuntimeError(f"SDK lifecycle disagrees for {record.case['id']}")


def reports_for(
    runs: list[CaseRun],
) -> dict[str, ReliabilityReport | AggregationConflict]:
    out: dict[str, ReliabilityReport | AggregationConflict] = {}
    for spec in INDICATORS:
        observations = [
            r.observations[spec.name] for r in runs if spec.name in r.observations
        ]
        out[spec.name] = evaluate_reliability(
            indicator=spec.name,
            observations=observations,
            slo=spec.slo,
            unknown_policy=spec.unknown_policy,
        )
    return out


# -- structured-claim check -----------------------------------------------------------


def structured_claim_failure(record: CaseRun) -> bool | None:
    """Does the agent's *structured* claim contradict the case's expectation?

    Only ``task_success`` has a check that is not the same state the evaluator reads:
    the evaluator reads the answer **text**; this reads the fact ids the agent itself
    reports it stated. A disagreement is a text-matching error (false positive or
    negative). It is not independent of the agent: if the agent mis-reports its own
    facts, this check is wrong too. For ``escalation``, ``refund_policy`` and
    ``latency`` the "truth" would be the very value the evaluator already receives, so
    no accuracy claim is made for them (``None``)."""
    if "task_success" not in record.outcomes:
        return None
    result = record.result
    if result is None:
        return True
    expected = record.case["expected"]
    right = bool(set(expected["facts_any"]) & result.fact_ids) or (
        expected["accept_escalation"] and result.escalated
    )
    return not right


def confusion(runs: list[CaseRun]) -> dict[str, dict[str, int]]:
    """Text-matching verdicts for ``task_success`` versus the structured claims."""
    table = {
        "task_success": {
            "true_positive": 0,
            "false_positive": 0,
            "false_negative": 0,
            "true_negative": 0,
        }
    }
    for record in runs:
        really_fails = structured_claim_failure(record)
        flagged = record.outcomes.get("task_success") is EvaluationOutcome.FAIL
        if really_fails is None:
            continue
        if flagged and really_fails:
            table["task_success"]["true_positive"] += 1
        elif flagged:
            table["task_success"]["false_positive"] += 1
        elif really_fails:
            table["task_success"]["false_negative"] += 1
        else:
            table["task_success"]["true_negative"] += 1
    return table


def confirmed_failing_indicators(record: CaseRun) -> list[str]:
    """Failing indicators excluding ``task_success`` verdicts the structured claim
    contradicts (known text-matching false positives)."""
    confirmed = []
    for name in record.failing_indicators:
        if name == "task_success" and structured_claim_failure(record) is False:
            continue
        confirmed.append(name)
    return confirmed


# -- analysis -----------------------------------------------------------------------


def report_dict(report: ReliabilityReport | AggregationConflict) -> dict[str, Any]:
    if isinstance(report, AggregationConflict):
        return {"conflict": sorted(r.value for r in report.reasons)}
    return report_to_dict(report)


def failure_evidence(
    runs: list[CaseRun], modes: dict[str, str]
) -> list[dict[str, Any]]:
    """One bounded evidence record per FAIL observation."""
    evidence: list[dict[str, Any]] = []
    for record in runs:
        claim = structured_claim_failure(record)
        for name in record.failing_indicators:
            result = record.result
            case = record.case
            evidence.append(
                {
                    "case": case["id"],
                    "version": record.version,
                    "indicator": name,
                    "evaluator_reason": record.reasons[name],
                    "origin": case["origin"],
                    "fault": case["fault"],
                    "failure_mode": case["failure_mode"],
                    "run_lifecycle": record.lifecycle,
                    "exception_type": record.exception_type,
                    "log_signal": record.log_signal,
                    "structured_claim_agrees_it_is_a_failure": (
                        claim if name == "task_success" else None
                    ),
                    "request": case["query"],
                    "answer": result.answer if result else None,
                    "tools_called": sorted(result.called_tools) if result else [],
                    "duration_seconds": result.duration_seconds if result else None,
                    "corrective_action": modes.get(case["failure_mode"] or "", ""),
                    "reproduce": (
                        "python run_evaluation.py "
                        f"--version {record.version} --case {case['id']}"
                    ),
                }
            )
    return evidence


def visibility(runs: list[CaseRun]) -> dict[str, Any]:
    """Failures judged by Gentlity versus the run status and the agent's own log lines.

    Illustrative, not a measurement of any real team's tooling: the "ordinary" baseline
    is **run status plus the WARNING/ERROR lines this example agent chose to write**.
    It ignores metrics, traces, dashboards and alerts a real team may have (for example,
    anyone charting latency would see the slow cases). Runs whose only failure is a
    known text-matching false positive are excluded and listed separately."""
    gentlity_failed = [r for r in runs if confirmed_failing_indicators(r)]
    excluded = sorted(
        r.case["id"] for r in runs if r.failing_indicators and r not in gentlity_failed
    )
    silent = [
        r
        for r in gentlity_failed
        if r.lifecycle == "completed" and r.log_signal == "none"
    ]
    warning_only = [
        r
        for r in gentlity_failed
        if r.lifecycle == "completed" and r.log_signal == "warning"
    ]
    loud = [
        r for r in gentlity_failed if r.lifecycle == "failed" or r.log_signal == "error"
    ]
    log_view_ok = [r for r in runs if r.log_signal != "error"]
    return {
        "baseline": "run status plus the example agent's own WARNING/ERROR log lines",
        "runs": len(runs),
        "runs_with_a_confirmed_failure": len(gentlity_failed),
        "run_status_or_error_log_success": len(log_view_ok),
        "silent_failures_no_log_signal": sorted(r.case["id"] for r in silent),
        "failures_with_only_a_warning_log": sorted(r.case["id"] for r in warning_only),
        "failures_visible_as_run_failure_or_error_log": sorted(
            r.case["id"] for r in loud
        ),
        "excluded_text_matching_false_positives": excluded,
    }


def methodology_change_demo(
    knowledge: dict[str, Any], cases: list[dict[str, Any]]
) -> dict[str, Any]:
    """Mixing observations from two evaluator versions must be refused, not averaged."""
    first = run_version("v2", knowledge, cases, build_evaluators("1"))
    second = run_version("v2", knowledge, cases, build_evaluators("2"))
    mixed = [r.observations["task_success"] for r in first[:3] + second[3:]]
    spec = _SPEC["task_success"]
    outcome = evaluate_reliability(
        indicator="task_success",
        observations=mixed,
        slo=spec.slo,
        unknown_policy=spec.unknown_policy,
    )
    return report_dict(outcome)


def analyse(
    cases_file: dict[str, Any],
    knowledge: dict[str, Any],
    versions: tuple[str, ...] = VERSIONS,
    selected: str | None = None,
) -> dict[str, Any]:
    cases = [c for c in cases_file["cases"] if selected in (None, c["id"])]
    if not cases:
        raise ValueError(f"no case matches {selected!r}")
    modes = cases_file["failure_modes"]
    per_version: dict[str, Any] = {}
    all_runs: dict[str, list[CaseRun]] = {}
    for version in versions:
        runs = run_version(version, knowledge, cases)
        all_runs[version] = runs
        reports = reports_for(runs)
        per_version[version] = {
            "indicators": {name: report_dict(rep) for name, rep in reports.items()},
            "visibility": visibility(runs),
            "evaluator_accuracy_vs_structured_claims": confusion(runs),
            "failures": failure_evidence(runs, modes),
        }
    out: dict[str, Any] = {
        "dataset": {
            "cases": len(cases),
            "organic": sum(c["origin"] == "organic" for c in cases),
            "injected": sum(c["origin"] == "injected" for c in cases),
        },
        "objectives": {
            spec.name: {
                "slo": f"{float(spec.slo.target):.0%} {spec.slo.direction.value}",
                "unknown_policy": spec.unknown_policy.value,
                "meaning": spec.meaning,
            }
            for spec in INDICATORS
        },
        "versions": per_version,
    }
    if len(versions) == 2 and selected is None:
        out["regression"] = regression(per_version, versions)
        out["methodology_change_demo"] = methodology_change_demo(knowledge, cases)
    return out


def regression(
    per_version: dict[str, Any], versions: tuple[str, ...]
) -> dict[str, Any]:
    """Compare the two versions indicator by indicator using the SDK's own numbers."""
    before, after = versions
    table: dict[str, Any] = {}
    for spec in INDICATORS:
        old = per_version[before]["indicators"][spec.name]
        new = per_version[after]["indicators"][spec.name]
        if "conflict" in old or "conflict" in new:
            table[spec.name] = {"comparable": False}
            continue

        def ratio(entry: dict[str, Any]) -> float:
            part = entry["reliability"]["pass_ratio"]
            return part["numerator"] / part["denominator"]

        table[spec.name] = {
            "comparable": old["cohort"] == new["cohort"],
            f"{before}_reliability": round(ratio(old), 4),
            f"{after}_reliability": round(ratio(new), 4),
            f"{before}_slo": old["slo"]["status"],
            f"{after}_slo": new["slo"]["status"],
            f"{before}_budget": old["error_budget"]["status"],
            f"{after}_budget": new["error_budget"]["status"],
        }
    return table

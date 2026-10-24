# ruff: noqa: E501 -- long explanatory strings stay readable as sentences.
"""Run an upstream smolagents agent under Gentlity and measure its reliability.

Language: Python. Every number comes from the SDK (``EvaluatorRunner``,
``ReliabilityObservation``, ``evaluate_reliability``, ``report_to_dict``). The agent is
the upstream ``smolagents.ToolCallingAgent``; this module only wraps one request in
``sdk.run`` and reads the agent's own step log.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from fractions import Fraction
from importlib import metadata
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
    EvaluatorIdentity,
    LatencyThresholdEvaluator,
    PredicateEvaluator,
    ToolCalledEvaluator,
)
from agent_reliability.ports.events import EvaluationRecorded, RunCompleted, RunFailed
from agent_reliability.reliability import (
    AggregationConflict,
    ReliabilityObservation,
    ReliabilityReport,
    evaluate_reliability,
)
from agent_reliability.reporting import report_to_dict
from agent_reliability.sdk import AgentReliability, EvaluatorRunner

from .checks import answer_matches
from .replay import RecordingModel, ReplayDivergence, ReplayModel
from .scenario import build_sql_engine_tool

PACKAGE = Path(__file__).resolve().parent
DATA_DIR = PACKAGE / "data"
TRANSCRIPT_DIR = PACKAGE / "transcripts"
DEFAULT_MODEL_TAG = "qwen2.5-coder-7b"
MAX_STEPS = 6
LATENCY_THRESHOLD_SECONDS = 10.0
AGENT_ID = "smolagents-text-to-sql"


@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    slo: Slo
    unknown_policy: UnknownPolicy
    meaning: str


# Fixed before the first run (see README): one indicator, one evaluator, one SLO each.
INDICATORS: tuple[IndicatorSpec, ...] = (
    IndicatorSpec(
        "task_success",
        Slo("task-success", Fraction(9, 10), ObjectiveDirection.AT_LEAST),
        UnknownPolicy.TREAT_AS_BAD,
        "the final answer agrees with the independent SQL reference",
    ),
    IndicatorSpec(
        "tool_used",
        Slo("tool-used", Fraction(95, 100), ObjectiveDirection.AT_LEAST),
        UnknownPolicy.TREAT_AS_BAD,
        "the agent queried the database instead of answering from memory",
    ),
    IndicatorSpec(
        "tool_execution",
        Slo("tool-execution", Fraction(95, 100), ObjectiveDirection.AT_LEAST),
        UnknownPolicy.TREAT_AS_BAD,
        "no step of the run raised a tool or parsing error (recovered or not)",
    ),
    IndicatorSpec(
        "latency",
        Slo("latency", Fraction(95, 100), ObjectiveDirection.AT_LEAST),
        UnknownPolicy.EXCLUDE,
        f"the wall-clock time of the run is within {LATENCY_THRESHOLD_SECONDS:g} s",
    ),
)
_SPEC = {spec.name: spec for spec in INDICATORS}


def build_evaluators(tolerance: float) -> dict[str, Any]:
    def matches_reference(value: tuple[dict[str, Any], str]) -> bool:
        case, answer = value
        return answer_matches(case, answer, tolerance)

    def no_step_error(error_types: tuple[str, ...]) -> bool:
        return not error_types

    return {
        "task_success": PredicateEvaluator(
            EvaluatorIdentity("matches-sql-reference", "1"), matches_reference, True
        ),
        "tool_used": ToolCalledEvaluator(
            EvaluatorIdentity("queried-database", "1"), "sql_engine"
        ),
        "tool_execution": PredicateEvaluator(
            EvaluatorIdentity("no-step-error", "1"), no_step_error, True
        ),
        "latency": LatencyThresholdEvaluator(
            EvaluatorIdentity("within-10-seconds", "1"), LATENCY_THRESHOLD_SECONDS
        ),
    }


@dataclass
class CaseRun:
    case: dict[str, Any]
    answer: str = ""
    agent_state: str = "not_run"
    step_error_types: tuple[str, ...] = ()
    tool_names: tuple[str, ...] = ()
    sql_queries: tuple[str, ...] = ()
    steps: int = 0
    duration_seconds: float | None = None
    tokens: tuple[int, int] | None = None
    exception_type: str | None = None
    lifecycle: str = "completed"
    outcomes: dict[str, EvaluationOutcome] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    observations: dict[str, ReliabilityObservation] = field(default_factory=dict)
    recorded_steps: list[dict[str, Any]] = field(default_factory=list)


class SequentialRunIds:
    def __init__(self, prefix: str) -> None:
        self._prefix, self._next = prefix, 0

    def generate(self) -> str:
        self._next += 1
        return f"{self._prefix}-{self._next:04d}"


def load_cases() -> dict[str, Any]:
    return json.loads((DATA_DIR / "cases.json").read_text(encoding="utf-8"))


def load_transcript(tag: str) -> dict[str, Any]:
    path = TRANSCRIPT_DIR / f"{tag}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_adjudication(tag: str) -> dict[str, Any]:
    path = DATA_DIR / f"adjudication_{tag}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _agent_step_facts(
    result: Any,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """(error types, tool names, SQL queries) from the upstream agent's own step log."""
    errors: list[str] = []
    tools: list[str] = []
    queries: list[str] = []
    for step in result.steps:
        if "step_number" not in step:
            continue  # the task entry
        error = step.get("error")
        if error:
            errors.append(str(error.get("type", "AgentError")))
        for call in step.get("tool_calls") or []:
            name = call["function"]["name"] if "function" in call else call["name"]
            tools.append(name)
            arguments = (call.get("function") or call).get("arguments")
            if name == "sql_engine" and isinstance(arguments, dict):
                queries.append(str(arguments.get("query", "")))
    return tuple(errors), tuple(tools), tuple(queries)


def _make_agent(model: Any) -> Any:
    from smolagents import ToolCallingAgent

    return ToolCallingAgent(
        tools=[build_sql_engine_tool()],
        model=model,
        max_steps=MAX_STEPS,
        verbosity_level=0,
    )


def execute_case(
    record: CaseRun, model: Any, recorded_duration: float | None = None
) -> None:
    """Run the upstream agent on one case and copy what its step log says."""
    agent = _make_agent(model)
    started = time.perf_counter()
    result = agent.run(record.case["question"], return_full_result=True)
    elapsed = time.perf_counter() - started
    record.duration_seconds = (
        recorded_duration if recorded_duration is not None else elapsed
    )
    record.answer = "" if result.output is None else str(result.output)
    record.agent_state = str(result.state)
    record.step_error_types, record.tool_names, record.sql_queries = _agent_step_facts(
        result
    )
    record.steps = sum(1 for s in result.steps if "step_number" in s)
    if result.token_usage is not None:
        record.tokens = (
            result.token_usage.input_tokens,
            result.token_usage.output_tokens,
        )


def _require_faithful_replay(model: Any) -> None:
    if isinstance(model, ReplayModel):
        if model.divergence is not None:
            raise model.divergence
        if not model.exhausted:
            raise ReplayDivergence("the agent made fewer model calls than recorded")


def _evaluate(
    record: CaseRun,
    evaluators: dict[str, Any],
    runner: EvaluatorRunner,
    run: Any,
) -> None:
    inputs = {
        "task_success": (record.case, record.answer),
        "tool_used": frozenset(record.tool_names),
        "tool_execution": record.step_error_types,
        "latency": record.duration_seconds,
    }
    for name in _SPEC:
        outcome = runner.evaluate(evaluators[name], inputs[name])
        if isinstance(outcome, EvaluationExecutionFailure):
            raise RuntimeError(f"evaluator {name} could not run")
        record.outcomes[name] = outcome.outcome
        record.reasons[name] = outcome.reason_code or ""
        record.observations[name] = ReliabilityObservation.from_evaluation(
            indicator=name, result=outcome
        )
        run.record_evaluation(indicator=name, result=outcome)


def run_cases(
    cases: list[dict[str, Any]],
    tolerance: float,
    *,
    mode: str,
    tag: str = DEFAULT_MODEL_TAG,
    live_model_factory: Any = None,
) -> list[CaseRun]:
    """Execute every case once under ``sdk.run`` (``mode`` is ``replay`` or ``live``)."""
    transcript = load_transcript(tag) if mode == "replay" else None
    evaluators = build_evaluators(tolerance)
    sink = InMemoryEventSink()
    sdk = AgentReliability(sink=sink, run_id_generator=SequentialRunIds(mode))
    runner = EvaluatorRunner()
    version = metadata.version("smolagents")
    runs: list[CaseRun] = []
    run_ids: list[str | None] = []
    for case in cases:
        record = CaseRun(case)
        recorder: RecordingModel | None = None
        recorded_duration: float | None = None
        if transcript is not None:
            entry = transcript["cases"][case["id"]]
            model: Any = ReplayModel(entry["steps"], transcript["meta"]["model_id"])
            recorded_duration = entry["duration_seconds"]
        else:
            recorder = RecordingModel(live_model_factory())
            model = recorder
        run_id: str | None = None
        try:
            with sdk.run(
                agent_id=AGENT_ID,
                name="smolagents ToolCallingAgent (text-to-SQL)",
                version=version,
                environment="local-evaluation",
            ) as run:
                run_id = run.run_id
                try:
                    execute_case(record, model, recorded_duration)
                    _require_faithful_replay(model)
                except ReplayDivergence:
                    raise
                except Exception as exc:
                    if isinstance(model, ReplayModel) and model.divergence:
                        raise model.divergence from exc
                    record.exception_type = type(exc).__name__
                    record.duration_seconds = None
                    _evaluate(record, evaluators, runner, run)
                    raise
                _evaluate(record, evaluators, runner, run)
        except ReplayDivergence:
            raise
        except Exception:
            record.lifecycle = "failed"
        if recorder is not None:
            record.recorded_steps = recorder.steps
        runs.append(record)
        run_ids.append(run_id)
    _confirm_lifecycle(runs, run_ids, sink)
    return runs


def _confirm_lifecycle(
    runs: list[CaseRun], run_ids: list[str | None], sink: InMemoryEventSink
) -> None:
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
    return {
        spec.name: evaluate_reliability(
            indicator=spec.name,
            observations=[
                r.observations[spec.name] for r in runs if spec.name in r.observations
            ],
            slo=spec.slo,
            unknown_policy=spec.unknown_policy,
        )
        for spec in INDICATORS
    }


def upstream_visible(record: CaseRun) -> bool:
    """Would the upstream agent's own signals (state, step errors, no output) show it?"""
    return (
        record.agent_state != "success"
        or bool(record.step_error_types)
        or not record.answer
        or record.lifecycle == "failed"
    )


def analyse(
    runs: list[CaseRun], meta: dict[str, Any], adjudication: dict[str, Any]
) -> dict[str, Any]:
    reports = reports_for(runs)
    indicators: dict[str, Any] = {}
    for spec in INDICATORS:
        report = reports[spec.name]
        if isinstance(report, AggregationConflict):
            indicators[spec.name] = {
                "conflict": sorted(r.value for r in report.reasons)
            }
        else:
            indicators[spec.name] = report_to_dict(report)
    cases: list[dict[str, Any]] = []
    for r in runs:
        item = {
            "case": r.case["id"],
            "kind": r.case["kind"],
            "origin": r.case["origin"],
            "question": r.case["question"],
            "answer": r.answer,
            "expected": r.case["expected"],
            "agent_state": r.agent_state,
            "steps": r.steps,
            "tool_names": list(r.tool_names),
            "sql_queries": list(r.sql_queries),
            "step_error_types": list(r.step_error_types),
            "duration_seconds": None
            if r.duration_seconds is None
            else round(r.duration_seconds, 2),
            "tokens_in_out": list(r.tokens) if r.tokens else None,
            "outcomes": {k: v.value for k, v in r.outcomes.items()},
            "upstream_visible": upstream_visible(r),
            "adjudication": adjudication.get(r.case["id"]),
        }
        cases.append(item)
    failures = [c for c in cases if c["outcomes"].get("task_success") != "pass"]
    silent = [c["case"] for c in failures if not c["upstream_visible"]]
    confusion = {
        "true_failure": 0,
        "evaluator_false_positive": 0,
        "true_pass": 0,
        "evaluator_false_negative": 0,
        "ambiguous_case": 0,
        "unadjudicated": 0,
    }
    for c in cases:
        verdict = (c["adjudication"] or {}).get("verdict")
        confusion[verdict if verdict in confusion else "unadjudicated"] += 1
    return {
        "meta": meta,
        "slo_design": {
            s.name: {
                "slo": f"{s.slo.target.numerator}/{s.slo.target.denominator}",
                "meaning": s.meaning,
            }
            for s in INDICATORS
        },
        "indicators": indicators,
        "cases": cases,
        "summary": {
            "cases": len(cases),
            "task_failures": len(failures),
            "silent_task_failures": silent,
            "task_failures_visible_to_upstream_signals": [
                c["case"] for c in failures if c["upstream_visible"]
            ],
            "runs_with_step_error": [c["case"] for c in cases if c["step_error_types"]],
            "adjudication": confusion,
        },
    }

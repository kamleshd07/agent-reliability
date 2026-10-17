"""Local calibration harness (P29 S10, stdlib only, P29-D10 option A).

Calibration is a customer-local practice: a labelled dataset file is read
locally, its content goes only to the provider the supplied judge already uses,
and the result is a **content-free** report (no case text, no judge ``reason``,
no raw output). There is no upload path and no network I/O in this module.

The metrics are descriptive. The harness never emits "good", "bad", "ready" or
"accurate"; thresholds are the customer's. Every rate is shown beside its raw
counts and a Wilson interval; a dataset smaller than the number of
confusion-matrix cells is flagged ``insufficient_for_rates`` and reports counts
only.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any, Final

from agent_reliability.experimental.judge._jsonschema import validate
from agent_reliability.experimental.judge.errors import JudgeError
from agent_reliability.experimental.judge.identity import TEMPLATE_ID
from agent_reliability.experimental.judge.judge import LLMJudge
from agent_reliability.experimental.judge.rubric import _strict_loads
from agent_reliability.experimental.judge.sync import SyncLLMJudge
from agent_reliability.experimental.judge.values import (
    Confidence,
    ContentPart,
    ContentRole,
    EvaluationRequest,
    JudgeDimension,
    JudgeEvaluation,
    JudgeStats,
    _NoCopy,
)

__all__ = [
    "CASE_SCHEMA_ID",
    "REPORT_SCHEMA_ID",
    "CalibrationCase",
    "CalibrationReport",
    "FlippedCase",
    "ReportComparison",
    "compare_reports",
    "load_cases",
    "load_schema",
    "run_calibration",
    "run_calibration_async",
    "wilson_interval",
]

CASE_SCHEMA_ID: Final = "gentlity.calibration-case/1"
REPORT_SCHEMA_ID: Final = "gentlity.calibration-report/1"
#: Confusion-matrix cells (3 human labels x 4 judge columns); fewer cases than this
#: is reported as ``insufficient_for_rates``.
MATRIX_CELLS: Final = 12
_WILSON_Z: Final = 1.96
_HUMAN: Final = ("pass", "fail", "unknown")
_DECISIONS: Final = ("PASS", "FAIL", "UNKNOWN", "FAILURE")
_LEVELS: Final = ("high", "medium", "low")


def load_schema(name: str) -> dict[str, Any]:
    """Load the ``calibration-case`` or ``calibration-report`` JSON Schema."""
    if name not in ("calibration-case", "calibration-report"):
        raise ValueError("unknown schema name")
    text = (
        resources.files("agent_reliability.experimental.judge")
        .joinpath("schemas", f"{name}.schema.json")
        .read_text(encoding="utf-8")
    )
    schema: dict[str, Any] = json.loads(text)
    return schema


# ------------------------------------------------------------------- cases


@dataclass(frozen=True, slots=True, repr=False)
class CalibrationCase(_NoCopy):
    """One labelled case. Holds raw content: never rendered, serialized or copied."""

    case_id: str
    dimension: JudgeDimension
    parts: tuple[ContentPart, ...] = field(repr=False)
    human_label: str
    difficulty: str
    labels: tuple[tuple[str, str], ...] = ()
    source: str | None = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> CalibrationCase:
        validate(document, load_schema("calibration-case"))
        return cls(
            case_id=document["case_id"],
            dimension=JudgeDimension(document["dimension"]),
            parts=tuple(
                ContentPart(ContentRole(p["role"]), p["text"])
                for p in document["parts"]
            ),
            human_label=document["human_label"],
            difficulty=document["difficulty"],
            labels=tuple(
                (x["labeler"], x["label"]) for x in document.get("labels", [])
            ),
            source=document.get("source"),
        )

    def request(self) -> EvaluationRequest:
        return EvaluationRequest(self.dimension, self.parts)

    def __repr__(self) -> str:
        return (
            f"CalibrationCase(case_id={self.case_id!r}, difficulty={self.difficulty})"
        )


def load_cases(path: str | Path) -> tuple[tuple[CalibrationCase, ...], str]:
    """Read a JSON Lines dataset; return ``(cases, sha256-of-file)``. Local only."""
    data = Path(path).read_bytes()
    cases: list[CalibrationCase] = []
    for number, raw in enumerate(data.decode("utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            document = _strict_loads(raw)
            cases.append(CalibrationCase.from_dict(document))
        except ValueError:
            raise ValueError(f"invalid calibration case on line {number}") from None
    if len({c.case_id for c in cases}) != len(cases):
        raise ValueError("case_id values must be unique within a dataset")
    return tuple(cases), hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------ metrics


def wilson_interval(successes: int, total: int) -> tuple[float, float] | None:
    """95% Wilson score interval, or ``None`` when ``total`` is zero."""
    if total <= 0:
        return None
    p = successes / total
    z2 = _WILSON_Z**2
    denominator = 1 + z2 / total
    centre = (p + z2 / (2 * total)) / denominator
    half = (
        _WILSON_Z * math.sqrt(p * (1 - p) / total + z2 / (4 * total**2)) / denominator
    )
    return max(0.0, centre - half), min(1.0, centre + half)


def _rate(num: int, den: int, flagged: bool) -> dict[str, Any]:
    interval = None if flagged else wilson_interval(num, den)
    return {
        "numerator": num,
        "denominator": den,
        "rate": None if flagged or den == 0 else round(num / den, 6),
        "wilson_low": None if interval is None else round(interval[0], 6),
        "wilson_high": None if interval is None else round(interval[1], 6),
        "method": "wilson-95",
    }


def _kappa(pairs: Sequence[tuple[str, str]]) -> float | None:
    n = len(pairs)
    if n == 0:
        return None
    observed = sum(1 for a, b in pairs if a == b) / n
    expected = sum(
        (sum(1 for a, _ in pairs if a == label) / n)
        * (sum(1 for _, b in pairs if b == label) / n)
        for label in _HUMAN
    )
    if expected >= 1.0:
        return None
    return round((observed - expected) / (1 - expected), 6)


@dataclass(frozen=True, slots=True)
class _Call:
    decision: str  # PASS | FAIL | UNKNOWN | FAILURE
    failure_class: str | None
    confidence: Confidence | None
    stats: JudgeStats | None


def _slice(entries: Sequence[tuple[str, _Call]]) -> dict[str, Any]:
    n = len(entries)
    flagged = n < MATRIX_CELLS
    matrix = {h: dict.fromkeys(_DECISIONS, 0) for h in _HUMAN}
    for human, call in entries:
        matrix[human][call.decision] += 1
    answered = [(h, c) for h, c in entries if c.decision in ("PASS", "FAIL")]
    decided = [(h, c) for h, c in entries if c.decision != "FAILURE"]
    pairs = [(h, c.decision.lower()) for h, c in decided]
    agree = sum(1 for a, b in pairs if a == b)

    def column(label: str) -> int:
        return sum(matrix[h][label.upper()] for h in _HUMAN)

    return {
        "n": n,
        "insufficient_for_rates": flagged,
        "matrix": matrix,
        "false_negatives": matrix["fail"]["PASS"],
        "false_positives": matrix["pass"]["FAIL"],
        "over_confident": matrix["unknown"]["PASS"] + matrix["unknown"]["FAIL"],
        "abstention": _rate(column("unknown"), n, flagged),
        "abstention_by_human": {
            h: _rate(matrix[h]["UNKNOWN"], sum(matrix[h].values()), flagged)
            for h in _HUMAN
        },
        "accuracy_on_answered": _rate(
            sum(1 for h, c in answered if h == c.decision.lower()),
            len(answered),
            flagged,
        ),
        "precision": {
            c: _rate(matrix[c][c.upper()], column(c), flagged) for c in ("pass", "fail")
        },
        "recall": {
            c: _rate(
                matrix[c][c.upper()], matrix[c]["PASS"] + matrix[c]["FAIL"], flagged
            )
            for c in ("pass", "fail")
        },
        "agreement": {
            "decided": len(decided),
            "raw": _rate(agree, len(decided), flagged),
            "kappa": None if flagged else _kappa(pairs),
        },
        "confidence_accuracy": {
            level: _rate(
                sum(
                    1
                    for h, c in answered
                    if c.confidence is not None
                    and c.confidence.value == level
                    and h == c.decision.lower()
                ),
                sum(
                    1
                    for _, c in answered
                    if c.confidence is not None and c.confidence.value == level
                ),
                flagged,
            )
            for level in _LEVELS
        },
    }


# ---------------------------------------------------------------- the report


class CalibrationReport:
    """Immutable, content-free report document validated against its JSON Schema."""

    __slots__ = ("_document",)

    def __init__(self, document: Mapping[str, Any]) -> None:
        copied = json.loads(json.dumps(document))
        validate(copied, load_schema("calibration-report"))
        self._document = copied

    @property
    def document(self) -> dict[str, Any]:
        return copy.deepcopy(self._document)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self._document, indent=indent, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> CalibrationReport:
        return cls(_strict_loads(text))

    def __repr__(self) -> str:
        doc = self._document
        return (
            f"CalibrationReport(rubric={doc['rubric']['rubric_id']!r}, "
            f"model_label={doc['model_label']!r}, cases={doc['dataset']['case_count']})"
        )

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, CalibrationReport) and self._document == other._document
        )

    def __hash__(self) -> int:
        return hash(self.to_json(indent=None))


def _build_report(
    judge: SyncLLMJudge | LLMJudge,
    cases: Sequence[CalibrationCase],
    calls: Sequence[Sequence[_Call]],
    *,
    dataset_id: str,
    dataset_sha256: str | None,
    repetitions: int,
    created_at: datetime,
) -> CalibrationReport:
    rubric = judge.rubric
    config_id = judge.identity.configuration_id or ""
    parts = config_id.split(".")
    model_label = ".".join(parts[:-4]) if len(parts) > 4 else config_id
    first = [(c.human_label, per[0]) for c, per in zip(cases, calls, strict=True)]

    def pick(difficulties: tuple[str, ...]) -> list[tuple[str, _Call]]:
        return [
            e for e, c in zip(first, cases, strict=True) if c.difficulty in difficulties
        ]

    headline = pick(("clear", "ambiguous"))
    failures: dict[str, int] = {}
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_total = latency_max = 0
    for per in calls:
        for call in per:
            if call.failure_class is not None:
                failures[call.failure_class] = failures.get(call.failure_class, 0) + 1
            if call.stats is not None:
                if call.stats.input_tokens is not None:
                    tokens_in = (tokens_in or 0) + call.stats.input_tokens
                if call.stats.output_tokens is not None:
                    tokens_out = (tokens_out or 0) + call.stats.output_tokens
                latency_total += call.stats.latency_ms
                latency_max = max(latency_max, call.stats.latency_ms)
    repeatability: dict[str, Any] | None = None
    if repetitions > 1:
        changed = [len({call.decision for call in per}) > 1 for per in calls]
        by_human = {}
        for label in _HUMAN:
            subset = [
                ch
                for ch, c in zip(changed, cases, strict=True)
                if c.human_label == label
            ]
            by_human[label] = _rate(sum(subset), len(subset), len(cases) < MATRIX_CELLS)
        repeatability = {
            "repetitions": repetitions,
            "cases_compared": len(cases),
            "changed": sum(changed),
            "changed_rate": _rate(sum(changed), len(cases), len(cases) < MATRIX_CELLS),
            "changed_by_human": by_human,
        }
    by_dimension: dict[str, int] = {}
    by_difficulty: dict[str, int] = {}
    for case in cases:
        by_dimension[case.dimension.value] = (
            by_dimension.get(case.dimension.value, 0) + 1
        )
        by_difficulty[case.difficulty] = by_difficulty.get(case.difficulty, 0) + 1
    document = {
        "schema": REPORT_SCHEMA_ID,
        "created_at": created_at.astimezone(UTC).isoformat(),
        "rubric": {
            "rubric_id": rubric.rubric_id,
            "rubric_version": rubric.rubric_version,
            "fingerprint": rubric.fingerprint(),
        },
        "model_label": model_label,
        "template_id": TEMPLATE_ID,
        "configuration_id": config_id,
        "min_confidence": parts[-3].removeprefix("mc-") if len(parts) > 4 else "medium",
        "judge_repeats": int(parts[-2][2:]) if len(parts) > 4 else 1,
        "repetitions": repetitions,
        "dataset": {
            "dataset_id": dataset_id,
            "sha256": dataset_sha256,
            "case_count": len(cases),
            "by_dimension": by_dimension,
            "by_difficulty": by_difficulty,
        },
        "headline": _slice(headline),
        "borderline": _slice(pick(("borderline",))),
        "adversarial": _slice(pick(("adversarial",))),
        "repeatability": repeatability,
        "failures_by_class": failures,
        "usage": {
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "latency_ms_total": latency_total,
            "latency_ms_max": latency_max,
        },
        "misjudged_case_ids": [
            c.case_id
            for c, (human, call) in zip(cases, first, strict=True)
            if call.decision != "FAILURE" and call.decision.lower() != human
        ],
        "per_case": [
            {
                "case_id": c.case_id,
                "human_label": c.human_label,
                "difficulty": c.difficulty,
                "decision": call.decision,
            }
            for c, (_, call) in zip(cases, first, strict=True)
        ],
    }
    return CalibrationReport(document)


def _validate_inputs(
    judge: SyncLLMJudge | LLMJudge,
    cases: Sequence[CalibrationCase],
    repetitions: int,
) -> None:
    if not cases or not all(isinstance(c, CalibrationCase) for c in cases):
        raise ValueError("cases must be a non-empty sequence of CalibrationCase")
    if len({c.case_id for c in cases}) != len(cases):
        raise ValueError("case_id values must be unique within a dataset")
    if type(repetitions) is not int or not 1 <= repetitions <= 10:
        raise ValueError("repetitions must be an int in 1..10")
    dimension = judge.rubric.dimension
    if any(c.dimension != dimension for c in cases):
        raise ValueError("every case dimension must match the judge rubric dimension")


def _to_call(evaluation: JudgeEvaluation) -> _Call:
    return _Call(
        evaluation.decision.outcome.name,
        None,
        evaluation.confidence,
        evaluation.stats,
    )


def _failed(error: JudgeError) -> _Call:
    return _Call("FAILURE", type(error).__name__, None, error.stats)


def run_calibration(
    judge: SyncLLMJudge,
    cases: Sequence[CalibrationCase],
    *,
    dataset_id: str,
    dataset_sha256: str | None = None,
    repetitions: int = 1,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> CalibrationReport:
    """Run every case ``repetitions`` times through ``judge`` and report locally.

    The first repetition feeds the confusion matrix (use ``repetitions=1`` to
    measure the production configuration); further repetitions feed only the
    repeatability figures. The only I/O is whatever ``judge``'s provider does.
    """
    _validate_inputs(judge, cases, repetitions)
    calls: list[list[_Call]] = []
    for case in cases:
        per: list[_Call] = []
        for _ in range(repetitions):
            try:
                per.append(_to_call(judge.evaluate_detailed(case.request())))
            except JudgeError as error:
                per.append(_failed(error))
        calls.append(per)
    return _build_report(
        judge,
        cases,
        calls,
        dataset_id=dataset_id,
        dataset_sha256=dataset_sha256,
        repetitions=repetitions,
        created_at=now(),
    )


async def run_calibration_async(
    judge: LLMJudge,
    cases: Sequence[CalibrationCase],
    *,
    dataset_id: str,
    dataset_sha256: str | None = None,
    repetitions: int = 1,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> CalibrationReport:
    """Async twin of :func:`run_calibration` (cases run one after another)."""
    _validate_inputs(judge, cases, repetitions)
    calls: list[list[_Call]] = []
    for case in cases:
        per: list[_Call] = []
        for _ in range(repetitions):
            try:
                outcome = await judge.evaluate_detailed(case.request())
                per.append(_to_call(outcome))
            except JudgeError as error:
                per.append(_failed(error))
        calls.append(per)
    return _build_report(
        judge,
        cases,
        calls,
        dataset_id=dataset_id,
        dataset_sha256=dataset_sha256,
        repetitions=repetitions,
        created_at=now(),
    )


# -------------------------------------------------------------- comparison


@dataclass(frozen=True, slots=True)
class FlippedCase:
    case_id: str
    from_decision: str
    to_decision: str


@dataclass(frozen=True, slots=True)
class ReportComparison:
    """Structured, verdict-free difference between two reports (labels only)."""

    baseline_rubric_version: str
    candidate_rubric_version: str
    baseline_model_label: str
    candidate_model_label: str
    rubric_fingerprint_changed: bool
    common_cases: int
    only_in_baseline: tuple[str, ...]
    only_in_candidate: tuple[str, ...]
    flipped: tuple[FlippedCase, ...]
    net_false_negative_change: int
    net_false_positive_change: int
    net_unknown_change: int
    net_failure_change: int
    judge_agreement_raw: float | None
    judge_agreement_kappa: float | None


def _counts(per_case: Sequence[Mapping[str, Any]]) -> tuple[int, int, int, int]:
    fn = sum(
        1 for c in per_case if c["human_label"] == "fail" and c["decision"] == "PASS"
    )
    fp = sum(
        1 for c in per_case if c["human_label"] == "pass" and c["decision"] == "FAIL"
    )
    unknown = sum(1 for c in per_case if c["decision"] == "UNKNOWN")
    failure = sum(1 for c in per_case if c["decision"] == "FAILURE")
    return fn, fp, unknown, failure


def compare_reports(
    baseline: CalibrationReport, candidate: CalibrationReport
) -> ReportComparison:
    """List flipped ``case_id`` values and net FN/FP change; no pass/fail verdict."""
    a, b = baseline.document, candidate.document
    pa = {c["case_id"]: c for c in a["per_case"]}
    pb = {c["case_id"]: c for c in b["per_case"]}
    common = sorted(set(pa) & set(pb))
    flipped = tuple(
        FlippedCase(i, pa[i]["decision"], pb[i]["decision"])
        for i in common
        if pa[i]["decision"] != pb[i]["decision"]
    )
    decided = [
        (pa[i]["decision"], pb[i]["decision"])
        for i in common
        if "FAILURE" not in (pa[i]["decision"], pb[i]["decision"])
    ]
    raw = (
        round(sum(1 for x, y in decided if x == y) / len(decided), 6)
        if decided
        else None
    )
    kappa = _kappa([(x.lower(), y.lower()) for x, y in decided])
    fa, pa_, ua, xa = _counts(a["per_case"])
    fb, pb_, ub, xb = _counts(b["per_case"])
    return ReportComparison(
        baseline_rubric_version=a["rubric"]["rubric_version"],
        candidate_rubric_version=b["rubric"]["rubric_version"],
        baseline_model_label=a["model_label"],
        candidate_model_label=b["model_label"],
        rubric_fingerprint_changed=a["rubric"]["fingerprint"]
        != b["rubric"]["fingerprint"],
        common_cases=len(common),
        only_in_baseline=tuple(sorted(set(pa) - set(pb))),
        only_in_candidate=tuple(sorted(set(pb) - set(pa))),
        flipped=flipped,
        net_false_negative_change=fb - fa,
        net_false_positive_change=pb_ - pa_,
        net_unknown_change=ub - ua,
        net_failure_change=xb - xa,
        judge_agreement_raw=raw,
        judge_agreement_kappa=kappa,
    )

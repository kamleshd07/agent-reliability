"""The judgment table: what a judge said about each labelled example, per run.

``FAILURE`` (the evaluation ran and produced no verdict) and ``MISSING`` (no
judgment exists for an example that should have one) are different conditions and
are never merged. ``MISSING`` is derived, never stored.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from agent_reliability.experimental.calibration.dataset import ReferenceCase
from agent_reliability.experimental.calibration.fingerprint import (
    JudgeFingerprint,
    ModelDeclaration,
)
from agent_reliability.experimental.judge import (
    FAILURE_CLASS_NAMES,
    JudgeError,
    LLMJudge,
    SyncLLMJudge,
)

__all__ = [
    "MAX_REPETITIONS",
    "Judgment",
    "JudgmentTable",
    "Outcome",
    "collect_judgments",
    "collect_judgments_async",
]

MAX_REPETITIONS: Final = 10
MAX_EXAMPLES: Final = 20_000
_LEVELS: Final = ("high", "medium", "low")
_FAILURE_CLASSES: Final = frozenset(FAILURE_CLASS_NAMES) | {"JudgeError"}


class Outcome(enum.StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    FAILURE = "FAILURE"
    MISSING = "MISSING"

    @property
    def is_verdict(self) -> bool:
        return self in (Outcome.PASS, Outcome.FAIL, Outcome.UNKNOWN)

    @property
    def is_committed(self) -> bool:
        return self in (Outcome.PASS, Outcome.FAIL)


@dataclass(frozen=True, slots=True)
class Judgment:
    example_id: str
    run_index: int
    outcome: Outcome
    failure_class: str | None = None
    confidence_level: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, Outcome) or self.outcome is Outcome.MISSING:
            raise ValueError(
                "a stored judgment is a verdict or a FAILURE, never MISSING"
            )
        if type(self.run_index) is not int or not 0 <= self.run_index < MAX_REPETITIONS:
            raise ValueError("run_index is out of range")
        if self.outcome is Outcome.FAILURE:
            if self.failure_class not in _FAILURE_CLASSES:
                raise ValueError("a FAILURE needs a closed failure_class")
            if self.confidence_level is not None:
                raise ValueError("a FAILURE has no confidence level")
        elif self.failure_class is not None:
            raise ValueError("only a FAILURE carries a failure_class")
        if self.confidence_level is not None and self.confidence_level not in _LEVELS:
            raise ValueError("unknown confidence level")


@dataclass(frozen=True, slots=True)
class JudgmentTable:
    fingerprint: JudgeFingerprint
    rows: tuple[Judgment, ...]

    def __post_init__(self) -> None:
        keys = [(r.example_id, r.run_index) for r in self.rows]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate (example, run) judgment")

    def runs(self, example_id: str) -> tuple[Judgment, ...]:
        return tuple(
            sorted(
                (r for r in self.rows if r.example_id == example_id),
                key=lambda r: r.run_index,
            )
        )

    def outcome(self, example_id: str, run_index: int = 0) -> Outcome:
        for row in self.rows:
            if row.example_id == example_id and row.run_index == run_index:
                return row.outcome
        return Outcome.MISSING

    def row(self, example_id: str, run_index: int = 0) -> Judgment | None:
        for candidate in self.rows:
            if candidate.example_id == example_id and candidate.run_index == run_index:
                return candidate
        return None

    @property
    def runs_available(self) -> int:
        counts: dict[str, int] = {}
        for r in self.rows:
            counts[r.example_id] = counts.get(r.example_id, 0) + 1
        return max(counts.values(), default=0)


def _validate(
    judge: SyncLLMJudge | LLMJudge, cases: Sequence[ReferenceCase], repetitions: int
) -> None:
    if not cases or len(cases) > MAX_EXAMPLES:
        raise ValueError(f"cases must hold 1..{MAX_EXAMPLES} examples")
    if type(repetitions) is not int or not 1 <= repetitions <= MAX_REPETITIONS:
        raise ValueError(f"repetitions must be an int in 1..{MAX_REPETITIONS}")
    dimension = judge.rubric.dimension
    if any(c.case.dimension != dimension for c in cases):
        raise ValueError("every case dimension must match the judge rubric dimension")
    if len({c.case_id for c in cases}) != len(cases):
        raise ValueError("case ids must be unique")


def _failure(case_id: str, run: int, error: JudgeError) -> Judgment:
    name = type(error).__name__
    return Judgment(
        case_id,
        run,
        Outcome.FAILURE,
        name if name in _FAILURE_CLASSES else "JudgeError",
    )


def collect_judgments(
    judge: SyncLLMJudge,
    model: ModelDeclaration,
    cases: Sequence[ReferenceCase],
    *,
    repetitions: int = 1,
) -> JudgmentTable:
    """Run ``judge`` over ``cases`` and tabulate every run.

    The only I/O is whatever the judge's own provider does (the caller's opt-in,
    budgets, limits and retry policy apply unchanged). Only :class:`JudgeError` is
    classified as FAILURE; any other exception propagates.
    """
    _validate(judge, cases, repetitions)
    fingerprint = JudgeFingerprint.for_evaluator(judge, model)
    rows: list[Judgment] = []
    for case in cases:
        for run in range(repetitions):
            try:
                evaluation = judge.evaluate_detailed(case.case.request())
            except JudgeError as error:
                rows.append(_failure(case.case_id, run, error))
                continue
            confidence = evaluation.confidence
            rows.append(
                Judgment(
                    case.case_id,
                    run,
                    Outcome(evaluation.decision.outcome.name),
                    None,
                    None if confidence is None else confidence.value,
                )
            )
    return JudgmentTable(fingerprint, tuple(rows))


async def collect_judgments_async(
    judge: LLMJudge,
    model: ModelDeclaration,
    cases: Sequence[ReferenceCase],
    *,
    repetitions: int = 1,
) -> JudgmentTable:
    """Async twin of :func:`collect_judgments` (cases run one after another)."""
    _validate(judge, cases, repetitions)
    fingerprint = JudgeFingerprint.for_evaluator(judge, model)
    rows: list[Judgment] = []
    for case in cases:
        for run in range(repetitions):
            try:
                evaluation = await judge.evaluate_detailed(case.case.request())
            except JudgeError as error:
                rows.append(_failure(case.case_id, run, error))
                continue
            confidence = evaluation.confidence
            rows.append(
                Judgment(
                    case.case_id,
                    run,
                    Outcome(evaluation.decision.outcome.name),
                    None,
                    None if confidence is None else confidence.value,
                )
            )
    return JudgmentTable(fingerprint, tuple(rows))

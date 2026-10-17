"""Reference rubrics shipped as package data (P29 S06, P29-D12 option A).

Five uncalibrated *examples*: the SDK makes no accuracy claim, the customer owns
calibration. They are plain ``gentlity.rubric/1`` JSON documents.
"""

from __future__ import annotations

from importlib import resources
from typing import Final

from agent_reliability.experimental.judge.rubric import Rubric

__all__ = ["REFERENCE_RUBRIC_IDS", "load_reference_rubric"]

REFERENCE_RUBRIC_IDS: Final = (
    "judge-answer-correctness",
    "judge-groundedness",
    "judge-instruction-adherence",
    "judge-safety-policy",
    "judge-task-completion-evidence",
)


def load_reference_rubric(rubric_id: str) -> Rubric:
    """Load one reference rubric by id (``ValueError`` for an unknown id)."""
    if rubric_id not in REFERENCE_RUBRIC_IDS:
        raise ValueError("unknown reference rubric id")
    text = (
        resources.files("agent_reliability.experimental.judge")
        .joinpath("rubrics", f"{rubric_id}.json")
        .read_text(encoding="utf-8")
    )
    return Rubric.from_json(text)

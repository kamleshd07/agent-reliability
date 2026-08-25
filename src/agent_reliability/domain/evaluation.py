"""Evaluation outcomes.

An ``EvaluationOutcome`` is the categorical result of assessing some
property of an agent run (task success, correctness, policy compliance,
...). It is deliberately a three-valued enum, not a ``bool``: missing or
inconclusive evidence (``UNKNOWN``) is a distinct, first-class outcome,
never collapsed into ``PASS`` or ``FAIL`` and never represented as
``None`` (see docs/DOMAIN_MODEL.md).

This module intentionally does not define the richer M4 ``EvaluationResult``
or a separate "reliability observation" wrapper type. For the ratio
mathematics in ``sli.py``, an eligible observation *is* its outcome — see
ADR-0002. Evaluator execution and provenance live one layer above in
``agent_reliability.evaluation``; the mathematical domain does not depend on
them.
"""

from __future__ import annotations

import enum

__all__ = ["EvaluationOutcome"]


class EvaluationOutcome(enum.Enum):
    """The categorical result of one evaluation.

    ``PASS`` and ``FAIL`` are never inferred from a quantitative score;
    thresholding a score into one of these outcomes is evaluator/policy
    behavior that lives outside this domain kernel (see
    docs/DOMAIN_MODEL.md, "Evaluation score" vs. "Evaluation result").
    """

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"

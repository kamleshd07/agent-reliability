"""Domain layer: pure reliability concepts (Run, Evaluation, SLI, SLO,
Error Budget). See docs/DOMAIN_MODEL.md, docs/SLO_SEMANTICS.md, and
ADR-0002 for the specification these types implement.

Rules for this package, enforced by review (not yet by tooling):

- No imports from ``agent_reliability.adapters``.
- No imports of network, filesystem, or database libraries.
- No dependency on any specific LLM provider or agent framework.
- Values are immutable.

The exports of this subpackage are part of the stable 1.0 contract documented
in docs/GA_CONTRACT.md. They are not re-exported from the
``agent_reliability`` package root, which exposes only ``__version__``.

M4 evaluator execution/provenance lives in the separate
``agent_reliability.evaluation`` namespace and depends on this domain, never
the reverse; see docs/ARCHITECTURE.md.
"""

from __future__ import annotations

from agent_reliability.domain.error_budget import (
    BudgetStatus,
    BurnRate,
    ErrorBudget,
    compute_burn_rate,
    compute_error_budget,
)
from agent_reliability.domain.evaluation import EvaluationOutcome
from agent_reliability.domain.identity import AgentIdentity
from agent_reliability.domain.runs import AgentRun, RunStatus
from agent_reliability.domain.sli import (
    ObservationCounts,
    RatioResult,
    UnknownPolicy,
    compute_ratio,
)
from agent_reliability.domain.slo import (
    ObjectiveDirection,
    Slo,
    SloEvaluation,
    SloStatus,
    evaluate_slo,
)

__all__ = [
    "AgentIdentity",
    "AgentRun",
    "BudgetStatus",
    "BurnRate",
    "ErrorBudget",
    "EvaluationOutcome",
    "ObjectiveDirection",
    "ObservationCounts",
    "RatioResult",
    "RunStatus",
    "Slo",
    "SloEvaluation",
    "SloStatus",
    "UnknownPolicy",
    "compute_burn_rate",
    "compute_error_budget",
    "compute_ratio",
    "evaluate_slo",
]

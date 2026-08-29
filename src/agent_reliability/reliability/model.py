"""Immutable inputs and outputs for local reliability aggregation."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from agent_reliability.domain import (
    BurnRate,
    ErrorBudget,
    EvaluationOutcome,
    RatioResult,
    SloEvaluation,
)
from agent_reliability.domain.measurement_health import (
    MeasurementHealthReason,
    MeasurementHealthReport,
)
from agent_reliability.evaluation import (
    EvaluationProvenance,
    EvaluationResult,
    EvaluatorIdentity,
)

__all__ = [
    "AggregationConflict",
    "AggregationConflictReason",
    "ReliabilityCohort",
    "ReliabilityObservation",
    "ReliabilityReport",
]

_MAX_INDICATOR_LENGTH = 128


def validate_indicator(indicator: str) -> None:
    """Validate a bounded, exact indicator without normalizing it."""
    if not isinstance(indicator, str):
        raise TypeError("indicator must be a str")
    if not indicator or len(indicator) > _MAX_INDICATOR_LENGTH:
        raise ValueError("indicator must contain 1-128 characters")
    if not indicator.isascii() or not indicator.isprintable():
        raise ValueError("indicator must contain printable ASCII characters only")
    if any(character.isspace() for character in indicator):
        raise ValueError("indicator must not contain whitespace")


@dataclass(frozen=True, slots=True)
class ReliabilityObservation:
    """One completed outcome for one indicator and methodology."""

    indicator: str
    outcome: EvaluationOutcome
    provenance: EvaluationProvenance | None = None

    def __post_init__(self) -> None:
        validate_indicator(self.indicator)
        if not isinstance(self.outcome, EvaluationOutcome):
            raise TypeError("outcome must be an EvaluationOutcome")
        if self.provenance is not None and not isinstance(
            self.provenance, EvaluationProvenance
        ):
            raise TypeError("provenance must be EvaluationProvenance or None")

    @classmethod
    def manual(
        cls, *, indicator: str, outcome: EvaluationOutcome
    ) -> ReliabilityObservation:
        """Create an observation from the low-level manual assertion path."""
        return cls(indicator=indicator, outcome=outcome)

    @classmethod
    def from_evaluation(
        cls, *, indicator: str, result: EvaluationResult
    ) -> ReliabilityObservation:
        """Bind an M4 completed result to the indicator it measured."""
        if not isinstance(result, EvaluationResult):
            raise TypeError("result must be an EvaluationResult")
        return cls(
            indicator=indicator,
            outcome=result.outcome,
            provenance=result.provenance,
        )


@dataclass(frozen=True, slots=True)
class ReliabilityCohort:
    """The exact measurement-methodology key for compatible observations."""

    indicator: str
    evaluator_identity: EvaluatorIdentity | None
    deterministic: bool | None

    def __post_init__(self) -> None:
        validate_indicator(self.indicator)
        if self.evaluator_identity is None:
            if self.deterministic is not None:
                raise ValueError("manual cohorts must not declare determinism")
            return
        if not isinstance(self.evaluator_identity, EvaluatorIdentity):
            raise TypeError("evaluator_identity must be EvaluatorIdentity or None")
        if not isinstance(self.deterministic, bool):
            raise TypeError("evaluated cohorts must declare bool determinism")

    @classmethod
    def from_observation(cls, observation: ReliabilityObservation) -> ReliabilityCohort:
        """Project one observation's provenance onto its cohort key."""
        if not isinstance(observation, ReliabilityObservation):
            raise TypeError("observation must be a ReliabilityObservation")
        provenance = observation.provenance
        if provenance is None:
            return cls(
                indicator=observation.indicator,
                evaluator_identity=None,
                deterministic=None,
            )
        return cls(
            indicator=observation.indicator,
            evaluator_identity=provenance.identity,
            deterministic=provenance.deterministic,
        )


class AggregationConflictReason(enum.StrEnum):
    """Bounded structural reasons that a dataset is not one cohort."""

    INDICATOR_MISMATCH = "indicator_mismatch"
    MANUAL_EVALUATED_MIX = "manual_evaluated_mix"
    EVALUATOR_NAME_MISMATCH = "evaluator_name_mismatch"
    EVALUATOR_VERSION_MISMATCH = "evaluator_version_mismatch"
    CONFIGURATION_ID_MISMATCH = "configuration_id_mismatch"
    DETERMINISM_MISMATCH = "determinism_mismatch"
    WINDOW_COHORT_MISMATCH = "window_cohort_mismatch"


@dataclass(frozen=True, slots=True)
class AggregationConflict:
    """A valid dataset for which no reliability number may be produced."""

    reasons: frozenset[AggregationConflictReason]

    def __post_init__(self) -> None:
        if not isinstance(self.reasons, frozenset):
            raise TypeError("reasons must be a frozenset")
        if not self.reasons:
            raise ValueError("reasons must not be empty")
        if any(
            not isinstance(reason, AggregationConflictReason) for reason in self.reasons
        ):
            raise TypeError("every reason must be an AggregationConflictReason")

    @property
    def measurement_health(self) -> MeasurementHealthReport:
        """Incompatible evidence cannot support the requested interpretation."""
        return MeasurementHealthReport.from_reasons(
            frozenset({MeasurementHealthReason.INCOMPATIBLE_EVIDENCE})
        )


@dataclass(frozen=True, slots=True)
class ReliabilityReport:
    """One complete, methodologically valid local reliability calculation."""

    indicator: str
    cohort: ReliabilityCohort | None
    ratio: RatioResult
    slo_evaluation: SloEvaluation
    error_budget: ErrorBudget
    burn_rate: BurnRate | None = None
    measurement_health: MeasurementHealthReport = field(
        default_factory=MeasurementHealthReport
    )

    def __post_init__(self) -> None:
        validate_indicator(self.indicator)
        if self.cohort is not None and not isinstance(self.cohort, ReliabilityCohort):
            raise TypeError("cohort must be ReliabilityCohort or None")
        if self.cohort is not None and self.cohort.indicator != self.indicator:
            raise ValueError("cohort indicator must match report indicator")
        if not isinstance(self.ratio, RatioResult):
            raise TypeError("ratio must be a RatioResult")
        if self.ratio.pass_count + self.ratio.fail_count + self.ratio.unknown_count:
            if self.cohort is None:
                raise ValueError("a non-empty report must have a cohort")
        elif self.cohort is not None:
            raise ValueError("an empty report must not invent a cohort")
        if not isinstance(self.slo_evaluation, SloEvaluation):
            raise TypeError("slo_evaluation must be a SloEvaluation")
        if self.slo_evaluation.ratio != self.ratio:
            raise ValueError("slo_evaluation must reference the report ratio")
        if not isinstance(self.error_budget, ErrorBudget):
            raise TypeError("error_budget must be an ErrorBudget")
        if self.error_budget.ratio != self.ratio:
            raise ValueError("error_budget must reference the report ratio")
        if self.error_budget.slo != self.slo_evaluation.slo:
            raise ValueError("error_budget and SLO evaluation must use the same SLO")
        if self.burn_rate is not None and not isinstance(self.burn_rate, BurnRate):
            raise TypeError("burn_rate must be a BurnRate or None")
        if self.burn_rate is not None and self.burn_rate.slo != self.slo_evaluation.slo:
            raise ValueError("burn_rate and SLO evaluation must use the same SLO")
        if (
            self.burn_rate is not None
            and self.burn_rate.ratio.unknown_policy != self.ratio.unknown_policy
        ):
            raise ValueError("burn_rate and report must use the same UNKNOWN policy")
        if not isinstance(self.measurement_health, MeasurementHealthReport):
            raise TypeError("measurement_health must be a MeasurementHealthReport")

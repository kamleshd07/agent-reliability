"""Pure, provenance-safe orchestration of the M1 reliability kernel."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from agent_reliability.domain import (
    EvaluationOutcome,
    RatioResult,
    Slo,
    UnknownPolicy,
    compute_burn_rate,
    compute_error_budget,
    compute_ratio,
    evaluate_slo,
)
from agent_reliability.evaluation import EvaluatorIdentity
from agent_reliability.reliability.model import (
    AggregationConflict,
    AggregationConflictReason,
    ReliabilityCohort,
    ReliabilityObservation,
    ReliabilityReport,
    validate_indicator,
)

__all__ = [
    "AggregationConflictError",
    "evaluate_reliability",
    "evaluate_reliability_or_raise",
]


class AggregationConflictError(RuntimeError):
    """Raised by ``evaluate_reliability_or_raise`` for an incompatible dataset.

    Carries the original :class:`AggregationConflict` verbatim on
    ``.conflict`` so a caller that wants full programmatic detail (or wants
    to catch this and fall back to the explicit, non-raising
    ``evaluate_reliability`` API) still has it. This exception is a
    convenience for the common "just tell me if it worked" call site; it
    does not resolve, hide, or silently retry the conflict — it surfaces the
    same bounded reasons as an exception instead of a return value.
    """

    def __init__(self, conflict: AggregationConflict) -> None:
        self.conflict = conflict
        reasons = ", ".join(sorted(reason.value for reason in conflict.reasons))
        super().__init__(
            f"reliability observations are not one comparable cohort: {reasons}"
        )


@dataclass(slots=True)
class _ScanState:
    cohort: ReliabilityCohort | None = None
    reasons: set[AggregationConflictReason] = field(default_factory=set)
    seen_manual: bool = False
    seen_evaluated: bool = False
    first_identity: EvaluatorIdentity | None = None
    first_deterministic: bool | None = None

    def inspect(
        self, expected_indicator: str, observation: ReliabilityObservation
    ) -> None:
        if observation.indicator != expected_indicator:
            self.reasons.add(AggregationConflictReason.INDICATOR_MISMATCH)

        if self.cohort is None:
            self.cohort = ReliabilityCohort.from_observation(observation)

        provenance = observation.provenance
        if provenance is None:
            self.seen_manual = True
        else:
            self.seen_evaluated = True
            identity = provenance.identity
            if self.first_identity is None:
                self.first_identity = identity
                self.first_deterministic = provenance.deterministic
            else:
                if identity.name != self.first_identity.name:
                    self.reasons.add(AggregationConflictReason.EVALUATOR_NAME_MISMATCH)
                if identity.version != self.first_identity.version:
                    self.reasons.add(
                        AggregationConflictReason.EVALUATOR_VERSION_MISMATCH
                    )
                if identity.configuration_id != self.first_identity.configuration_id:
                    self.reasons.add(
                        AggregationConflictReason.CONFIGURATION_ID_MISMATCH
                    )
                if provenance.deterministic != self.first_deterministic:
                    self.reasons.add(AggregationConflictReason.DETERMINISM_MISMATCH)

        if self.seen_manual and self.seen_evaluated:
            self.reasons.add(AggregationConflictReason.MANUAL_EVALUATED_MIX)


def _outcomes(
    expected_indicator: str,
    observations: Iterable[ReliabilityObservation],
    state: _ScanState,
) -> Iterator[EvaluationOutcome]:
    for observation in observations:
        if not isinstance(observation, ReliabilityObservation):
            raise TypeError("observations must contain ReliabilityObservation values")
        state.inspect(expected_indicator, observation)
        yield observation.outcome


def _aggregate(
    *,
    indicator: str,
    observations: Iterable[ReliabilityObservation],
    unknown_policy: UnknownPolicy,
) -> tuple[RatioResult, ReliabilityCohort | None, AggregationConflict | None]:
    state = _ScanState()
    ratio = compute_ratio(
        _outcomes(indicator, observations, state), unknown_policy=unknown_policy
    )
    conflict = AggregationConflict(frozenset(state.reasons)) if state.reasons else None
    return ratio, state.cohort, conflict


def evaluate_reliability(
    *,
    indicator: str,
    observations: Iterable[ReliabilityObservation],
    slo: Slo,
    unknown_policy: UnknownPolicy,
    burn_rate_lookback: Iterable[ReliabilityObservation] | None = None,
) -> ReliabilityReport | AggregationConflict:
    """Evaluate one compatible full-window cohort and optional lookback.

    Both iterables are consumed exactly once. Valid incompatibility returns a
    typed conflict and never a partial report. Argument misuse raises normally.
    """
    validate_indicator(indicator)
    if not isinstance(observations, Iterable):
        raise TypeError("observations must be an Iterable")
    if not isinstance(slo, Slo):
        raise TypeError("slo must be an Slo")
    if not isinstance(unknown_policy, UnknownPolicy):
        raise TypeError("unknown_policy must be an UnknownPolicy")
    if burn_rate_lookback is not None and not isinstance(burn_rate_lookback, Iterable):
        raise TypeError("burn_rate_lookback must be an Iterable or None")

    ratio, cohort, conflict = _aggregate(
        indicator=indicator,
        observations=observations,
        unknown_policy=unknown_policy,
    )
    if conflict is not None:
        return conflict

    burn_rate = None
    if burn_rate_lookback is not None:
        lookback_ratio, lookback_cohort, lookback_conflict = _aggregate(
            indicator=indicator,
            observations=burn_rate_lookback,
            unknown_policy=unknown_policy,
        )
        if lookback_conflict is not None:
            return lookback_conflict
        if lookback_cohort is not None and lookback_cohort != cohort:
            return AggregationConflict(
                frozenset({AggregationConflictReason.WINDOW_COHORT_MISMATCH})
            )
        burn_rate = compute_burn_rate(slo, lookback_ratio)

    slo_evaluation = evaluate_slo(slo, ratio)
    return ReliabilityReport(
        indicator=indicator,
        cohort=cohort,
        ratio=ratio,
        slo_evaluation=slo_evaluation,
        error_budget=compute_error_budget(slo, ratio),
        burn_rate=burn_rate,
    )


def evaluate_reliability_or_raise(
    *,
    indicator: str,
    observations: Iterable[ReliabilityObservation],
    slo: Slo,
    unknown_policy: UnknownPolicy,
    burn_rate_lookback: Iterable[ReliabilityObservation] | None = None,
) -> ReliabilityReport:
    """Convenience wrapper: ``evaluate_reliability`` that raises on conflict.

    Identical arguments and identical aggregation behavior as
    ``evaluate_reliability``. The only difference is the return type: a real
    measurement incompatibility (:class:`AggregationConflict`) is raised as
    :class:`AggregationConflictError` instead of being returned, which
    removes the ``isinstance(result, AggregationConflict)`` check at call
    sites that have no recovery path other than failing loudly.

    This does **not** resolve, average, or otherwise weaken a genuine
    conflict — it only changes how an unrecoverable one is surfaced. Call
    sites that want to inspect or handle a conflict programmatically (for
    example, to retry with a narrower observation set) should keep using
    ``evaluate_reliability`` directly and check the return type explicitly.
    """
    result = evaluate_reliability(
        indicator=indicator,
        observations=observations,
        slo=slo,
        unknown_policy=unknown_policy,
        burn_rate_lookback=burn_rate_lookback,
    )
    if isinstance(result, AggregationConflict):
        raise AggregationConflictError(result)
    return result

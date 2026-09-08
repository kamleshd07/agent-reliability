"""Coverage for the DX-1 evaluate_reliability_or_raise convenience API.

(The file keeps its original "m8" module name for historical git-blame
continuity; see CHANGELOG.md for why this milestone is labeled
"DX-1 — Developer Adoption", not "M8", in release-facing docs.)
"""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction

import pytest

from agent_reliability.domain import (
    EvaluationOutcome,
    ObjectiveDirection,
    Slo,
    UnknownPolicy,
)
from agent_reliability.evaluation import (
    ContainsEvaluator,
    EvaluationProvenance,
    EvaluatorIdentity,
)
from agent_reliability.reliability import (
    AggregationConflictError,
    ReliabilityObservation,
    ReliabilityReport,
    evaluate_reliability,
    evaluate_reliability_or_raise,
)

_SLO = Slo("task-success", Fraction(3, 4), ObjectiveDirection.AT_LEAST)


def _observation(
    outcome: EvaluationOutcome, version: str = "1"
) -> ReliabilityObservation:
    return ReliabilityObservation(
        indicator="task_success",
        outcome=outcome,
        provenance=EvaluationProvenance(
            EvaluatorIdentity("judge", version),
            datetime(2026, 1, 1, tzinfo=UTC),
            True,
        ),
    )


def test_or_raise_returns_the_same_report_as_the_explicit_api() -> None:
    observations = [_observation(EvaluationOutcome.PASS)] * 3 + [
        _observation(EvaluationOutcome.FAIL)
    ]
    explicit = evaluate_reliability(
        indicator="task_success",
        observations=observations,
        slo=_SLO,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    convenience = evaluate_reliability_or_raise(
        indicator="task_success",
        observations=observations,
        slo=_SLO,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    assert isinstance(explicit, ReliabilityReport)
    assert explicit == convenience


def test_or_raise_raises_on_genuine_conflict_carrying_the_original_conflict() -> None:
    observations = [
        _observation(EvaluationOutcome.PASS, version="1"),
        _observation(EvaluationOutcome.PASS, version="2"),
    ]
    with pytest.raises(AggregationConflictError) as excinfo:
        evaluate_reliability_or_raise(
            indicator="task_success",
            observations=observations,
            slo=_SLO,
            unknown_policy=UnknownPolicy.EXCLUDE,
        )
    conflict = excinfo.value.conflict
    reasons = {reason.value for reason in conflict.reasons}
    assert "evaluator_version_mismatch" in reasons
    # The exception message names the conflict; it does not fabricate a number.
    assert "not one comparable cohort" in str(excinfo.value)


def test_or_raise_does_not_resolve_or_hide_the_conflict() -> None:
    """The convenience API must raise, not silently pick a winner."""
    observations = [
        _observation(EvaluationOutcome.PASS, version="a"),
        _observation(EvaluationOutcome.PASS, version="b"),
    ]
    explicit = evaluate_reliability(
        indicator="task_success",
        observations=observations,
        slo=_SLO,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    assert not isinstance(explicit, ReliabilityReport)
    with pytest.raises(AggregationConflictError):
        evaluate_reliability_or_raise(
            indicator="task_success",
            observations=observations,
            slo=_SLO,
            unknown_policy=UnknownPolicy.EXCLUDE,
        )


def test_or_raise_propagates_ordinary_argument_errors_unchanged() -> None:
    with pytest.raises(TypeError, match="slo must be an Slo"):
        evaluate_reliability_or_raise(
            indicator="task_success",
            observations=[],
            slo=object(),  # type: ignore[arg-type]
            unknown_policy=UnknownPolicy.EXCLUDE,
        )


# ---------------------------------------------------------------------------
# EvaluatorIdentity / cohort aggregation contract (documentation hardening
# only — this is pre-existing, deliberate behavior; these tests demonstrate
# it, they do not change it. See the "Configuration-identity warning" added
# to each of the five new evaluators' docstrings in
# agent_reliability/evaluation/builtins.py.)
# ---------------------------------------------------------------------------


def _observation_with_identity(
    outcome: EvaluationOutcome, identity: EvaluatorIdentity
) -> ReliabilityObservation:
    return ReliabilityObservation(
        indicator="task_success",
        outcome=outcome,
        provenance=EvaluationProvenance(
            identity,
            datetime(2026, 1, 1, tzinfo=UTC),
            True,
        ),
    )


def test_same_evaluator_identity_with_different_configuration_is_one_cohort() -> None:
    """Documents the existing, unchanged contract: EvaluatorIdentity (name +
    version [+ configuration_id]) is the cohort key. Two observations
    produced by evaluator instances with the *same* EvaluatorIdentity but
    different underlying configuration (here: simulated by different
    ContainsEvaluator substrings feeding the same identity) still aggregate
    into one comparable cohort with no AggregationConflict — because nothing
    about ContainsEvaluator's ``substring``/``case_sensitive`` fields, or any
    other evaluator's non-identity configuration, participates in the cohort
    key at all.
    """
    shared_identity = EvaluatorIdentity("contains-refund", "1")
    first_config = ContainsEvaluator(shared_identity, "refund")
    second_config = ContainsEvaluator(shared_identity, "escalation")
    assert first_config.identity == second_config.identity

    observations = [
        _observation_with_identity(EvaluationOutcome.PASS, shared_identity),
        _observation_with_identity(EvaluationOutcome.FAIL, shared_identity),
    ]
    result = evaluate_reliability_or_raise(
        indicator="task_success",
        observations=observations,
        slo=_SLO,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    assert isinstance(result, ReliabilityReport)
    assert result.cohort is not None
    assert result.cohort.evaluator_identity == shared_identity


def test_different_configuration_id_does_separate_the_cohort() -> None:
    """The existing identity mechanism already supports separating cohorts
    via ``configuration_id`` (no new mechanism added here): two observations
    that share evaluator name/version but declare a different
    ``configuration_id`` are a genuine conflict, not silently merged."""
    observations = [
        _observation_with_identity(
            EvaluationOutcome.PASS,
            EvaluatorIdentity("contains-refund", "1", configuration_id="strict"),
        ),
        _observation_with_identity(
            EvaluationOutcome.PASS,
            EvaluatorIdentity("contains-refund", "1", configuration_id="lenient"),
        ),
    ]
    with pytest.raises(AggregationConflictError) as excinfo:
        evaluate_reliability_or_raise(
            indicator="task_success",
            observations=observations,
            slo=_SLO,
            unknown_policy=UnknownPolicy.EXCLUDE,
        )
    reasons = {reason.value for reason in excinfo.value.conflict.reasons}
    assert "configuration_id_mismatch" in reasons

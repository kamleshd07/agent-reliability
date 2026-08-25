from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone, tzinfo

import pytest

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation import (
    EvaluationDecision,
    EvaluationExecutionFailure,
    EvaluationFailureStage,
    EvaluationProvenance,
    EvaluationResult,
    EvaluatorIdentity,
)

NOW = datetime(2026, 8, 25, tzinfo=UTC)


def test_evaluator_identity_has_opaque_value_semantics() -> None:
    first = EvaluatorIdentity(
        name="task-success",
        version="policy-v7",
        configuration_id="threshold-095",
    )
    second = EvaluatorIdentity(
        name="task-success",
        version="policy-v7",
        configuration_id="threshold-095",
    )
    assert first == second
    assert hash(first) == hash(second)
    assert first.version == "policy-v7"


@pytest.mark.parametrize(
    "name",
    ["", "Task-Success", "-leading", "trailing-", "has space", "évaluator"],
)
def test_evaluator_identity_rejects_noncanonical_names(name: str) -> None:
    with pytest.raises(ValueError, match="evaluator name"):
        EvaluatorIdentity(name=name, version="1")


@pytest.mark.parametrize("version", ["", "has space", "bad/value", "x" * 129])
def test_evaluator_identity_rejects_invalid_versions(version: str) -> None:
    with pytest.raises(ValueError, match="version"):
        EvaluatorIdentity(name="task-success", version=version)


def test_evaluator_identity_accepts_documented_version_examples_and_bounds() -> None:
    for version in ("1.0.0", "2026-08-25", "build-184", "sha-abcd123", "x" * 128):
        assert EvaluatorIdentity("task-success", version).version == version


def test_identity_result_and_provenance_are_immutable() -> None:
    identity = EvaluatorIdentity("task-success", "1")
    provenance = EvaluationProvenance(identity, NOW, True)
    result = EvaluationResult(EvaluationOutcome.PASS, provenance, "equal")
    with pytest.raises(FrozenInstanceError):
        identity.version = "2"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        provenance.deterministic = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.outcome = EvaluationOutcome.FAIL  # type: ignore[misc]


def test_provenance_normalizes_aware_time_to_utc_and_rejects_naive_time() -> None:
    identity = EvaluatorIdentity("task-success", "1")
    offset = timezone(timedelta(hours=5, minutes=30))
    provenance = EvaluationProvenance(
        identity, datetime(2026, 8, 25, 12, tzinfo=offset), True
    )
    assert provenance.evaluated_at.tzinfo is UTC
    assert provenance.evaluated_at.hour == 6
    assert provenance.evaluated_at.minute == 30
    with pytest.raises(ValueError, match="timezone-aware"):
        EvaluationProvenance(identity, datetime(2026, 8, 25), True)


def test_provenance_rejects_tzinfo_with_undefined_utc_offset() -> None:
    """A ``tzinfo`` object may be set while ``utcoffset()`` still returns
    ``None`` (a documented, if pathological, corner of the datetime data
    model — e.g. an incompletely implemented custom tzinfo). ``evaluated_at``
    must be rejected the same way a naive datetime is, not accepted with an
    undefined offset."""

    class UndefinedOffsetTzinfo(tzinfo):
        def utcoffset(self, dt: object) -> None:
            return None

        def tzname(self, dt: object) -> None:
            return None

        def dst(self, dt: object) -> None:
            return None

    identity = EvaluatorIdentity("task-success", "1")
    pathological = datetime(2026, 8, 25, tzinfo=UndefinedOffsetTzinfo())
    assert pathological.tzinfo is not None  # tzinfo is set...
    assert pathological.utcoffset() is None  # ...but the offset is undefined

    with pytest.raises(ValueError, match="timezone-aware"):
        EvaluationProvenance(identity, pathological, True)


@pytest.mark.parametrize("outcome", list(EvaluationOutcome))
def test_result_preserves_every_m1_outcome(outcome: EvaluationOutcome) -> None:
    provenance = EvaluationProvenance(EvaluatorIdentity("task-success", "1"), NOW, True)
    assert EvaluationResult(outcome, provenance).outcome is outcome


@pytest.mark.parametrize("reason", ["", "HasUpper", "has space", "x" * 129])
def test_reason_code_is_bounded_machine_data(reason: str) -> None:
    with pytest.raises(ValueError, match="reason_code"):
        EvaluationDecision(EvaluationOutcome.UNKNOWN, reason)


def test_execution_failure_is_not_an_evaluation_result() -> None:
    failure = EvaluationExecutionFailure(
        identity=EvaluatorIdentity("task-success", "1"),
        stage=EvaluationFailureStage.EVALUATION,
        exception_type="RuntimeError",
    )
    assert not isinstance(failure, EvaluationResult)
    assert not hasattr(failure, "outcome")
    assert not hasattr(failure, "exception")


def test_result_values_reject_wrong_runtime_types() -> None:
    identity = EvaluatorIdentity("task-success", "1")
    provenance = EvaluationProvenance(identity, NOW, True)
    with pytest.raises(TypeError, match="outcome"):
        EvaluationDecision("pass")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="identity"):
        EvaluationProvenance("wrong", NOW, True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="deterministic"):
        EvaluationProvenance(identity, NOW, 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="outcome"):
        EvaluationResult("pass", provenance)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="provenance"):
        EvaluationResult(EvaluationOutcome.PASS, "wrong")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="identity"):
        EvaluationExecutionFailure(  # type: ignore[arg-type]
            "wrong", EvaluationFailureStage.EVALUATION, "RuntimeError"
        )
    with pytest.raises(TypeError, match="stage"):
        EvaluationExecutionFailure(identity, "evaluation", "RuntimeError")  # type: ignore[arg-type]


def test_execution_failure_rejects_unsafe_exception_type() -> None:
    with pytest.raises(ValueError, match="exception_type"):
        EvaluationExecutionFailure(
            None, EvaluationFailureStage.EVALUATION, "contains whitespace"
        )

"""Coverage for agent_reliability.reporting (format_report / report_to_dict)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from fractions import Fraction

import pytest

from agent_reliability.domain import (
    EvaluationOutcome,
    ObjectiveDirection,
    Slo,
    UnknownPolicy,
)
from agent_reliability.evaluation import EvaluationProvenance, EvaluatorIdentity
from agent_reliability.reliability import ReliabilityObservation, evaluate_reliability
from agent_reliability.reporting import format_report, report_to_dict

_SLO = Slo("task-success", Fraction(3, 4), ObjectiveDirection.AT_LEAST)


def _observation(outcome: EvaluationOutcome) -> ReliabilityObservation:
    return ReliabilityObservation(
        indicator="task_success",
        outcome=outcome,
        provenance=EvaluationProvenance(
            EvaluatorIdentity("judge", "1"),
            datetime(2026, 1, 1, tzinfo=UTC),
            True,
        ),
    )


def _report(observations: list[ReliabilityObservation]):
    result = evaluate_reliability(
        indicator="task_success",
        observations=observations,
        slo=_SLO,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    assert not hasattr(result, "reasons")  # not an AggregationConflict
    return result


def test_format_report_shows_counts_and_reliability() -> None:
    report = _report(
        [_observation(EvaluationOutcome.PASS)] * 3
        + [_observation(EvaluationOutcome.FAIL)]
    )
    text = format_report(report)
    assert "Indicator: task_success" in text
    assert "pass=3 fail=1 unknown=0" in text
    assert "Reliability: 75.00%" in text
    assert "status=MET" in text
    assert "Measurement health: HEALTHY" in text


def test_format_report_renders_no_data_not_zero_percent() -> None:
    report = _report([])
    text = format_report(report)
    assert "Reliability: NO DATA" in text
    assert "0.00%" not in text.split("Reliability:")[1].split("\n")[0]


def test_format_report_reads_engine_field_does_not_recompute() -> None:
    """The formatter must show exactly the engine's own pass_ratio, not an
    independently recomputed one. We corrupt nothing; we assert the string
    is derived from report.ratio.pass_ratio by constructing an equivalent
    percentage from that same field and comparing."""
    report = _report(
        [_observation(EvaluationOutcome.PASS)] * 2
        + [_observation(EvaluationOutcome.FAIL)]
    )
    expected_percent = f"{float(report.ratio.pass_ratio):.2%}"
    text = format_report(report)
    assert f"Reliability: {expected_percent}" in text


def test_format_report_rejects_wrong_type() -> None:
    with pytest.raises(TypeError, match="ReliabilityReport"):
        format_report(object())  # type: ignore[arg-type]


def test_report_to_dict_is_json_dumpable_and_deterministic() -> None:
    report = _report([_observation(EvaluationOutcome.PASS)])
    payload = report_to_dict(report)
    serialized = json.dumps(payload)  # must not raise
    assert json.loads(serialized) == payload
    # Determinism: calling again produces an identical structure.
    assert report_to_dict(report) == payload


def test_report_to_dict_no_data_uses_null_not_zero() -> None:
    report = _report([])
    payload = report_to_dict(report)
    assert payload["reliability"]["pass_ratio"] is None
    assert payload["reliability"]["pass_ratio_float"] is None
    assert payload["error_budget"]["remaining_fraction"] is None


def test_report_to_dict_shape_is_exactly_bounded() -> None:
    """Adversarial: no arbitrary/unbounded payload data, exact key set."""
    report = _report([_observation(EvaluationOutcome.PASS)])
    payload = report_to_dict(report)
    assert set(payload.keys()) == {
        "indicator",
        "cohort",
        "counts",
        "unknown_policy",
        "reliability",
        "slo",
        "error_budget",
        "burn_rate",
        "measurement_health",
    }
    assert set(payload["counts"].keys()) == {
        "pass",
        "fail",
        "unknown",
        "considered_pass",
        "considered_fail",
        "considered",
    }
    assert set(payload["measurement_health"].keys()) == {"health", "reasons"}
    for value in payload.values():
        assert isinstance(value, dict | list | str | int | float | bool | type(None))


def test_report_to_dict_exact_fraction_is_lossless() -> None:
    report = _report(
        [_observation(EvaluationOutcome.PASS)] * 2
        + [_observation(EvaluationOutcome.FAIL)]
    )
    payload = report_to_dict(report)
    fraction = payload["reliability"]["pass_ratio"]
    assert fraction == {"numerator": 2, "denominator": 3}


def test_report_to_dict_rejects_wrong_type() -> None:
    with pytest.raises(TypeError, match="ReliabilityReport"):
        report_to_dict(object())  # type: ignore[arg-type]


def _report_with_burn_rate():
    full_window = [_observation(EvaluationOutcome.PASS)] * 3 + [
        _observation(EvaluationOutcome.FAIL)
    ]
    lookback = [_observation(EvaluationOutcome.FAIL)] * 2
    result = evaluate_reliability(
        indicator="task_success",
        observations=full_window,
        slo=_SLO,
        unknown_policy=UnknownPolicy.EXCLUDE,
        burn_rate_lookback=lookback,
    )
    assert not hasattr(result, "reasons")
    return result


def test_format_report_includes_burn_rate_line_when_present() -> None:
    report = _report_with_burn_rate()
    assert report.burn_rate is not None
    text = format_report(report)
    assert "Burn rate: status=" in text
    expected_value = f"{float(report.burn_rate.value):.2f}x"  # type: ignore[arg-type]
    assert expected_value in text


def test_report_to_dict_includes_burn_rate_when_present() -> None:
    report = _report_with_burn_rate()
    payload = report_to_dict(report)
    assert payload["burn_rate"] is not None
    assert payload["burn_rate"]["status"] == report.burn_rate.status.value  # type: ignore[union-attr]
    assert set(payload["burn_rate"].keys()) == {"status", "value", "value_float"}

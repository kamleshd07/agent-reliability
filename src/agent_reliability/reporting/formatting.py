"""Local presentation of a canonical :class:`ReliabilityReport`.

This module never recomputes reliability, SLO status, error-budget
consumption, or burn rate. Every value shown or serialized here is read
directly from fields the M1/M5 engine already produced
(``report.ratio``, ``report.slo_evaluation``, ``report.error_budget``,
``report.burn_rate``, ``report.measurement_health``) — this module is a
pure, side-effect-free renderer of those fields, never a second source of
truth for the numbers themselves.

Both functions operate purely on the structural report values (indicator
name, evaluator identity, counts, ratios, SLO name/target/direction,
bounded status enums, and bounded measurement-health reasons). Neither
function accepts, inspects, or serializes arbitrary application payloads —
there is nothing on ``ReliabilityReport`` to leak in the first place, since
the domain model itself never carries raw prompts, responses, or tool data.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from agent_reliability.reliability.model import ReliabilityReport

__all__ = ["format_report", "report_to_dict"]


def _percent(value: Fraction | None) -> str:
    """Render a considered-fraction as a percentage, or ``"NO DATA"``.

    ``None`` means "no considered observations" (see ``RatioResult`` and
    ``ErrorBudget``/``BurnRate`` docstrings) — it must never be shown as
    ``0.00%``, which would falsely claim total unreliability.
    """
    return "NO DATA" if value is None else f"{float(value):.2%}"


def _multiplier(value: Fraction | None) -> str:
    """Render a burn-rate-shaped value as a multiplier, or ``"NO DATA"``."""
    return "NO DATA" if value is None else f"{float(value):.2f}x"


def format_report(report: ReliabilityReport) -> str:
    """Render ``report`` as a stable, human-readable multi-line text block.

    Shows observation counts (pass/fail/unknown, kept separate — never
    summed into one "success" number), the unknown-outcome policy applied,
    reliability (or ``"NO DATA"`` when there are no considered
    observations), the SLO target/direction/status, the error budget
    status/remaining fraction, the burn rate when supplied, and measurement
    health with its bounded reason codes.

    This layout is a display convenience, not a wire format: exact
    whitespace and line order may change between minor releases. Use
    ``report_to_dict`` for a stable machine-readable shape.
    """
    if not isinstance(report, ReliabilityReport):
        raise TypeError("report must be a ReliabilityReport")

    ratio = report.ratio
    slo = report.slo_evaluation.slo
    budget = report.error_budget
    health = report.measurement_health

    lines = [
        f"Indicator: {report.indicator}",
        (
            f"Observations: pass={ratio.pass_count} fail={ratio.fail_count} "
            f"unknown={ratio.unknown_count} considered={ratio.considered_count} "
            f"(unknown_policy={ratio.unknown_policy.value})"
        ),
        f"Reliability: {_percent(ratio.pass_ratio)}",
        (
            f"SLO: {slo.name} target={_percent(slo.target)} "
            f"direction={slo.direction.value} "
            f"status={report.slo_evaluation.status.value.upper()}"
        ),
        (
            f"Error budget: status={budget.status.value} "
            f"remaining={_percent(budget.remaining_fraction)}"
        ),
    ]
    if report.burn_rate is not None:
        lines.append(
            f"Burn rate: status={report.burn_rate.status.value} "
            f"value={_multiplier(report.burn_rate.value)}"
        )
    reasons = ", ".join(sorted(reason.value for reason in health.reasons))
    lines.append(
        f"Measurement health: {health.health.value.upper()}"
        + (f" (reasons: {reasons})" if reasons else "")
    )
    return "\n".join(lines)


def _fraction_to_dict(value: Fraction | None) -> dict[str, int] | None:
    """Represent an exact ``Fraction`` losslessly as JSON-compatible ints."""
    if value is None:
        return None
    return {"numerator": value.numerator, "denominator": value.denominator}


def report_to_dict(report: ReliabilityReport) -> dict[str, Any]:
    """Render ``report`` as JSON-compatible primitive structures.

    The return value is safe to pass to ``json.dumps`` and contains only
    ``dict``/``list``/``str``/``int``/``float``/``bool``/``None`` values, no
    proprietary wire envelope, and no networking. Fraction-valued fields are
    represented losslessly as a ``{"numerator": int, "denominator": int}``
    pair rather than a lossy ``float`` (the canonical engine uses exact
    ``fractions.Fraction`` arithmetic; this function preserves that when it
    matters and additionally exposes a rounded ``float`` copy for callers
    that only want a display number).

    The shape below is exhaustive and stable for a given report; it never
    grows an extra key for unexpected report content because
    ``ReliabilityReport`` itself has no open-ended payload field.
    """
    if not isinstance(report, ReliabilityReport):
        raise TypeError("report must be a ReliabilityReport")

    ratio = report.ratio
    slo = report.slo_evaluation.slo
    budget = report.error_budget
    health = report.measurement_health
    cohort = report.cohort

    cohort_dict: dict[str, Any] | None = None
    if cohort is not None:
        identity = cohort.evaluator_identity
        cohort_dict = {
            "indicator": cohort.indicator,
            "evaluator": (
                None
                if identity is None
                else {
                    "name": identity.name,
                    "version": identity.version,
                    "configuration_id": identity.configuration_id,
                }
            ),
            "deterministic": cohort.deterministic,
        }

    burn_rate_dict: dict[str, Any] | None = None
    if report.burn_rate is not None:
        burn_rate_dict = {
            "status": report.burn_rate.status.value,
            "value": _fraction_to_dict(report.burn_rate.value),
            "value_float": (
                None
                if report.burn_rate.value is None
                else float(report.burn_rate.value)
            ),
        }

    return {
        "indicator": report.indicator,
        "cohort": cohort_dict,
        "counts": {
            "pass": ratio.pass_count,
            "fail": ratio.fail_count,
            "unknown": ratio.unknown_count,
            "considered_pass": ratio.considered_pass_count,
            "considered_fail": ratio.considered_fail_count,
            "considered": ratio.considered_count,
        },
        "unknown_policy": ratio.unknown_policy.value,
        "reliability": {
            "pass_ratio": _fraction_to_dict(ratio.pass_ratio),
            "pass_ratio_float": (
                None if ratio.pass_ratio is None else float(ratio.pass_ratio)
            ),
            "fail_ratio": _fraction_to_dict(ratio.fail_ratio),
            "fail_ratio_float": (
                None if ratio.fail_ratio is None else float(ratio.fail_ratio)
            ),
        },
        "slo": {
            "name": slo.name,
            "target": _fraction_to_dict(slo.target),
            "target_float": float(slo.target),
            "direction": slo.direction.value,
            "status": report.slo_evaluation.status.value,
        },
        "error_budget": {
            "status": budget.status.value,
            "allowed_bad_fraction": _fraction_to_dict(budget.allowed_bad_fraction),
            "allowed_bad_events": _fraction_to_dict(budget.allowed_bad_events),
            "observed_bad_events": budget.observed_bad_events,
            "consumption_ratio": _fraction_to_dict(budget.consumption_ratio),
            "remaining_fraction": _fraction_to_dict(budget.remaining_fraction),
            "remaining_fraction_float": (
                None
                if budget.remaining_fraction is None
                else float(budget.remaining_fraction)
            ),
        },
        "burn_rate": burn_rate_dict,
        "measurement_health": {
            "health": health.health.value,
            "reasons": sorted(reason.value for reason in health.reasons),
        },
    }

"""Framework-neutral SLO assertion for tests and scripts.

Usable from plain ``assert``-based scripts, ``unittest``, ``pytest``, or any
other runner: ``assert_slo_met`` raises a plain ``AssertionError`` and adds
no runtime dependency (not even on ``pytest``). It reads
``SloStatus``/``ReliabilityReport`` fields the engine already computed; it
never recomputes reliability or SLO status itself, and it never invents a
policy the engine did not already decide (in particular, it does not decide
how ``UNKNOWN`` observations affect the ratio — that is
``UnknownPolicy``'s job, chosen when the report was built).
"""

from __future__ import annotations

from agent_reliability.domain.slo import SloStatus
from agent_reliability.reliability.model import AggregationConflict, ReliabilityReport

__all__ = ["assert_slo_met"]


def assert_slo_met(
    report: ReliabilityReport | AggregationConflict, *, message: str | None = None
) -> None:
    """Raise ``AssertionError`` unless ``report``'s SLO status is ``MET``.

    Accepts the same ``ReliabilityReport | AggregationConflict`` union that
    ``evaluate_reliability`` returns, so it can be called directly on that
    result without an intermediate ``isinstance`` check. An
    :class:`AggregationConflict` is never treated as success: it fails the
    assertion with its bounded conflict reasons, exactly like a breached SLO
    would, because "the data could not even be compared" is not a passing
    result. ``SloStatus.UNKNOWN`` (no considered observations — see
    ``evaluate_slo``) also fails the assertion with the same
    ``"NO DATA"`` wording ``agent_reliability.reporting`` uses, rather than
    reading the missing evidence as passing.

    ``message`` is prepended to the assertion text when supplied.

    The assertion message includes only bounded, structural fields already
    on the report: indicator/SLO names, pass/fail/unknown counts, the
    unknown-outcome policy, and the observed/target ratios. It never
    includes application payloads, because the domain report itself does
    not carry any.
    """
    if isinstance(report, AggregationConflict):
        reasons = ", ".join(sorted(reason.value for reason in report.reasons))
        detail = (
            "reliability observations are not one comparable cohort, so no "
            f"SLO could be evaluated: {reasons}"
        )
        raise AssertionError(_prefixed(message, detail))
    if not isinstance(report, ReliabilityReport):
        raise TypeError("report must be a ReliabilityReport or AggregationConflict")

    status = report.slo_evaluation.status
    if status is SloStatus.MET:
        return

    ratio = report.ratio
    slo = report.slo_evaluation.slo
    observed = (
        "NO DATA" if ratio.pass_ratio is None else f"{float(ratio.pass_ratio):.2%}"
    )
    target = f"{float(slo.target):.2%}"
    status_text = "NO DATA" if status is SloStatus.UNKNOWN else status.value.upper()
    detail = (
        f"SLO '{slo.name}' on indicator '{report.indicator}' was not met "
        f"(status={status_text}, observed_reliability={observed}, "
        f"target={target}, direction={slo.direction.value}, "
        f"pass={ratio.pass_count}, fail={ratio.fail_count}, "
        f"unknown={ratio.unknown_count}, unknown_policy={ratio.unknown_policy.value})"
    )
    raise AssertionError(_prefixed(message, detail))


def _prefixed(message: str | None, detail: str) -> str:
    return detail if message is None else f"{message}: {detail}"

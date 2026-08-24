"""Error budget and burn rate.

Both are, mechanically, the same computation —
``observed_bad_fraction / allowed_bad_fraction`` — applied to different
observation windows: a full window for the cumulative error budget, an
arbitrary shorter lookback for burn rate (docs/SLO_SEMANTICS.md,
ADR-0002). ``_consumption`` below is the single shared implementation;
``compute_error_budget`` and ``compute_burn_rate`` are thin, differently
-shaped public wrappers around it, so the two can never silently drift
apart.

Three states are distinguished (``BudgetStatus``), because two
different situations both prevent an ordinary finite number from being
produced, and they are not the same situation:

- ``NO_DATA``: no considered observations at all (division is
  undefined because there is nothing to divide).
- ``ZERO_TOLERANCE_INTACT`` / ``ZERO_TOLERANCE_EXCEEDED``: data exists,
  but the SLO's target is 100% (``AT_LEAST``) or 0% (``AT_MOST``), so
  ``allowed_bad_fraction == 0``. Zero observed bad events against a
  zero-tolerance budget is well-defined (fully intact); any observed
  bad event makes the true consumption unbounded, which
  ``fractions.Fraction`` cannot represent (it has no infinity) — this
  is reported as its own status with the numeric value left ``None``,
  rather than smuggled in as a ``float('inf')``.

See ADR-0002 for the full reasoning and alternatives considered.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from fractions import Fraction

from agent_reliability.domain.sli import RatioResult
from agent_reliability.domain.slo import Slo

__all__ = [
    "BudgetStatus",
    "BurnRate",
    "ErrorBudget",
    "compute_burn_rate",
    "compute_error_budget",
]


class BudgetStatus(enum.Enum):
    """Shared status for any bad-fraction-over-allowed-fraction division.

    Used by both ``ErrorBudget`` (cumulative, full-window) and
    ``BurnRate`` (a lookback window) because they are the same
    underlying division — see module docstring.
    """

    MEASURED = "measured"
    NO_DATA = "no_data"
    ZERO_TOLERANCE_INTACT = "zero_tolerance_intact"
    ZERO_TOLERANCE_EXCEEDED = "zero_tolerance_exceeded"


def _consumption(
    allowed_bad_fraction: Fraction, ratio: RatioResult
) -> tuple[BudgetStatus, Fraction | None]:
    """The single shared computation behind both public functions below.

    Returns ``(status, value)`` where ``value`` is
    ``observed_bad_fraction / allowed_bad_fraction`` when that division
    is well-defined, and ``None`` otherwise (with ``status`` explaining
    why — see module docstring).
    """
    observed_bad_fraction = ratio.fail_ratio
    if observed_bad_fraction is None:
        return BudgetStatus.NO_DATA, None
    if allowed_bad_fraction == 0:
        if observed_bad_fraction == 0:
            return BudgetStatus.ZERO_TOLERANCE_INTACT, Fraction(0)
        return BudgetStatus.ZERO_TOLERANCE_EXCEEDED, None
    return BudgetStatus.MEASURED, observed_bad_fraction / allowed_bad_fraction


@dataclass(frozen=True)
class ErrorBudget:
    """The error budget implied by an ``Slo`` over one observation window.

    ``allowed_bad_events`` may be non-integral (e.g. ``4.995`` for a
    0.5% allowance over 999 considered events) — this is kept exact via
    ``Fraction`` rather than rounded, per docs/SLO_SEMANTICS.md.
    ``observed_bad_events`` is always a plain, exact integer count (it is
    never reconstructed by multiplying a ratio back out).

    ``consumption_ratio`` and ``remaining_fraction`` are ``None`` iff
    ``status`` is ``NO_DATA`` or ``ZERO_TOLERANCE_EXCEEDED``.
    ``remaining_fraction`` is not clamped to ``[0, 1]``: a negative value
    means the budget is exhausted and exceeded, and the magnitude is the
    size of the breach (docs/SLO_SEMANTICS.md).
    """

    slo: Slo
    ratio: RatioResult
    status: BudgetStatus
    allowed_bad_fraction: Fraction
    allowed_bad_events: Fraction
    observed_bad_events: int
    consumption_ratio: Fraction | None
    remaining_fraction: Fraction | None


def compute_error_budget(slo: Slo, ratio: RatioResult) -> ErrorBudget:
    """Compute the error budget implied by ``slo`` over ``ratio``'s window."""
    allowed_bad_fraction = slo.allowed_bad_fraction
    status, consumption_ratio = _consumption(allowed_bad_fraction, ratio)
    remaining_fraction = (
        None if consumption_ratio is None else Fraction(1) - consumption_ratio
    )
    return ErrorBudget(
        slo=slo,
        ratio=ratio,
        status=status,
        allowed_bad_fraction=allowed_bad_fraction,
        allowed_bad_events=allowed_bad_fraction * ratio.considered_count,
        observed_bad_events=ratio.considered_fail_count,
        consumption_ratio=consumption_ratio,
        remaining_fraction=remaining_fraction,
    )


@dataclass(frozen=True)
class BurnRate:
    """How fast a budget is being consumed over one (typically short)
    lookback window, relative to the rate that would exactly exhaust it
    over the SLO's full observation window.

    ``value`` of ``1`` means consuming budget at exactly the sustainable
    rate; ``> 1`` means faster than sustainable. ``None`` iff ``status``
    is ``NO_DATA`` or ``ZERO_TOLERANCE_EXCEEDED`` — see module docstring.

    ``ratio`` represents whatever lookback period the caller chose; this
    function has no notion of window length or time itself (see
    docs/SLO_SEMANTICS.md — multi-window/time-aware alerting is deferred).
    """

    slo: Slo
    ratio: RatioResult
    status: BudgetStatus
    value: Fraction | None


def compute_burn_rate(slo: Slo, ratio: RatioResult) -> BurnRate:
    """Compute the burn rate implied by ``slo`` over ``ratio``'s (lookback)
    window."""
    status, value = _consumption(slo.allowed_bad_fraction, ratio)
    return BurnRate(slo=slo, ratio=ratio, status=status, value=value)

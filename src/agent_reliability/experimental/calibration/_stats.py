"""Deterministic statistics for calibration (stdlib only).

Every ratio is a :class:`Proportion` (numerator, denominator, two exact-or-score
intervals) or an :class:`Undefined` marker with a reason. Nothing divides by zero
silently, returns NaN, or substitutes 0/1 for "not computable".
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from typing import Any, Final

__all__ = [
    "CONFIDENCE",
    "Proportion",
    "Undefined",
    "clopper_pearson",
    "cohen_kappa",
    "f1",
    "mean",
    "wilson",
]

#: Two-sided confidence of every interval in this package.
CONFIDENCE: Final = 0.95
_Z: Final = 1.959963984540054  # two-sided 95% normal quantile
_ALPHA: Final = 1.0 - CONFIDENCE
_REASONS: Final = frozenset({"zero_denominator", "single_class", "no_judgments"})


@dataclass(frozen=True, slots=True)
class Undefined:
    """A statistic that cannot be computed, with the reason it cannot."""

    reason: str

    def __post_init__(self) -> None:
        if self.reason not in _REASONS:
            raise ValueError("unknown undefined reason")

    def as_json(self) -> dict[str, Any]:
        return {"value": None, "undefined_reason": self.reason}


def _round(value: float) -> float:
    return round(value, 6)


def wilson(successes: int, total: int) -> tuple[float, float] | None:
    """95% Wilson score interval (display convention shared with the judge harness)."""
    if total <= 0:
        return None
    p = successes / total
    z2 = _Z * _Z
    denominator = 1 + z2 / total
    centre = (p + z2 / (2 * total)) / denominator
    half = _Z * math.sqrt(p * (1 - p) / total + z2 / (4 * total * total)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


# -- regularized incomplete beta (Numerical Recipes continued fraction) ----------


def _betacf(a: float, b: float, x: float) -> float:
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    d = tiny if abs(d) < tiny else d
    d = 1.0 / d
    h = d
    for m in range(1, 1000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = tiny if abs(d) < tiny else d
        c = 1.0 + aa / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = tiny if abs(d) < tiny else d
        c = 1.0 + aa / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_front = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    front = math.exp(log_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _beta_quantile(q: float, a: float, b: float) -> float:
    """x with I_x(a, b) = q, by bisection (monotone, deterministic)."""
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _betai(a, b, mid) < q:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-16:
            break
    return (lo + hi) / 2.0


def clopper_pearson(successes: int, total: int) -> tuple[float, float] | None:
    """Exact (Clopper-Pearson) two-sided 95% interval, or ``None`` for ``total == 0``.

    Conservative by construction (coverage at least nominal); used by policy
    decisions. Assumes independent trials.
    """
    if total <= 0:
        return None
    if not 0 <= successes <= total:
        raise ValueError("successes must be within 0..total")
    half = _ALPHA / 2.0
    lower = (
        0.0
        if successes == 0
        else _beta_quantile(half, float(successes), float(total - successes + 1))
    )
    upper = (
        1.0
        if successes == total
        else _beta_quantile(1.0 - half, float(successes + 1), float(total - successes))
    )
    return lower, upper


@dataclass(frozen=True, slots=True)
class Proportion:
    """``numerator / denominator`` with both intervals; never silently defined."""

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if (
            type(self.numerator) is not int
            or type(self.denominator) is not int
            or self.denominator < 0
            or not 0 <= self.numerator <= max(self.denominator, 0)
        ):
            raise ValueError("a proportion needs 0 <= numerator <= denominator")

    @property
    def value(self) -> float | Undefined:
        if self.denominator == 0:
            return Undefined("zero_denominator")
        return self.numerator / self.denominator

    @property
    def wilson(self) -> tuple[float, float] | None:
        return wilson(self.numerator, self.denominator)

    @property
    def exact(self) -> tuple[float, float] | None:
        return clopper_pearson(self.numerator, self.denominator)

    def as_json(self) -> dict[str, Any]:
        value = self.value
        wilson_interval = self.wilson
        exact_interval = self.exact
        document: dict[str, Any] = {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "value": None if isinstance(value, Undefined) else _round(value),
            "wilson_95": None
            if wilson_interval is None
            else [_round(wilson_interval[0]), _round(wilson_interval[1])],
            "clopper_pearson_95": None
            if exact_interval is None
            else [_round(exact_interval[0]), _round(exact_interval[1])],
        }
        if isinstance(value, Undefined):
            document["undefined_reason"] = value.reason
        return document


def f1(
    true_positive: int, false_positive: int, false_negative: int
) -> float | Undefined:
    """``2TP / (2TP + FP + FN)``; 0 when TP is 0 with errors, undefined only at 0/0."""
    denominator = 2 * true_positive + false_positive + false_negative
    if denominator == 0:
        return Undefined("zero_denominator")
    return 2 * true_positive / denominator


def cohen_kappa(
    pairs: Sequence[tuple[Hashable, Hashable]], categories: Sequence[Hashable]
) -> float | Undefined:
    """Cohen's kappa over an explicit category set; undefined when not computable."""
    n = len(pairs)
    if n == 0:
        return Undefined("no_judgments")
    observed = sum(1 for a, b in pairs if a == b) / n
    expected = sum(
        (sum(1 for a, _ in pairs if a == label) / n)
        * (sum(1 for _, b in pairs if b == label) / n)
        for label in categories
    )
    if expected >= 1.0:
        return Undefined("single_class")
    return (observed - expected) / (1.0 - expected)


def mean(values: Sequence[float]) -> float | Undefined:
    if not values:
        return Undefined("zero_denominator")
    return math.fsum(values) / len(values)

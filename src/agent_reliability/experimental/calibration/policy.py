"""Calibration policy: the caller's thresholds, stated explicitly.

Every field is required: the library has no implicit threshold (owner decision
P29-D10 is that thresholds belong to the customer). :meth:`CalibrationPolicy.
starting_point` is an explicit, caller-invoked preset adapted from the proposals of
``docs/P28_P29_CALIBRATION_PREPARATION.md`` section 10; it makes no safety claim.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, fields
from typing import Any, Final

from agent_reliability.experimental.calibration._json import canonical
from agent_reliability.experimental.calibration._stats import clopper_pearson
from agent_reliability.experimental.calibration.dataset import LabelProvenance

__all__ = ["CalibrationPolicy", "PolicyError"]

_BASES: Final = ("conditional", "effective")
_HUMAN: Final = frozenset(
    {
        LabelProvenance.HUMAN_SINGLE,
        LabelProvenance.HUMAN_MULTI,
        LabelProvenance.HUMAN_ADJUDICATED,
    }
)
_POSITIVE_INTS: Final = (
    "min_examples",
    "min_per_class",
    "min_adversarial_fail",
    "min_repeat_cases",
    "validity_days",
    "max_dataset_age_days",
)
_RATE_CAPS: Final = (
    "max_abstention_rate",
    "max_failure_rate",
    "max_missing_rate",
    "max_fnr",
    "max_fpr",
    "max_unstable_rate",
    "max_indeterminate_fraction",
)


class PolicyError(ValueError):
    """The policy is invalid or cannot be satisfied by its own size minima."""


MAX_SIZE = 10**9
MAX_DAYS = 36_500  # one hundred years: far inside timedelta's range


def _is_number(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:  # an integer too large for a float
        return False


def _upper_at_zero(n: int) -> float:
    interval = clopper_pearson(0, n)
    assert interval is not None
    return interval[1]


def _lower_at_all(n: int) -> float:
    interval = clopper_pearson(n, n)
    assert interval is not None
    return interval[0]


@dataclass(frozen=True, slots=True)
class CalibrationPolicy:
    """All fields are required. Rate criteria compare exact (Clopper-Pearson) bounds
    on unrounded counts; see ARCHITECTURE section 6 for the three-way test."""

    min_examples: int
    min_per_class: int
    min_adversarial_fail: int
    min_committed_coverage: float
    max_abstention_rate: float
    max_failure_rate: float
    max_missing_rate: float
    max_fnr: float
    fn_basis: str
    max_fpr: float
    fp_basis: str
    max_adversarial_pass_on_fail: int
    max_unstable_rate: float
    min_repeat_cases: int
    max_indeterminate_fraction: float
    min_inter_labeler_agreement: float | None
    accepted_label_provenance: frozenset[LabelProvenance]
    require_verified_integrity: bool
    validity_days: int
    max_dataset_age_days: int
    demonstration_only: bool

    def __post_init__(self) -> None:
        for name in _POSITIVE_INTS:
            value = getattr(self, name)
            limit = MAX_DAYS if name.endswith("_days") else MAX_SIZE
            if type(value) is not int or not 1 <= value <= limit:
                raise PolicyError(f"{name} must be an int in 1..{limit}")
        if (
            type(self.max_adversarial_pass_on_fail) is not int
            or not 0 <= self.max_adversarial_pass_on_fail <= MAX_SIZE
        ):
            raise PolicyError("max_adversarial_pass_on_fail must be an int >= 0")
        for name in _RATE_CAPS:
            value = getattr(self, name)
            if not _is_number(value) or not math.isfinite(value) or not 0 < value <= 1:
                raise PolicyError(f"{name} must be a number in (0, 1]")
        if not _is_number(self.min_committed_coverage) or not (
            0 < self.min_committed_coverage < 1
        ):
            raise PolicyError("min_committed_coverage must be a number in (0, 1)")
        agreement = self.min_inter_labeler_agreement
        if agreement is not None and (
            not _is_number(agreement) or not 0 < agreement <= 1
        ):
            raise PolicyError("min_inter_labeler_agreement must be None or in (0, 1]")
        for name in ("fn_basis", "fp_basis"):
            if getattr(self, name) not in _BASES:
                raise PolicyError(f"{name} must be 'conditional' or 'effective'")
        accepted = self.accepted_label_provenance
        if (
            not isinstance(accepted, frozenset)
            or not accepted
            or not all(isinstance(p, LabelProvenance) for p in accepted)
        ):
            raise PolicyError("accepted_label_provenance must be a non-empty frozenset")
        if type(self.require_verified_integrity) is not bool:
            raise PolicyError("require_verified_integrity must be a bool")
        if type(self.demonstration_only) is not bool:
            raise PolicyError("demonstration_only must be a bool")
        # Synthetic data, demonstration and calibrated are tied together.
        if LabelProvenance.SYNTHETIC in accepted and not self.demonstration_only:
            raise PolicyError(
                "synthetic labels are accepted only by a demonstration_only policy"
            )
        if not self.demonstration_only and not self.require_verified_integrity:
            raise PolicyError(
                "a calibrating policy must require verified integrity: an unsigned "
                "record can be forged by anyone who can write the file"
            )
        if not self.demonstration_only and not accepted <= _HUMAN:
            raise PolicyError("a calibrating policy accepts human provenance only")
        self._check_coherence()

    def _check_coherence(self) -> None:
        """Reject size minima that cannot satisfy their own bound with zero errors."""
        coverage_n = math.ceil(self.min_examples * self.min_committed_coverage)
        checks = (
            ("max_fnr", self.max_fnr, self.min_per_class, "min_per_class"),
            ("max_fpr", self.max_fpr, self.min_per_class, "min_per_class"),
            (
                "max_unstable_rate",
                self.max_unstable_rate,
                self.min_repeat_cases,
                "min_repeat_cases",
            ),
            (
                "max_failure_rate",
                self.max_failure_rate,
                self.min_examples,
                "min_examples",
            ),
            (
                "max_missing_rate",
                self.max_missing_rate,
                self.min_examples,
                "min_examples",
            ),
            (
                "max_abstention_rate",
                self.max_abstention_rate,
                coverage_n,
                "min_examples x min_committed_coverage",
            ),
        )
        for name, limit, n, size_name in checks:
            if _upper_at_zero(n) > limit:
                raise PolicyError(
                    f"{size_name} ({n}) cannot satisfy {name} ({limit}) "
                    "with zero errors"
                )
        if _lower_at_all(self.min_examples) < self.min_committed_coverage:
            raise PolicyError(
                "min_examples cannot satisfy min_committed_coverage "
                "even at full coverage"
            )
        if self.min_per_class > self.min_examples:
            raise PolicyError("min_per_class cannot exceed min_examples")

    @classmethod
    def starting_point(cls) -> CalibrationPolicy:
        """An explicit preset: a starting point to review, never a safety claim.

        Adapted from ``P28_P29_CALIBRATION_PREPARATION.md`` section 10 and made
        sample-size-coherent (a 0.05 exact upper bound needs 72 error-free cases;
        150 allows two errors). Differences from that document are listed in
        docs/p29-calibration/ARCHITECTURE.md section 6.
        """
        return cls(
            min_examples=400,
            min_per_class=150,
            min_adversarial_fail=30,
            min_committed_coverage=0.80,
            max_abstention_rate=0.20,
            max_failure_rate=0.02,
            max_missing_rate=0.02,
            max_fnr=0.05,
            fn_basis="effective",
            max_fpr=0.10,
            fp_basis="conditional",
            max_adversarial_pass_on_fail=0,
            max_unstable_rate=0.05,
            min_repeat_cases=150,
            max_indeterminate_fraction=0.20,
            min_inter_labeler_agreement=0.80,
            accepted_label_provenance=frozenset(
                {LabelProvenance.HUMAN_MULTI, LabelProvenance.HUMAN_ADJUDICATED}
            ),
            require_verified_integrity=True,
            validity_days=90,
            max_dataset_age_days=365,
            demonstration_only=False,
        )

    def as_dict(self) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name == "accepted_label_provenance":
                value = sorted(p.value for p in value)
            document[field.name] = value
        return document

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical(self.as_dict()).encode("utf-8")).hexdigest()

    def below_starting_point(self) -> tuple[str, ...]:
        """Names of fields weaker than :meth:`starting_point` (informational)."""
        base = CalibrationPolicy.starting_point()
        weaker: list[str] = []
        for name in (
            *_RATE_CAPS,
            "max_adversarial_pass_on_fail",
            "validity_days",
            "max_dataset_age_days",
        ):
            if getattr(self, name) > getattr(base, name):
                weaker.append(name)
        for name in (
            "min_examples",
            "min_per_class",
            "min_adversarial_fail",
            "min_committed_coverage",
            "min_repeat_cases",
        ):
            if getattr(self, name) < getattr(base, name):
                weaker.append(name)
        if self.min_inter_labeler_agreement is None or (
            self.min_inter_labeler_agreement < (base.min_inter_labeler_agreement or 0)
        ):
            weaker.append("min_inter_labeler_agreement")
        for name in ("fn_basis", "fp_basis"):
            if getattr(self, name) != getattr(base, name):
                weaker.append(name)
        if not self.accepted_label_provenance <= base.accepted_label_provenance:
            weaker.append("accepted_label_provenance")
        if not self.require_verified_integrity:
            weaker.append("require_verified_integrity")
        if self.demonstration_only:
            weaker.append("demonstration_only")
        return tuple(weaker)

    def summary(self) -> dict[str, Any]:
        return {
            "policy": self.as_dict(),
            "policy_digest": self.digest,
            "below_starting_point": list(self.below_starting_point()),
        }

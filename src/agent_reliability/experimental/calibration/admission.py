"""Calibration status, evidence admission and the opt-in coordinator gate.

``assess_admission`` is a pure function: given an assessment, the *current*
fingerprint, a caller-supplied policy and the time, it returns a status and the
verdict of every criterion. It never changes outcome meaning, run health or any wire
member. :class:`CalibrationGate` plugs the same decision into the judge
coordinator's calibration-agnostic admission hook (docs/p29-calibration/
ARCHITECTURE.md section 8).
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from agent_reliability.experimental.calibration._stats import Proportion
from agent_reliability.experimental.calibration.assessment import CalibrationAssessment
from agent_reliability.experimental.calibration.dataset import LabelProvenance
from agent_reliability.experimental.calibration.fingerprint import (
    JudgeFingerprint,
    ModelDeclaration,
)
from agent_reliability.experimental.calibration.policy import CalibrationPolicy
from agent_reliability.experimental.judge import (
    AdmissionVerdict,
    LLMJudge,
    SyncLLMJudge,
)

__all__ = [
    "AdmissionDecision",
    "CalibrationGate",
    "CalibrationStatus",
    "Criterion",
    "assess_admission",
]

FUTURE_SKEW: Final = timedelta(seconds=60)


class CalibrationStatus(enum.StrEnum):
    CALIBRATED = "calibrated"
    UNCALIBRATED = "uncalibrated"
    INSUFFICIENT_REFERENCE_EVIDENCE = "insufficient_reference_evidence"
    CALIBRATION_EXPIRED = "calibration_expired"
    INCOMPATIBLE = "incompatible"
    DEMONSTRATION = "demonstration"


_SKIP_CODES: Final = {
    CalibrationStatus.UNCALIBRATED: "calibration_uncalibrated",
    CalibrationStatus.INSUFFICIENT_REFERENCE_EVIDENCE: "calibration_no_evidence",
    CalibrationStatus.CALIBRATION_EXPIRED: "calibration_expired",
    CalibrationStatus.INCOMPATIBLE: "calibration_incompatible",
    CalibrationStatus.DEMONSTRATION: "calibration_demonstration",
    CalibrationStatus.CALIBRATED: "calibration_calibrated",
}

MET: Final = "met"
VIOLATED: Final = "violated"
INCONCLUSIVE: Final = "inconclusive"


@dataclass(frozen=True, slots=True)
class Criterion:
    """One checked criterion: its group, verdict and the numbers behind it."""

    name: str
    group: str  # structure | version | data | rate | time
    verdict: str  # met | violated | inconclusive
    detail: tuple[tuple[str, Any], ...] = field(default=())

    def as_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.name,
            "group": self.group,
            "verdict": self.verdict,
            "detail": dict(self.detail),
        }


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    """Content-free decision. ``admissible`` is true only for ``calibrated``."""

    status: CalibrationStatus
    criteria: tuple[Criterion, ...]
    policy_summary: dict[str, Any]
    integrity: str  # verified | unverified | mismatch | absent
    assessment_digest: str | None
    model: dict[str, Any] | None
    decided_at: datetime

    @property
    def admissible(self) -> bool:
        return self.status is CalibrationStatus.CALIBRATED

    @property
    def reason_code(self) -> str:
        return _SKIP_CODES[self.status]

    def failing(self) -> tuple[Criterion, ...]:
        return tuple(c for c in self.criteria if c.verdict != MET)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "admissible": self.admissible,
            "integrity": self.integrity,
            "assessment_digest": self.assessment_digest,
            "model_declaration": self.model,
            "decided_at": self.decided_at.isoformat(),
            "attested_provenance": True,
            "criteria": [c.as_dict() for c in self.criteria],
            "policy": self.policy_summary,
        }

    def explain(self) -> str:
        """Content-free text for an application dashboard."""
        lines = [
            f"status={self.status.value} admissible={self.admissible} "
            f"integrity={self.integrity}",
            "claim: meets the caller's stated policy on the named held-out dataset "
            "for this exact behaviour digest and model declaration at that time; "
            "label provenance is an attestation; not a statement about production "
            "accuracy",
        ]
        below = self.policy_summary.get("below_starting_point") or []
        if below:
            lines.append(
                "policy weaker than the starting point on: " + ", ".join(below)
            )
        for c in self.failing():
            lines.append(f"- {c.group}/{c.name}: {c.verdict}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"AdmissionDecision(status={self.status.value}, "
            f"admissible={self.admissible})"
        )


# ---------------------------------------------------------------- criteria


def _prop(document: dict[str, Any]) -> Proportion:
    return Proportion(int(document["numerator"]), int(document["denominator"]))


def _detail(prop: Proportion, limit: float) -> tuple[tuple[str, Any], ...]:
    interval = prop.exact
    return (
        ("numerator", prop.numerator),
        ("denominator", prop.denominator),
        ("limit", limit),
        ("clopper_pearson_lower", None if interval is None else round(interval[0], 6)),
        ("clopper_pearson_upper", None if interval is None else round(interval[1], 6)),
    )


def _upper(name: str, prop: Proportion, limit: float) -> Criterion:
    """Rate must be <= limit: met if the exact upper bound is, violated if even the
    exact lower bound is above it, otherwise inconclusive (not provably good)."""
    interval = prop.exact
    if interval is None:
        verdict = INCONCLUSIVE
    elif interval[1] <= limit:
        verdict = MET
    elif interval[0] > limit:
        verdict = VIOLATED
    else:
        verdict = INCONCLUSIVE
    return Criterion(name, "rate", verdict, _detail(prop, limit))


def _lower(name: str, prop: Proportion, minimum: float) -> Criterion:
    interval = prop.exact
    if interval is None:
        verdict = INCONCLUSIVE
    elif interval[0] >= minimum:
        verdict = MET
    elif interval[1] < minimum:
        verdict = VIOLATED
    else:
        verdict = INCONCLUSIVE
    return Criterion(name, "rate", verdict, _detail(prop, minimum))


def _size(name: str, value: int, minimum: int, group: str = "data") -> Criterion:
    return Criterion(
        name,
        group,
        MET if value >= minimum else VIOLATED,
        (("value", value), ("minimum", minimum)),
    )


def _structure_and_version(
    assessment: CalibrationAssessment,
    current: JudgeFingerprint,
    policy: CalibrationPolicy,
    now: datetime,
    integrity: str,
) -> list[Criterion]:
    document = assessment.document
    assessed = assessment.fingerprint
    criteria: list[Criterion] = []
    criteria.append(
        Criterion(
            "integrity_digest",
            "structure",
            MET if integrity != "mismatch" else VIOLATED,
        )
    )
    if policy.require_verified_integrity:
        criteria.append(
            Criterion(
                "integrity_verified",
                "structure",
                MET if integrity == "verified" else VIOLATED,
                (("integrity", integrity),),
            )
        )
    criteria.append(
        Criterion(
            "heldout_split",
            "structure",
            MET if document["dataset"]["split"] == "heldout" else VIOLATED,
        )
    )
    created = assessment.created_at
    criteria.append(
        Criterion(
            "not_future_dated",
            "structure",
            MET if created <= now + FUTURE_SKEW else VIOLATED,
        )
    )
    differing = assessed.diff(current)
    behavioural = tuple(n for n in differing if n != "implementation_version")
    criteria.append(
        Criterion(
            "fingerprint_equivalent",
            "version",
            MET if not behavioural else VIOLATED,
            (("differing_components", list(behavioural)),),
        )
    )
    criteria.append(
        Criterion(
            "rubric_matches_dataset",
            "version",
            MET if document["dataset"]["rubric_matches_fingerprint"] else VIOLATED,
        )
    )
    return criteria


def _data_and_rates(
    assessment: CalibrationAssessment, policy: CalibrationPolicy
) -> list[Criterion]:
    document = assessment.document
    metrics = document["metrics"]
    headline = metrics["headline"]
    counts = headline["counts"]
    rates = headline["rates"]
    dataset = document["dataset"]
    criteria: list[Criterion] = []

    provenance = LabelProvenance(dataset["label_provenance"])
    criteria.append(
        Criterion(
            "label_provenance_accepted",
            "data",
            MET if provenance in policy.accepted_label_provenance else VIOLATED,
            (("provenance", provenance.value), ("attested", True)),
        )
    )
    criteria.append(
        Criterion(
            "leakage_checked_against_other_splits",
            "data",
            MET if dataset["leakage_checked_against"] else INCONCLUSIVE,
            (("checked_against", dataset["leakage_checked_against"]),),
        )
    )
    criteria.append(
        Criterion(
            "no_split_leakage",
            "data",
            MET if dataset["leakage_clean"] else VIOLATED,
            (
                ("checked_against", dataset["leakage_checked_against"]),
                ("detects", "exact and normalised duplicates only"),
            ),
        )
    )
    criteria.append(
        _size("labelled_examples", headline["n_labelled"], policy.min_examples)
    )
    criteria.append(_size("support_fail", counts["support_fail"], policy.min_per_class))
    criteria.append(_size("support_pass", counts["support_pass"], policy.min_per_class))
    adversarial = metrics["strata"]["adversarial"]["counts"]
    criteria.append(
        _size(
            "adversarial_fail_support",
            adversarial["support_fail"],
            policy.min_adversarial_fail,
        )
    )
    criteria.append(
        Criterion(
            "adversarial_defects_passed",
            "rate",
            MET
            if adversarial["fn"] <= policy.max_adversarial_pass_on_fail
            else VIOLATED,
            (
                ("value", adversarial["fn"]),
                ("maximum", policy.max_adversarial_pass_on_fail),
            ),
        )
    )
    indeterminate = _prop(headline["indeterminate"]["indeterminate_fraction"])
    fraction = _upper(
        "indeterminate_fraction", indeterminate, policy.max_indeterminate_fraction
    )
    criteria.append(Criterion(fraction.name, "data", fraction.verdict, fraction.detail))
    if policy.min_inter_labeler_agreement is not None:
        agreement = metrics["inter_labeler_agreement"]["mean_pairwise_agreement"][
            "value"
        ]
        criteria.append(
            Criterion(
                "inter_labeler_agreement",
                "data",
                INCONCLUSIVE
                if agreement is None
                else (
                    MET if agreement >= policy.min_inter_labeler_agreement else VIOLATED
                ),
                (("value", agreement), ("minimum", policy.min_inter_labeler_agreement)),
            )
        )
    repeat = document["repeatability"]
    repeat_n = int(repeat["cases_compared"]) + int(repeat["excluded_for_failures"])
    criteria.append(_size("repeat_cases", repeat_n, policy.min_repeat_cases))
    criteria.append(
        Criterion(
            "repeatability_measured_on_all_cases",
            "data",
            MET if repeat["single_run_cases"] == 0 else VIOLATED,
            (("single_run_cases", repeat["single_run_cases"]),),
        )
    )

    criteria.append(
        _lower(
            "committed_coverage",
            _prop(rates["committed_coverage"]),
            policy.min_committed_coverage,
        )
    )
    criteria.append(
        _upper(
            "abstention_rate",
            _prop(rates["abstention_rate"]),
            policy.max_abstention_rate,
        )
    )
    criteria.append(
        _upper("failure_rate", _prop(rates["failure_rate"]), policy.max_failure_rate)
    )
    criteria.append(
        _upper("missing_rate", _prop(rates["missing_rate"]), policy.max_missing_rate)
    )
    criteria.append(
        _upper(
            f"fnr_{policy.fn_basis}",
            _prop(rates[f"fnr_{policy.fn_basis}"]),
            policy.max_fnr,
        )
    )
    criteria.append(
        _upper(
            f"fpr_{policy.fp_basis}",
            _prop(rates[f"fpr_{policy.fp_basis}"]),
            policy.max_fpr,
        )
    )
    criteria.append(
        _upper(
            "unstable_rate_worst_case",
            _prop(repeat["unstable_rate_worst_case"]),
            policy.max_unstable_rate,
        )
    )
    return criteria


def _time(
    assessment: CalibrationAssessment, policy: CalibrationPolicy, now: datetime
) -> list[Criterion]:
    age = now - assessment.created_at
    dataset_age = now - assessment.dataset_created_at
    future_dataset = assessment.dataset_created_at > now + FUTURE_SKEW
    return [
        Criterion(
            "calibration_valid",
            "time",
            MET if age <= timedelta(days=policy.validity_days) else VIOLATED,
            (
                ("age_days", round(age.total_seconds() / 86400, 3)),
                ("validity_days", policy.validity_days),
            ),
        ),
        Criterion(
            "dataset_current",
            "time",
            MET
            if not future_dataset
            and dataset_age <= timedelta(days=policy.max_dataset_age_days)
            else VIOLATED,
            (
                ("age_days", round(dataset_age.total_seconds() / 86400, 3)),
                ("max_dataset_age_days", policy.max_dataset_age_days),
            ),
        ),
    ]


def _integrity(assessment: CalibrationAssessment | None, hmac_key: bytes | None) -> str:
    if assessment is None:
        return "absent"
    if not assessment.digest_matches:
        return "mismatch"
    if hmac_key is not None and assessment.verify(hmac_key):
        return "verified"
    return "unverified"


def _decide(
    assessment: CalibrationAssessment | None,
    current: JudgeFingerprint,
    policy: CalibrationPolicy,
    now: datetime,
    integrity: str,
) -> AdmissionDecision:
    summary = policy.summary()
    if assessment is None:
        return AdmissionDecision(
            CalibrationStatus.UNCALIBRATED,
            (Criterion("assessment_present", "structure", VIOLATED),),
            summary,
            integrity,
            None,
            None,
            now,
        )
    structure = _structure_and_version(assessment, current, policy, now, integrity)
    digest = assessment.digest
    model = assessment.fingerprint.model.as_dict()
    if any(c.group == "structure" and c.verdict != MET for c in structure):
        # The record itself cannot be trusted: no metric is read from it.
        return AdmissionDecision(
            CalibrationStatus.UNCALIBRATED,
            tuple(structure),
            summary,
            integrity,
            digest,
            model,
            now,
        )
    measured = _data_and_rates(assessment, policy)
    timing = _time(assessment, policy, now)
    criteria = (*structure, *measured, *timing)

    def verdicts(group: str) -> set[str]:
        return {c.verdict for c in criteria if c.group == group}

    version_bad = VIOLATED in verdicts("version")
    rate_violated = any(c.group == "rate" and c.verdict == VIOLATED for c in criteria)
    insufficient = any(
        (c.group == "data" and c.verdict != MET)
        or (c.group == "rate" and c.verdict == INCONCLUSIVE)
        for c in criteria
    )
    expired = VIOLATED in verdicts("time")
    if rate_violated:
        status = CalibrationStatus.UNCALIBRATED
    elif version_bad:
        status = CalibrationStatus.INCOMPATIBLE
    elif insufficient:
        status = CalibrationStatus.INSUFFICIENT_REFERENCE_EVIDENCE
    elif expired:
        status = CalibrationStatus.CALIBRATION_EXPIRED
    elif policy.demonstration_only:
        status = CalibrationStatus.DEMONSTRATION
    else:
        status = CalibrationStatus.CALIBRATED
    return AdmissionDecision(status, criteria, summary, integrity, digest, model, now)


def assess_admission(
    assessment: CalibrationAssessment | None,
    current_fingerprint: JudgeFingerprint,
    policy: CalibrationPolicy,
    now: datetime,
    *,
    hmac_key: bytes | None = None,
) -> AdmissionDecision:
    """Decide whether this judge's evidence may feed reliability windows.

    Pure: the same inputs always give the same decision. ``now`` must be an aware
    datetime (injected, so tests and replays are deterministic).
    """
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("now must be a timezone-aware datetime")
    if not isinstance(policy, CalibrationPolicy):
        raise TypeError("policy must be a CalibrationPolicy")
    return _decide(
        assessment,
        current_fingerprint,
        policy,
        now.astimezone(UTC),
        _integrity(assessment, hmac_key),
    )


# ------------------------------------------------------------------- the gate


class CalibrationGate:
    """Implements the judge coordinator's ``EvidenceAdmission`` hook.

    The fingerprint is derived from the bound evaluator (never typed in); only the
    model declaration is the caller's. The decision is recomputed with the clock on
    every call, so an expiry takes effect when it happens. A gate is bound to one
    evaluator: ``IndicatorBinding`` rejects it for any other.
    """

    __slots__ = (
        "_assessment",
        "_clock",
        "_evaluator",
        "_fingerprint",
        "_integrity",
        "_model",
        "_policy",
    )

    def __init__(
        self,
        evaluator: LLMJudge | SyncLLMJudge,
        model: ModelDeclaration,
        assessment: CalibrationAssessment | None,
        policy: CalibrationPolicy,
        *,
        clock: Callable[[], datetime] | None = None,
        hmac_key: bytes | None = None,
    ) -> None:
        if not isinstance(policy, CalibrationPolicy):
            raise TypeError("policy must be a CalibrationPolicy")
        if policy.require_verified_integrity and hmac_key is None:
            raise ValueError(
                "this policy requires verified integrity: supply the HMAC key"
            )
        self._evaluator = evaluator
        self._model = model
        self._fingerprint = JudgeFingerprint.for_evaluator(evaluator, model)
        self._assessment = assessment
        self._policy = policy
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))
        # The assessment is immutable, so integrity is verified once.
        self._integrity = _integrity(assessment, hmac_key)

    @property
    def fingerprint(self) -> JudgeFingerprint:
        return self._fingerprint

    def bound_to(self, evaluator: Any) -> bool:
        if evaluator is not self._evaluator:
            return False
        try:
            current = JudgeFingerprint.for_evaluator(evaluator, self._model)
        except (TypeError, ValueError):
            return False
        return current.equivalent_to(self._fingerprint)

    def decision(self) -> AdmissionDecision:
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise ValueError("the gate clock must return an aware datetime")
        return _decide(
            self._assessment,
            self._fingerprint,
            self._policy,
            now.astimezone(UTC),
            self._integrity,
        )

    def decide(self, indicator: str, evaluator: Any) -> AdmissionVerdict:
        decision = self.decision()
        if decision.admissible:
            return AdmissionVerdict.allow()
        return AdmissionVerdict.skip(decision.reason_code)

    def __repr__(self) -> str:
        return f"CalibrationGate(model={self._model.model_id!r})"

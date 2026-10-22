"""EXPERIMENTAL: judge calibration and evidence admission (P29 Session 4).

Stdlib only. No network, no environment reads, no provider calls of its own: every
function works on local files and in-memory tables (``collect_judgments`` runs a
judge the caller supplies, with that judge's own provider, budgets and limits).
Names, signatures and defaults may change in a minor release with release notes
(docs/VERSIONING.md). See docs/p29-calibration/ for the architecture, statistical
definitions, threat model and owner decisions.

Calibration status describes one judge configuration against one held-out labelled
dataset under a *caller-supplied* policy. It is not a claim of accuracy in production.
"""

from __future__ import annotations

from agent_reliability.experimental.calibration._stats import (
    Proportion,
    Undefined,
    clopper_pearson,
)
from agent_reliability.experimental.calibration.admission import (
    AdmissionDecision,
    CalibrationGate,
    CalibrationStatus,
    Criterion,
    assess_admission,
)
from agent_reliability.experimental.calibration.analysis import (
    DISAGREEMENT_CATEGORIES,
    compare_judges,
    repeatability,
)
from agent_reliability.experimental.calibration.assessment import (
    AssessmentError,
    CalibrationAssessment,
    build_assessment,
)
from agent_reliability.experimental.calibration.dataset import (
    AdjudicationMethod,
    DatasetError,
    LabelProvenance,
    LeakageReport,
    ReferenceCase,
    ReferenceDataset,
    Split,
    load_reference_dataset,
)
from agent_reliability.experimental.calibration.drift import assess_drift
from agent_reliability.experimental.calibration.fingerprint import (
    JudgeFingerprint,
    ModelDeclaration,
)
from agent_reliability.experimental.calibration.judgments import (
    Judgment,
    JudgmentTable,
    Outcome,
    collect_judgments,
    collect_judgments_async,
)
from agent_reliability.experimental.calibration.metrics import split_metrics
from agent_reliability.experimental.calibration.policy import (
    CalibrationPolicy,
    PolicyError,
)

__all__ = [
    "DISAGREEMENT_CATEGORIES",
    "AdjudicationMethod",
    "AdmissionDecision",
    "AssessmentError",
    "CalibrationAssessment",
    "CalibrationGate",
    "CalibrationPolicy",
    "CalibrationStatus",
    "Criterion",
    "DatasetError",
    "JudgeFingerprint",
    "Judgment",
    "JudgmentTable",
    "LabelProvenance",
    "LeakageReport",
    "ModelDeclaration",
    "Outcome",
    "PolicyError",
    "Proportion",
    "ReferenceCase",
    "ReferenceDataset",
    "Split",
    "Undefined",
    "assess_admission",
    "assess_drift",
    "build_assessment",
    "clopper_pearson",
    "collect_judgments",
    "collect_judgments_async",
    "compare_judges",
    "load_reference_dataset",
    "repeatability",
    "split_metrics",
]

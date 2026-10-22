"""The calibration assessment: a content-free, integrity-checked measurement record.

An assessment states what one judge configuration did on the held-out split of one
labelled dataset at one time. It contains identifiers, counts, digests and bounded
enums only: no case text, no judge reasons, no raw output, no content digests.
Integrity is a plain SHA-256 (detects accident) plus an optional HMAC-SHA256 (the
only form that resists tampering by someone without the key).
"""

from __future__ import annotations

import copy
import hashlib
import hmac
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from agent_reliability.experimental.calibration._json import canonical, strict_loads
from agent_reliability.experimental.calibration._schemas import check
from agent_reliability.experimental.calibration.analysis import repeatability
from agent_reliability.experimental.calibration.dataset import (
    LabelProvenance,
    ReferenceDataset,
    Split,
)
from agent_reliability.experimental.calibration.fingerprint import JudgeFingerprint
from agent_reliability.experimental.calibration.judgments import JudgmentTable
from agent_reliability.experimental.calibration.metrics import split_metrics

__all__ = [
    "ASSESSMENT_SCHEMA",
    "AssessmentError",
    "CalibrationAssessment",
    "build_assessment",
]

ASSESSMENT_SCHEMA: Final = "gentlity.calibration-assessment/1"
_REQUIRED: Final = (
    "schema",
    "created_at",
    "fingerprint",
    "dataset",
    "metrics",
    "repeatability",
    "heldout_attempt",
    "integrity",
)
MAX_ASSESSMENT_BYTES: Final = 1024 * 1024


class AssessmentError(ValueError):
    """An assessment cannot be built or parsed. Messages never contain content."""


_HMAC_DOMAIN: Final = b"gentlity.calibration-assessment/1\x00hmac-sha256\x00"


def _body_bytes(document: Mapping[str, Any]) -> bytes:
    body = {k: v for k, v in document.items() if k != "integrity"}
    return canonical(body).encode("utf-8")


def _check_consistency(document: Mapping[str, Any]) -> None:
    """Arithmetic consistency that a schema cannot express (a hostile record could
    otherwise pass the schema yet contradict itself)."""

    def fail() -> AssessmentError:
        return AssessmentError("assessment is internally inconsistent")

    stack: list[Any] = [document]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if (
                "numerator" in node
                and "denominator" in node
                and not (0 <= node["numerator"] <= node["denominator"])
            ):
                raise fail()
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    metrics = document["metrics"]
    for block in (metrics["headline"], *metrics["strata"].values()):
        c = block["counts"]
        if (
            c["answered"] + c["abstained"] + c["failed"] + c["missing"]
            != block["n_labelled"]
            or c["tp"] + c["fn"] + c["fp"] + c["tn"] != c["answered"]
            or c["support_fail"] + c["support_pass"] != block["n_labelled"]
            or c["judged"] != c["answered"] + c["abstained"]
        ):
            raise fail()
    repeat = document["repeatability"]
    if repeat["unstable"] > repeat["cases_compared"]:
        raise fail()
    try:
        created = datetime.fromisoformat(document["created_at"])
        dataset_created = datetime.fromisoformat(document["dataset"]["created_at"])
    except ValueError:
        raise fail() from None
    if created.tzinfo is None or dataset_created.tzinfo is None:
        raise fail()
    if dataset_created > created + timedelta(seconds=60):
        raise fail()  # a dataset cannot be created after it was assessed


class CalibrationAssessment:
    """Immutable assessment document."""

    __slots__ = ("_document",)

    def __init__(self, document: Mapping[str, Any]) -> None:
        if not isinstance(document, Mapping):
            raise AssessmentError("an assessment must be an object")
        copied: dict[str, Any] = copy.deepcopy(dict(document))
        missing = [k for k in _REQUIRED if k not in copied]
        if missing or copied.get("schema") != ASSESSMENT_SCHEMA:
            raise AssessmentError("not a calibration assessment document")
        try:
            check(copied, "calibration-assessment")
        except ValueError:
            raise AssessmentError("assessment does not satisfy its schema") from None
        _check_consistency(copied)
        try:
            JudgeFingerprint.from_dict(copied["fingerprint"])
        except (ValueError, KeyError, TypeError):
            raise AssessmentError("assessment fingerprint is inconsistent") from None
        self._document = copied

    # -- access --------------------------------------------------------------

    @property
    def document(self) -> dict[str, Any]:
        return copy.deepcopy(self._document)

    @property
    def digest(self) -> str:
        """SHA-256 of the canonical document without its ``integrity`` member."""
        return hashlib.sha256(_body_bytes(self._document)).hexdigest()

    @property
    def digest_matches(self) -> bool:
        return hmac.compare_digest(self.digest, self._document["integrity"]["sha256"])

    @property
    def created_at(self) -> datetime:
        return datetime.fromisoformat(self._document["created_at"]).astimezone(UTC)

    @property
    def dataset_created_at(self) -> datetime:
        return datetime.fromisoformat(
            self._document["dataset"]["created_at"]
        ).astimezone(UTC)

    @property
    def split(self) -> str:
        return str(self._document["dataset"]["split"])

    @property
    def fingerprint(self) -> JudgeFingerprint:
        return JudgeFingerprint.from_dict(self._document["fingerprint"])

    def to_json(self, *, indent: int | None = 2) -> str:
        import json

        return json.dumps(self._document, indent=indent, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> CalibrationAssessment:
        if len(text.encode("utf-8")) > MAX_ASSESSMENT_BYTES:
            raise AssessmentError("assessment is too large")
        try:
            return cls(strict_loads(text))
        except ValueError as error:
            if isinstance(error, AssessmentError):
                raise
            raise AssessmentError("assessment is not valid strict JSON") from None

    # -- integrity -----------------------------------------------------------

    def sign(self, key: bytes) -> CalibrationAssessment:
        """Return a copy carrying an HMAC-SHA256 over the canonical body."""
        if not isinstance(key, bytes) or len(key) < 16:
            raise AssessmentError("an HMAC key must be at least 16 bytes")
        document = self.document
        document["integrity"] = {
            "sha256": self.digest,
            "hmac_sha256": hmac.new(
                key, _HMAC_DOMAIN + _body_bytes(document), hashlib.sha256
            ).hexdigest(),
        }
        return CalibrationAssessment(document)

    def verify(self, key: bytes) -> bool:
        """True only if the digest matches AND the HMAC verifies under ``key``."""
        stored = self._document["integrity"].get("hmac_sha256")
        if (
            not isinstance(key, bytes)
            or not isinstance(stored, str)
            or not self.digest_matches
        ):
            return False
        expected = hmac.new(
            key, _HMAC_DOMAIN + _body_bytes(self._document), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, stored)

    def __repr__(self) -> str:
        dataset = self._document["dataset"]
        return (
            f"CalibrationAssessment(dataset={dataset['dataset_id']!r}, "
            f"split={dataset['split']!r}, digest={self.digest[:12]})"
        )

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, CalibrationAssessment)
            and self._document == other._document
        )

    def __hash__(self) -> int:
        return hash(self.digest)


def build_assessment(
    dataset: ReferenceDataset,
    split: Split,
    table: JudgmentTable,
    *,
    now: datetime,
    heldout_attempt: int = 1,
) -> CalibrationAssessment:
    """Assess ``table`` against one split. Only the held-out split may be assessed.

    ``heldout_attempt`` is the caller's count of assessments tried against this
    held-out set (trying many configurations against one held-out set is an
    uncontrolled multiple-testing risk that the assessment makes visible).
    """
    if split is not Split.HELDOUT:
        raise AssessmentError(
            "only the held-out split may be assessed: train and calibration tune "
            "prompts, rubrics and thresholds and would inflate every metric"
        )
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise AssessmentError("now must be a timezone-aware datetime")
    if type(heldout_attempt) is not int or heldout_attempt < 1:
        raise AssessmentError("heldout_attempt must be an int >= 1")
    cases = dataset.cases(split)
    ids = {c.case_id for c in cases}
    if any(row.example_id not in ids for row in table.rows):
        raise AssessmentError("the judgment table names examples outside the split")
    fingerprint = table.fingerprint
    rubric_matches = (
        fingerprint.rubric_id == dataset.rubric_id
        and fingerprint.rubric_version == dataset.rubric_version
        and fingerprint.dimension == dataset.dimension.value
    )
    multi = sum(1 for c in cases if len(c.labels) >= 2)
    adjudicated = sum(
        1 for c in cases if c.provenance is LabelProvenance.HUMAN_ADJUDICATED
    )
    document: dict[str, Any] = {
        "schema": ASSESSMENT_SCHEMA,
        "created_at": now.astimezone(UTC).isoformat(),
        "fingerprint": fingerprint.as_dict(),
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "dataset_version": dataset.dataset_version,
            "manifest_sha256": dataset.manifest_sha256,
            "created_at": dataset.created_at.isoformat(),
            "split": split.value,
            "case_count": len(cases),
            "label_provenance": dataset.split_provenance[split].value,
            "attested": True,
            "provenance_counts": dataset.provenance_counts(split),
            "multi_labelled_cases": multi,
            "adjudicated_cases": adjudicated,
            "rubric": {
                "rubric_id": dataset.rubric_id,
                "rubric_version": dataset.rubric_version,
                "dimension": dataset.dimension.value,
            },
            "rubric_matches_fingerprint": rubric_matches,
            "leakage": dataset.leakage.as_dict(),
            "leakage_checked_against": sorted(
                s.value for s in dataset.splits if s is not split
            ),
            "leakage_clean": dataset.leakage.clean,
        },
        "metrics": split_metrics(cases, table, 0),
        "repeatability": repeatability(cases, table),
        "heldout_attempt": heldout_attempt,
    }
    document["integrity"] = {
        "sha256": hashlib.sha256(_body_bytes(document)).hexdigest()
    }
    return CalibrationAssessment(document)

"""Versioned reference datasets: manifest, splits, label rules, provenance, leakage.

Dataset files are untrusted input. Reading is bounded (bytes, lines, cases, nesting),
strict (duplicate members and NaN rejected), hash-pinned (the caller must pass the
expected manifest digest) and contained (split files live next to the manifest; no
path separators, no symlinks). Case text lives only in memory and in the dataset
files: no artefact derived from a dataset contains it, and leakage findings are
reported as counts and ``case_id`` values, never as content digests.
"""

from __future__ import annotations

import enum
import errno
import hashlib
import os
import re
import stat
import unicodedata
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from agent_reliability.experimental.calibration._json import canonical, strict_loads
from agent_reliability.experimental.calibration._schemas import check
from agent_reliability.experimental.judge import CalibrationCase, JudgeDimension

__all__ = [
    "AdjudicationMethod",
    "DatasetError",
    "LabelProvenance",
    "LeakageReport",
    "ReferenceCase",
    "ReferenceDataset",
    "Split",
    "load_reference_dataset",
]

MANIFEST_SCHEMA: Final = "gentlity.reference-dataset/1"
CASE_SCHEMA: Final = "gentlity.reference-case/1"
_CASE_V1: Final = "gentlity.calibration-case/1"

MAX_MANIFEST_BYTES: Final = 64 * 1024
MAX_SPLIT_BYTES: Final = 8 * 1024 * 1024
MAX_DATASET_BYTES: Final = 25 * 1024 * 1024
MAX_CASES_PER_SPLIT: Final = 20_000
MAX_LINE_BYTES: Final = 64 * 1024
_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_VERSION: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
_EXTRA_CASE_KEYS: Final = frozenset({"adjudication", "label_provenance"})
_MANIFEST_KEYS: Final = frozenset(
    {
        "schema",
        "dataset_id",
        "dataset_version",
        "created_at",
        "license",
        "description",
        "rubric",
        "splits",
    }
)


class DatasetError(ValueError):
    """A dataset or manifest is invalid. Messages never contain case content."""


class LabelProvenance(enum.StrEnum):
    SYNTHETIC = "synthetic"
    HUMAN_SINGLE = "human_single"
    HUMAN_MULTI = "human_multi"
    HUMAN_ADJUDICATED = "human_adjudicated"

    @property
    def rank(self) -> int:
        return _RANK[self]

    @property
    def is_human(self) -> bool:
        return self is not LabelProvenance.SYNTHETIC


_RANK: Final = {
    LabelProvenance.SYNTHETIC: 0,
    LabelProvenance.HUMAN_SINGLE: 1,
    LabelProvenance.HUMAN_MULTI: 2,
    LabelProvenance.HUMAN_ADJUDICATED: 3,
}


class Split(enum.StrEnum):
    TRAIN = "train"
    CALIBRATION = "calibration"
    HELDOUT = "heldout"


class AdjudicationMethod(enum.StrEnum):
    NONE = "none"
    MAJORITY = "majority"
    THIRD_REVIEWER = "third_reviewer"
    UNRESOLVED = "unresolved"


#: Characters that carry no visible content and are used to dodge exact matching:
#: format characters (zero-width space/joiner, soft hyphen, BOM) and punctuation.
_IGNORABLE = frozenset({"Cf", "Cc", "Mn"})


def _normalise(text: str) -> str:
    """Comparison form for near-duplicate detection (NOT a security boundary).

    NFKC + case folding, then drop format/control/combining characters and all
    punctuation, and collapse whitespace. Homoglyph substitution (for example a
    Cyrillic letter for a Latin one), paraphrase and translation are not detected.
    """
    folded = unicodedata.normalize("NFKC", text).casefold()
    kept = "".join(
        ch
        for ch in folded
        if unicodedata.category(ch) not in _IGNORABLE
        and not unicodedata.category(ch).startswith("P")
    )
    return " ".join(kept.split())


@dataclass(frozen=True, slots=True, repr=False)
class ReferenceCase:
    """A labelled example. Holds raw content: never rendered, never serialised."""

    case: CalibrationCase
    provenance: LabelProvenance
    adjudication: AdjudicationMethod
    content_key: str = field(repr=False)
    normalized_key: str = field(repr=False)

    @property
    def case_id(self) -> str:
        return self.case.case_id

    @property
    def human_label(self) -> str:
        return self.case.human_label

    @property
    def difficulty(self) -> str:
        return self.case.difficulty

    @property
    def labels(self) -> tuple[tuple[str, str], ...]:
        return self.case.labels

    @property
    def indeterminate(self) -> bool:
        """Ground truth is not established: people could not decide, or adjudication
        was left unresolved."""
        return (
            self.human_label == "unknown"
            or self.adjudication is AdjudicationMethod.UNRESOLVED
        )

    def __repr__(self) -> str:
        return f"ReferenceCase(case_id={self.case_id!r}, difficulty={self.difficulty})"


@dataclass(frozen=True, slots=True)
class LeakageReport:
    """Counts and ``case_id`` values only (content digests would be dictionary-
    reversible for short texts and are never exported)."""

    duplicate_case_ids: tuple[tuple[str, tuple[str, ...]], ...]
    identical_content: tuple[tuple[str, ...], ...]
    identical_normalized: tuple[tuple[str, ...], ...]
    cross_split: bool

    @property
    def clean(self) -> bool:
        return not (
            self.duplicate_case_ids
            or self.identical_content
            or self.identical_normalized
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "duplicate_case_ids": len(self.duplicate_case_ids),
            "identical_content_groups": len(self.identical_content),
            "identical_normalized_groups": len(self.identical_normalized),
            "cross_split": self.cross_split,
            "case_ids": sorted(
                {i for g in self.identical_content for i in g}
                | {i for g in self.identical_normalized for i in g}
                | {i for i, _ in self.duplicate_case_ids}
            ),
        }


@dataclass(frozen=True, slots=True)
class ReferenceDataset:
    dataset_id: str
    dataset_version: str
    created_at: datetime
    license: str
    rubric_id: str
    rubric_version: str
    dimension: JudgeDimension
    manifest_sha256: str
    splits: Mapping[Split, tuple[ReferenceCase, ...]]
    split_provenance: Mapping[Split, LabelProvenance]
    leakage: LeakageReport

    def cases(self, split: Split) -> tuple[ReferenceCase, ...]:
        if split not in self.splits:
            raise DatasetError("the dataset has no such split")
        return self.splits[split]

    def provenance_counts(self, split: Split) -> dict[str, int]:
        counts = dict.fromkeys((p.value for p in LabelProvenance), 0)
        for case in self.cases(split):
            counts[case.provenance.value] += 1
        return counts

    def __repr__(self) -> str:
        sizes = {s.value: len(c) for s, c in self.splits.items()}
        return (
            f"ReferenceDataset(id={self.dataset_id!r}, "
            f"version={self.dataset_version!r}, splits={sizes})"
        )


# ---------------------------------------------------------------- parsing


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DatasetError(message)


def _aware_utc(value: object, name: str) -> datetime:
    _require(isinstance(value, str), f"{name} must be an ISO 8601 string")
    assert isinstance(value, str)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise DatasetError(f"{name} is not an ISO 8601 timestamp") from None
    _require(parsed.tzinfo is not None, f"{name} must carry a UTC offset")
    return parsed.astimezone(UTC)


def _parse_case(
    document: Any, default_provenance: LabelProvenance, dimension: JudgeDimension
) -> ReferenceCase:
    _require(isinstance(document, dict), "a case must be a JSON object")
    _require(document.get("schema") == CASE_SCHEMA, "unexpected case schema")
    try:
        check(document, "reference-case")
    except ValueError:
        raise DatasetError("a case does not satisfy the case schema") from None
    base = {k: v for k, v in document.items() if k not in _EXTRA_CASE_KEYS}
    base["schema"] = _CASE_V1
    try:
        case = CalibrationCase.from_dict(base)
    except ValueError:
        raise DatasetError("a case does not satisfy the case schema") from None
    _require(case.dimension is dimension, "case dimension differs from the rubric")

    raw_prov = document.get("label_provenance")
    try:
        provenance = (
            default_provenance if raw_prov is None else LabelProvenance(raw_prov)
        )
    except ValueError:
        raise DatasetError("unknown label_provenance") from None
    raw_adj = document.get("adjudication", {"method": "none"})
    _require(
        isinstance(raw_adj, dict) and set(raw_adj) == {"method"},
        "adjudication must be {'method': ...}",
    )
    try:
        method = AdjudicationMethod(raw_adj["method"])
    except ValueError:
        raise DatasetError("unknown adjudication method") from None

    labels = case.labels
    names = [name for name, _ in labels]
    _require(len(set(names)) == len(names), "labeler ids must be unique within a case")
    n = len(labels)
    if provenance is LabelProvenance.SYNTHETIC:
        pass
    else:
        _require(n >= 1, "human-provenance cases need labeler entries")
        if provenance is not LabelProvenance.HUMAN_SINGLE:
            _require(n >= 2, "this provenance needs at least two labeler entries")
    if provenance is LabelProvenance.HUMAN_ADJUDICATED:
        _require(
            method is not AdjudicationMethod.NONE,
            "human_adjudicated cases need an adjudication method",
        )
    if n:
        distinct = {label for _, label in labels}
        if len(distinct) == 1 and method is not AdjudicationMethod.UNRESOLVED:
            _require(
                case.human_label == next(iter(distinct)),
                "human_label contradicts unanimous labels",
            )
        elif len(distinct) > 1:
            _require(
                method is not AdjudicationMethod.NONE,
                "labelers disagree: an adjudication method is required",
            )
        if method is AdjudicationMethod.MAJORITY:
            tally: dict[str, int] = defaultdict(int)
            for _, label in labels:
                tally[label] += 1
            top = max(tally.values())
            winners = [k for k, v in tally.items() if v == top]
            _require(
                len(winners) == 1 and case.human_label == winners[0],
                "human_label is not the strict majority label",
            )
    elif method is not AdjudicationMethod.NONE:
        raise DatasetError("adjudication requires labeler entries")
    if method is AdjudicationMethod.UNRESOLVED:
        _require(case.human_label == "unknown", "unresolved cases must be 'unknown'")
        _require(
            len({label for _, label in labels}) > 1,
            "unresolved adjudication needs disagreeing labels",
        )

    content = canonical([[p.role.value, p.text] for p in case.parts])
    # Parts are sorted so that reordering them does not evade detection.
    normalised = canonical(
        sorted([p.role.value, _normalise(p.text)] for p in case.parts)
    )
    return ReferenceCase(
        case=case,
        provenance=provenance,
        adjudication=method,
        content_key=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        normalized_key=hashlib.sha256(normalised.encode("utf-8")).hexdigest(),
    )


def _read_bounded(directory: Path, name: object, limit: int) -> bytes:
    _require(isinstance(name, str) and bool(name), "a file name is required")
    assert isinstance(name, str)
    _require(
        Path(name).name == name and name not in {".", ".."} and "\x00" not in name,
        "split files must be plain names beside the manifest",
    )
    path = directory / name
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise DatasetError("symlinks are refused") from None
        raise DatasetError("a dataset file cannot be read") from None
    try:
        info = os.fstat(fd)  # the descriptor we will read, not a path that may change
        _require(stat.S_ISREG(info.st_mode), "dataset files must be regular files")
        _require(info.st_size <= limit, "a dataset file exceeds its size cap")
        chunks: list[bytes] = []
        remaining = limit + 1  # read at most one byte past the cap, never more
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    except OSError:
        raise DatasetError("a dataset file cannot be read") from None
    finally:
        os.close(fd)
    data = b"".join(chunks)
    _require(len(data) <= limit, "a dataset file exceeds its size cap")
    return data


def _leakage(splits: Mapping[Split, tuple[ReferenceCase, ...]]) -> LeakageReport:
    by_id: dict[str, list[str]] = defaultdict(list)
    by_content: dict[str, list[tuple[str, str]]] = defaultdict(list)
    by_norm: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for split, cases in splits.items():
        for c in cases:
            by_id[c.case_id].append(split.value)
            by_content[c.content_key].append((split.value, c.case_id))
            by_norm[c.normalized_key].append((split.value, c.case_id))
    dup_ids = tuple(
        sorted((i, tuple(sorted(s))) for i, s in by_id.items() if len(s) > 1)
    )
    content_groups = [g for g in by_content.values() if len(g) > 1]
    norm_groups = [g for g in by_norm.values() if len(g) > 1]
    cross = any(
        len({s for s, _ in g}) > 1 for g in content_groups + norm_groups
    ) or any(len(set(s)) > 1 for _, s in dup_ids)
    return LeakageReport(
        duplicate_case_ids=dup_ids,
        identical_content=tuple(
            sorted(tuple(sorted(i for _, i in g)) for g in content_groups)
        ),
        identical_normalized=tuple(
            sorted(tuple(sorted(i for _, i in g)) for g in norm_groups)
        ),
        cross_split=cross,
    )


def load_reference_dataset(
    manifest_path: str | Path, *, expected_manifest_sha256: str
) -> ReferenceDataset:
    """Load and validate a dataset. ``expected_manifest_sha256`` is mandatory: the
    held-out data must be pinned before any judge is run against it."""
    _require(
        isinstance(expected_manifest_sha256, str)
        and _SHA256.fullmatch(expected_manifest_sha256) is not None,
        "expected_manifest_sha256 must be a lowercase sha-256 hex digest",
    )
    manifest_file = Path(manifest_path)
    directory = manifest_file.parent
    raw = _read_bounded(directory, manifest_file.name, MAX_MANIFEST_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    _require(
        digest == expected_manifest_sha256, "manifest digest does not match the pin"
    )
    try:
        manifest = strict_loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise DatasetError("manifest is not valid strict JSON") from None
    _require(isinstance(manifest, dict), "manifest must be an object")
    _require(set(manifest) <= _MANIFEST_KEYS, "manifest has unknown members")
    try:
        check(manifest, "reference-dataset")
    except ValueError:
        raise DatasetError("manifest does not satisfy the manifest schema") from None
    _require(manifest.get("schema") == MANIFEST_SCHEMA, "unexpected manifest schema")
    for key in (
        "dataset_id",
        "dataset_version",
        "created_at",
        "license",
        "rubric",
        "splits",
    ):
        _require(key in manifest, f"manifest is missing {key}")
    _require(
        isinstance(manifest["dataset_id"], str)
        and _ID.fullmatch(manifest["dataset_id"]) is not None,
        "dataset_id is invalid",
    )
    _require(
        isinstance(manifest["dataset_version"], str)
        and _VERSION.fullmatch(manifest["dataset_version"]) is not None,
        "dataset_version is invalid",
    )
    _require(
        isinstance(manifest["license"], str) and 1 <= len(manifest["license"]) <= 100,
        "license must be 1-100 characters",
    )
    created = _aware_utc(manifest["created_at"], "created_at")
    rubric = manifest["rubric"]
    _require(
        isinstance(rubric, dict)
        and set(rubric) == {"rubric_id", "rubric_version", "dimension"},
        "rubric needs rubric_id, rubric_version and dimension",
    )
    try:
        dimension = JudgeDimension(rubric["dimension"])
    except ValueError:
        raise DatasetError("unknown rubric dimension") from None
    _require(
        isinstance(rubric["rubric_id"], str)
        and isinstance(rubric["rubric_version"], str),
        "rubric ids must be strings",
    )
    split_docs = manifest["splits"]
    _require(
        isinstance(split_docs, dict) and 1 <= len(split_docs) <= 3,
        "splits must hold 1-3 entries",
    )

    loaded: dict[Split, tuple[ReferenceCase, ...]] = {}
    provenance: dict[Split, LabelProvenance] = {}
    total_bytes = len(raw)
    for name, entry in split_docs.items():
        try:
            split = Split(name)
        except ValueError:
            raise DatasetError("unknown split name") from None
        _require(
            isinstance(entry, dict)
            and set(entry) == {"file", "sha256", "case_count", "label_provenance"},
            "a split needs file, sha256, case_count and label_provenance",
        )
        try:
            declared = LabelProvenance(entry["label_provenance"])
        except ValueError:
            raise DatasetError("unknown split label_provenance") from None
        _require(
            isinstance(entry["sha256"], str)
            and _SHA256.fullmatch(entry["sha256"]) is not None,
            "split sha256 is invalid",
        )
        _require(
            type(entry["case_count"]) is int
            and 0 <= entry["case_count"] <= MAX_CASES_PER_SPLIT,
            "case_count is out of range",
        )
        data = _read_bounded(directory, entry["file"], MAX_SPLIT_BYTES)
        total_bytes += len(data)
        _require(
            total_bytes <= MAX_DATASET_BYTES, "the dataset exceeds its total size cap"
        )
        _require(
            hashlib.sha256(data).hexdigest() == entry["sha256"],
            "a split file does not match its digest",
        )
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise DatasetError("a split file is not UTF-8") from None
        cases: list[ReferenceCase] = []
        for line in text.split("\n"):
            if not line.strip():
                continue
            _require(
                len(line.encode("utf-8")) <= MAX_LINE_BYTES,
                "a case line exceeds its size cap",
            )
            _require(len(cases) < MAX_CASES_PER_SPLIT, "too many cases in a split")
            try:
                document = strict_loads(line)
            except ValueError:
                raise DatasetError("a case line is not valid strict JSON") from None
            cases.append(_parse_case(document, declared, dimension))
        _require(
            len(cases) == entry["case_count"], "case_count does not match the file"
        )
        ids = [c.case_id for c in cases]
        _require(
            len(set(ids)) == len(ids), "case_id values must be unique within a split"
        )
        derived = min(
            (c.provenance for c in cases), key=lambda p: p.rank, default=declared
        )
        _require(
            derived is declared,
            "declared label_provenance differs from the weakest case provenance",
        )
        loaded[split] = tuple(cases)
        provenance[split] = derived
    return ReferenceDataset(
        dataset_id=manifest["dataset_id"],
        dataset_version=manifest["dataset_version"],
        created_at=created,
        license=manifest["license"],
        rubric_id=rubric["rubric_id"],
        rubric_version=rubric["rubric_version"],
        dimension=dimension,
        manifest_sha256=digest,
        splits=loaded,
        split_provenance=provenance,
        leakage=_leakage(loaded),
    )

# ruff: noqa: E501 -- long assertion and data lines are kept readable.
"""Helpers for the Session 4 calibration tests (no network, no model)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_reliability.experimental.calibration import (
    CalibrationPolicy,
    JudgeFingerprint,
    Judgment,
    JudgmentTable,
    LabelProvenance,
    ModelDeclaration,
    Outcome,
    ReferenceDataset,
    Split,
    load_reference_dataset,
)
from agent_reliability.experimental.judge import SyncLLMJudge
from agent_reliability.experimental.judge.testing import FakeSyncProvider
from tests.fakes.p29_judge import named_rubrics

CANARY = "CANARY_P29_S4_DO_NOT_LEAK_91827"
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
CREATED = datetime(2026, 9, 1, tzinfo=UTC)
MODEL = ModelDeclaration("local", "llama-3-8b-q4", "2026-09")
RUBRIC = named_rubrics()["ac"]
KEY = b"0123456789abcdef0123456789abcdef"


def case_doc(
    case_id: str,
    label: str = "pass",
    *,
    difficulty: str = "clear",
    provenance: str | None = None,
    labels: Sequence[tuple[str, str]] | None = None,
    adjudication: str | None = None,
    text: str | None = None,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": "gentlity.reference-case/1",
        "case_id": case_id,
        "dimension": "answer-correctness",
        "parts": [
            {"role": "reference", "text": "The refund window is 30 days."},
            {"role": "answer", "text": text or f"[{case_id}] {CANARY} answer text."},
        ],
        "human_label": label,
        "difficulty": difficulty,
        "source": "synthetic",
    }
    if labels is not None:
        document["labels"] = [{"labeler": n, "label": v} for n, v in labels]
    if provenance is not None:
        document["label_provenance"] = provenance
    if adjudication is not None:
        document["adjudication"] = {"method": adjudication}
    return document


def write_dataset(
    directory: Path,
    splits: dict[str, list[dict[str, Any]]],
    *,
    provenance: dict[str, str] | None = None,
    dataset_id: str = "synthetic-ds",
    dataset_version: str = "1",
    created_at: datetime = CREATED,
    raw_lines: dict[str, list[str]] | None = None,
) -> tuple[Path, str]:
    """Write split files and a manifest; return ``(manifest_path, manifest_sha256)``."""
    directory.mkdir(parents=True, exist_ok=True)
    split_entries: dict[str, Any] = {}
    for name, docs in splits.items():
        lines = (raw_lines or {}).get(name) or [
            json.dumps(d, sort_keys=True) for d in docs
        ]
        data = ("\n".join(lines) + "\n").encode("utf-8")
        (directory / f"{name}.jsonl").write_bytes(data)
        split_entries[name] = {
            "file": f"{name}.jsonl",
            "sha256": hashlib.sha256(data).hexdigest(),
            "case_count": len(lines),
            "label_provenance": (provenance or {}).get(name, "synthetic"),
        }
    manifest = {
        "schema": "gentlity.reference-dataset/1",
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "created_at": created_at.isoformat(),
        "license": "CC0-1.0",
        "description": "synthetic test data",
        "rubric": {
            "rubric_id": RUBRIC.rubric_id,
            "rubric_version": RUBRIC.rubric_version,
            "dimension": "answer-correctness",
        },
        "splits": split_entries,
    }
    raw = json.dumps(manifest, sort_keys=True).encode("utf-8")
    path = directory / "manifest.json"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def load(
    directory: Path, splits: dict[str, list[dict[str, Any]]], **kw: Any
) -> ReferenceDataset:
    path, digest = write_dataset(directory, splits, **kw)
    return load_reference_dataset(path, expected_manifest_sha256=digest)


def make_judge(
    model_label: str = "local-a", replies: Sequence[str] = ()
) -> SyncLLMJudge:
    return SyncLLMJudge(
        rubric=RUBRIC,
        provider=FakeSyncProvider(list(replies)),
        model_label=model_label,
        jitter=lambda: 0.0,
    )


def fingerprint(
    model_label: str = "local-a", model: ModelDeclaration = MODEL
) -> JudgeFingerprint:
    return JudgeFingerprint.for_evaluator(make_judge(model_label), model)


def table(
    outcomes: dict[str, str | Sequence[str]],
    *,
    fp: JudgeFingerprint | None = None,
) -> JudgmentTable:
    """Build a table from ``{example_id: outcome | [outcome per run]}``.

    Outcome strings: PASS, FAIL, UNKNOWN, FAILURE (a provider failure), MISSING (omitted).
    """
    rows: list[Judgment] = []
    for example_id, value in outcomes.items():
        runs = [value] if isinstance(value, str) else list(value)
        for index, name in enumerate(runs):
            if name == "MISSING":
                continue
            if name == "FAILURE":
                rows.append(
                    Judgment(
                        example_id,
                        index,
                        Outcome.FAILURE,
                        "JudgeProviderUnavailableError",
                    )
                )
            else:
                rows.append(Judgment(example_id, index, Outcome(name), None, "high"))
    return JudgmentTable(fp or fingerprint(), tuple(rows))


def demo_policy(**overrides: Any) -> CalibrationPolicy:
    """A small, coherent, DEMONSTRATION-only policy for tests on small data."""
    values: dict[str, Any] = {
        "min_examples": 20,
        "min_per_class": 8,
        "min_adversarial_fail": 3,
        "min_committed_coverage": 0.5,
        "max_abstention_rate": 0.5,
        "max_failure_rate": 0.5,
        "max_missing_rate": 0.5,
        "max_fnr": 0.5,
        "fn_basis": "effective",
        "max_fpr": 0.5,
        "fp_basis": "conditional",
        "max_adversarial_pass_on_fail": 3,
        "max_unstable_rate": 0.5,
        "min_repeat_cases": 6,
        "max_indeterminate_fraction": 0.5,
        "min_inter_labeler_agreement": None,
        "accepted_label_provenance": frozenset({LabelProvenance.SYNTHETIC}),
        "require_verified_integrity": False,
        "validity_days": 90,
        "max_dataset_age_days": 365,
        "demonstration_only": True,
    }
    values.update(overrides)
    return CalibrationPolicy(**values)


def human_policy(**overrides: Any) -> CalibrationPolicy:
    """A small coherent policy that CAN reach ``calibrated`` (human provenance)."""
    values: dict[str, Any] = {
        "accepted_label_provenance": frozenset(
            {LabelProvenance.HUMAN_MULTI, LabelProvenance.HUMAN_ADJUDICATED}
        ),
        "demonstration_only": False,
        "require_verified_integrity": True,
    }
    values.update(overrides)
    return demo_policy(**values)


def heldout_cases(
    n_fail: int = 12,
    n_pass: int = 12,
    n_adv_fail: int = 4,
    *,
    provenance: str | None = None,
    multi: bool = False,
) -> list[dict[str, Any]]:
    """A deterministic held-out set: clear pass/fail plus an adversarial stratum."""
    cases: list[dict[str, Any]] = []
    labels_pass = [("rev-a", "pass"), ("rev-b", "pass")] if multi else None
    labels_fail = [("rev-a", "fail"), ("rev-b", "fail")] if multi else None
    for i in range(n_fail):
        cases.append(
            case_doc(f"f{i:02d}", "fail", provenance=provenance, labels=labels_fail)
        )
    for i in range(n_pass):
        cases.append(
            case_doc(f"p{i:02d}", "pass", provenance=provenance, labels=labels_pass)
        )
    for i in range(n_adv_fail):
        cases.append(
            case_doc(
                f"a{i:02d}",
                "fail",
                difficulty="adversarial",
                provenance=provenance,
                labels=labels_fail,
            )
        )
    return cases


def train_cases(
    n: int = 3, *, provenance: str | None = "human_multi"
) -> list[dict[str, Any]]:
    """A small train split whose content is distinct from every held-out case."""
    return [
        case_doc(
            f"tr{i:02d}",
            "pass" if i % 2 else "fail",
            provenance=provenance,
            labels=[
                ("rev-a", "pass" if i % 2 else "fail"),
                ("rev-b", "pass" if i % 2 else "fail"),
            ],
            text=f"unrelated training sample number {i}",
        )
        for i in range(n)
    ]


def perfect_outcomes(
    dataset: ReferenceDataset, split: Split = Split.HELDOUT
) -> dict[str, str]:
    return {
        c.case_id: ("FAIL" if c.human_label == "fail" else "PASS")
        for c in dataset.cases(split)
    }

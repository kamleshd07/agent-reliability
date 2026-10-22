# ruff: noqa: E501 -- the printed docstring and figures are kept readable.
"""Bounded local benchmark of the calibration package (a measurement, not a claim).

Builds a synthetic held-out split near the package's caps (8 MiB per split file, 20 000 cases), then times
load, metrics, repeatability, assessment, admission and the per-call gate decision.
Uses no network and no judge. Output is JSON.

    python scripts/p29_calibration_benchmark.py [--cases N] [--runs R]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import resource
import statistics
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_reliability.experimental.calibration import (
    CalibrationPolicy,
    JudgeFingerprint,
    Judgment,
    JudgmentTable,
    ModelDeclaration,
    Outcome,
    Split,
    assess_admission,
    build_assessment,
    load_reference_dataset,
    repeatability,
    split_metrics,
)
from agent_reliability.experimental.judge import SyncLLMJudge, load_reference_rubric
from agent_reliability.experimental.judge.testing import FakeSyncProvider

NOW = datetime(2026, 10, 22, tzinfo=UTC)


def timed(fn):  # type: ignore[no-untyped-def]
    start = time.perf_counter()
    result = fn()
    return result, round(time.perf_counter() - start, 4)


def write(directory: Path, count: int) -> tuple[Path, str]:
    lines = []
    for i in range(count):
        label = "fail" if i % 2 else "pass"
        lines.append(
            json.dumps(
                {
                    "schema": "gentlity.reference-case/1",
                    "case_id": f"c{i:06d}",
                    "dimension": "answer-correctness",
                    "parts": [
                        {"role": "reference", "text": "The refund window is 30 days."},
                        {"role": "answer", "text": f"[c{i:06d}] synthetic answer {i}."},
                    ],
                    "human_label": label,
                    "difficulty": "clear",
                    "labels": [
                        {"labeler": "synthetic-a", "label": label},
                        {"labeler": "synthetic-b", "label": label},
                    ],
                    "label_provenance": "human_multi",
                    "source": "synthetic",
                },
                sort_keys=True,
            )
        )
    data = ("\n".join(lines) + "\n").encode()
    (directory / "heldout.jsonl").write_bytes(data)
    manifest = {
        "schema": "gentlity.reference-dataset/1",
        "dataset_id": "benchmark",
        "dataset_version": "1",
        "created_at": "2026-10-01T00:00:00+00:00",
        "license": "CC0-1.0",
        "rubric": {
            "rubric_id": "judge-answer-correctness",
            "rubric_version": "2026-10.r1",
            "dimension": "answer-correctness",
        },
        "splits": {
            "heldout": {
                "file": "heldout.jsonl",
                "sha256": hashlib.sha256(data).hexdigest(),
                "case_count": count,
                "label_provenance": "human_multi",
            }
        },
    }
    raw = json.dumps(manifest, sort_keys=True).encode()
    path = directory / "manifest.json"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=12_000)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    figures: dict[str, object] = {
        "environment": f"{platform.platform()} python {platform.python_version()}; "
        "a measurement on one machine, NOT a capacity claim",
        "cases": args.cases,
        "runs_per_case": args.runs,
    }
    with tempfile.TemporaryDirectory() as directory:
        path, digest = write(Path(directory), args.cases)
        dataset, seconds = timed(
            lambda: load_reference_dataset(path, expected_manifest_sha256=digest)
        )
        figures["load_seconds"] = seconds
        figures["dataset_bytes"] = (Path(directory) / "heldout.jsonl").stat().st_size
    cases = dataset.cases(Split.HELDOUT)
    judge = SyncLLMJudge(
        rubric=load_reference_rubric("judge-answer-correctness"),
        provider=FakeSyncProvider([]),
        model_label="bench",
    )
    fingerprint = JudgeFingerprint.for_evaluator(
        judge, ModelDeclaration("local", "bench-model", "1")
    )
    rows = []
    for index, case in enumerate(cases):
        truth = Outcome.FAIL if case.human_label == "fail" else Outcome.PASS
        for run in range(args.runs):
            outcome = truth if (index + run) % 97 else Outcome.UNKNOWN
            rows.append(Judgment(case.case_id, run, outcome, None, "high"))
    table, seconds = timed(lambda: JudgmentTable(fingerprint, tuple(rows)))
    figures["table_build_seconds"] = seconds
    metrics, seconds = timed(lambda: split_metrics(cases, table))
    figures["split_metrics_seconds"] = seconds
    _, seconds = timed(lambda: repeatability(cases, table))
    figures["repeatability_seconds"] = seconds
    assessment, seconds = timed(
        lambda: build_assessment(
            dataset, Split.HELDOUT, table, now=NOW - timedelta(days=1)
        )
    )
    figures["build_assessment_seconds"] = seconds
    figures["assessment_bytes"] = len(assessment.to_json().encode())
    policy = CalibrationPolicy.starting_point()
    _, seconds = timed(lambda: assess_admission(assessment, fingerprint, policy, NOW))
    figures["assess_admission_seconds"] = seconds
    samples = []
    for _ in range(200):
        start = time.perf_counter()
        assess_admission(assessment, fingerprint, policy, NOW)
        samples.append(time.perf_counter() - start)
    figures["gate_decision_ms"] = {
        "median": round(statistics.median(samples) * 1000, 3),
        "p95": round(sorted(samples)[int(len(samples) * 0.95)] * 1000, 3),
    }
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    figures["peak_rss_mib"] = round(
        usage / (1024 * 1024 if sys.platform == "darwin" else 1024), 1
    )
    figures["headline_n"] = metrics["headline"]["n_labelled"]
    print(json.dumps(figures, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

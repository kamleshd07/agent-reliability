"""M4 evaluator engineering baselines, never marketing claims.

Run with:

    python benchmarks/bench_evaluation.py

The script uses only the standard library and reports medians across batches.
"""

from __future__ import annotations

import platform
import statistics
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_reliability.adapters import NoOpEventSink
from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation import (
    EqualityEvaluator,
    EvaluationProvenance,
    EvaluationResult,
    EvaluatorIdentity,
)
from agent_reliability.sdk import AgentReliability

BATCHES = 7
ITERATIONS_PER_BATCH = 20_000


def _measure(operation: Callable[[], None]) -> tuple[float, float]:
    samples: list[float] = []
    for _ in range(BATCHES):
        started = time.perf_counter()
        for _ in range(ITERATIONS_PER_BATCH):
            operation()
        elapsed = time.perf_counter() - started
        samples.append(elapsed / ITERATIONS_PER_BATCH * 1_000_000)
    return statistics.median(samples), statistics.stdev(samples)


def _report(label: str, operation: Callable[[], None]) -> None:
    median, stdev = _measure(operation)
    print(f"{label:38s} median={median:9.3f} us  stdev={stdev:8.3f} us")


def main() -> None:
    identity = EvaluatorIdentity("benchmark-equality", "1")
    evaluator = EqualityEvaluator(identity, 42)
    evaluated_at = datetime(2026, 1, 1, tzinfo=UTC)
    provenance = EvaluationProvenance(identity, evaluated_at, True)
    result = EvaluationResult(EvaluationOutcome.PASS, provenance, "equal")

    def evaluate() -> None:
        evaluator.evaluate(42)

    def create_result() -> None:
        EvaluationResult(
            EvaluationOutcome.PASS,
            EvaluationProvenance(identity, evaluated_at, True),
            "equal",
        )

    sdk = AgentReliability(sink=NoOpEventSink())
    print(f"Python: {platform.python_version()} ({platform.python_implementation()})")
    print(f"Platform: {platform.platform()}")
    print(f"Batches: {BATCHES}; iterations per batch: {ITERATIONS_PER_BATCH}")
    _report("EqualityEvaluator.evaluate", evaluate)
    _report("EvaluationResult + provenance", create_result)
    with sdk.run(agent_id="benchmark", name="Benchmark", version="1") as run:
        _report(
            "RunHandle.record_evaluation",
            lambda: run.record_evaluation(indicator="task_success", result=result),
        )


if __name__ == "__main__":
    main()

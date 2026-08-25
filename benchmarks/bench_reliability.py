"""Local M5 aggregation baselines; not a performance test or SLA."""

from __future__ import annotations

import gc
import statistics
import sys
import time
import tracemalloc
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agent_reliability.domain import (  # noqa: E402
    EvaluationOutcome,
    ObjectiveDirection,
    Slo,
    UnknownPolicy,
)
from agent_reliability.evaluation import (  # noqa: E402
    EvaluationProvenance,
    EvaluatorIdentity,
)
from agent_reliability.reliability import (  # noqa: E402
    ReliabilityObservation,
    ReliabilityReport,
    evaluate_reliability,
)

SIZES = (1_000, 10_000, 100_000, 1_000_000)
SLO = Slo("task-success", Fraction(99, 100), ObjectiveDirection.AT_LEAST)
PROVENANCE = EvaluationProvenance(
    EvaluatorIdentity("benchmark-check", "v1"),
    datetime(2026, 1, 1, tzinfo=UTC),
    True,
)
PASS = ReliabilityObservation("task_success", EvaluationOutcome.PASS, PROVENANCE)
FAIL = ReliabilityObservation("task_success", EvaluationOutcome.FAIL, PROVENANCE)


def _evaluate(observations: list[ReliabilityObservation]) -> None:
    result = evaluate_reliability(
        indicator="task_success",
        observations=observations,
        slo=SLO,
        unknown_policy=UnknownPolicy.EXCLUDE,
    )
    if not isinstance(result, ReliabilityReport):
        raise AssertionError("benchmark unexpectedly produced a conflict")
    if (
        result.ratio.pass_count + result.ratio.fail_count + result.ratio.unknown_count
        != len(observations)
    ):
        raise AssertionError("aggregation count mismatch")


def _measure_time(observations: list[ReliabilityObservation]) -> float:
    started = time.perf_counter()
    _evaluate(observations)
    return (time.perf_counter() - started) * 1_000


def _measure_peak(observations: list[ReliabilityObservation]) -> int:
    gc.collect()
    tracemalloc.start()
    _evaluate(observations)
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak_bytes


def main() -> None:
    print(
        "Python: "
        f"{sys.version_info.major}.{sys.version_info.minor}."
        f"{sys.version_info.micro}"
    )
    print(
        "Input memory is the shallow list container; peak is traced engine allocation."
    )
    for size in SIZES:
        observations = [PASS] * (size - 1) + [FAIL]
        elapsed = [_measure_time(observations) for _ in range(7)]
        peak = _measure_peak(observations)
        print(
            f"n={size:>9,}  median={statistics.median(elapsed):>10.3f} ms  "
            f"stdev={statistics.pstdev(elapsed):>8.3f} ms  "
            f"input_list={sys.getsizeof(observations) / 1024:>10.1f} KiB  "
            f"engine_peak={peak / 1024:>7.1f} KiB"
        )


if __name__ == "__main__":
    main()

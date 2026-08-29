"""M9 measurement-health stress baseline; not a performance SLA."""

from __future__ import annotations

import asyncio
import sys
import time
import tracemalloc
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agent_reliability.measurement import (  # noqa: E402
    MeasurementHealthReason,
    MeasurementHealthReport,
)
from agent_reliability.sdk import AgentReliability  # noqa: E402

COMPOSITIONS = 100_000
CONCURRENT_RUNS = 1_000


def composition_stress() -> None:
    degraded = MeasurementHealthReport.from_reasons(
        frozenset({MeasurementHealthReason.EVENT_DELIVERY_FAILURE})
    )
    unavailable = MeasurementHealthReport.from_reasons(
        frozenset({MeasurementHealthReason.EVALUATOR_EXECUTION_FAILURE})
    )
    report = MeasurementHealthReport()
    tracemalloc.start()
    started = time.perf_counter()
    for index in range(COMPOSITIONS):
        report = report.combine(degraded if index % 2 else unavailable)
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if len(report.reasons) != 2:
        raise AssertionError("reason state grew unexpectedly")
    print(
        f"composition n={COMPOSITIONS:,} elapsed={elapsed:.3f}s "
        f"bounded_reasons={len(report.reasons)} peak={peak / 1024:.1f}KiB"
    )


async def concurrency_stress() -> None:
    sdk = AgentReliability()

    async def execute(index: int) -> None:
        async with sdk.run(agent_id=str(index), name="Stress", version="1") as run:
            await asyncio.sleep(0)
            if run.run_id is None:
                raise AssertionError("unexpected degraded run")

    started = time.perf_counter()
    await asyncio.gather(*(execute(index) for index in range(CONCURRENT_RUNS)))
    print(
        f"concurrent_runs n={CONCURRENT_RUNS:,} "
        f"elapsed={time.perf_counter() - started:.3f}s"
    )


def main() -> None:
    composition_stress()
    asyncio.run(concurrency_stress())


if __name__ == "__main__":
    main()

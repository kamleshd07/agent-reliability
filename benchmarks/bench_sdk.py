"""M2 SDK runtime overhead — engineering baseline measurements, not
marketing claims.

Uses only the standard library (`time.perf_counter`), per
docs/ENGINEERING_PRINCIPLES.md #10 (no heavyweight benchmarking
dependency). Run with:

    py -3.11 benchmarks/bench_sdk.py

Each number is a median of several batches to reduce noise, printed
with the Python version and a note that these are local, single-machine
measurements — see the M2 report for the actual numbers recorded from
one such run and their interpretation.
"""

from __future__ import annotations

import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_reliability.adapters import (
    NoOpEventSink,
    SystemClock,
    UuidRunIdGenerator,
)
from agent_reliability.domain import EvaluationOutcome
from agent_reliability.sdk import AgentReliability

BATCHES = 7
ITERATIONS_PER_BATCH = 20_000


def _time_batches(fn: object, iterations: int, batches: int) -> list[float]:
    results = []
    for _ in range(batches):
        start = time.perf_counter()
        for _ in range(iterations):
            fn()  # type: ignore[operator]
        elapsed = time.perf_counter() - start
        results.append((elapsed / iterations) * 1_000_000)  # microseconds/call
    return results


def bench_run_enter_exit(sdk: AgentReliability) -> None:
    def one() -> None:
        with sdk.run(agent_id="bench-agent", name="Bench", version="1"):
            pass

    _report("run: enter + exit (no body work)", one)


def bench_run_with_one_record(sdk: AgentReliability) -> None:
    def one() -> None:
        with sdk.run(agent_id="bench-agent", name="Bench", version="1") as run:
            run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)

    _report("run: enter + one record() + exit", one)


def bench_nested_three_deep(sdk: AgentReliability) -> None:
    def one() -> None:
        with (
            sdk.run(agent_id="a", name="A", version="1"),
            sdk.run(agent_id="b", name="B", version="1"),
            sdk.run(agent_id="c", name="C", version="1"),
        ):
            pass

    _report("run: three-level nesting (enter+exit x3)", one)


def bench_event_construction() -> None:
    from datetime import UTC, datetime

    from agent_reliability.ports.events import RunStarted

    identity_kwargs = {
        "run_id": "r1",
        "parent_run_id": None,
        "started_at": datetime.now(UTC),
    }
    from agent_reliability.domain import AgentIdentity

    agent = AgentIdentity(agent_id="a", name="A", version="1")

    def one() -> None:
        RunStarted(agent=agent, **identity_kwargs)  # type: ignore[arg-type]

    _report("event construction: RunStarted", one)


def _report(label: str, fn: object) -> None:
    samples = _time_batches(fn, ITERATIONS_PER_BATCH, BATCHES)
    median = statistics.median(samples)
    stdev = statistics.stdev(samples) if len(samples) > 1 else 0.0
    print(
        f"{label:45s} median={median:8.3f} us/call  stdev={stdev:6.3f} us  "
        f"(n={BATCHES} batches x {ITERATIONS_PER_BATCH})"
    )


def main() -> None:
    print(f"Python {platform.python_version()} ({platform.python_implementation()})")
    print(f"Platform: {platform.platform()}")
    print("Sink: NoOpEventSink (isolates SDK overhead from sink implementation cost)")
    print()

    sdk = AgentReliability(
        sink=NoOpEventSink(), clock=SystemClock(), run_id_generator=UuidRunIdGenerator()
    )
    bench_run_enter_exit(sdk)
    bench_run_with_one_record(sdk)
    bench_nested_three_deep(sdk)
    bench_event_construction()


if __name__ == "__main__":
    main()

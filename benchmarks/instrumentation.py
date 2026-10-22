"""Bounded offline synthetic overhead study. No capacity or production claim.

python benchmarks/instrumentation.py --output results.json
Only this benchmark process disables third-party tracing; the library does not.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import platform
import statistics
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any


def samples(
    call: Callable[[], Any], iterations: int, repeats: int
) -> dict[str, float | int]:
    values = []
    for _ in range(3):
        call()  # warm imports/caches; excluded from measurement
    for _ in range(repeats):
        for _ in range(iterations):
            start = time.perf_counter_ns()
            call()
            values.append(time.perf_counter_ns() - start)
    ordered = sorted(values)
    return {
        "samples": len(values),
        "p50_us": statistics.median(values) / 1000,
        "p95_us": ordered[min(len(values) - 1, int(len(values) * 0.95))] / 1000,
        "p99_us": ordered[min(len(values) - 1, int(len(values) * 0.99))] / 1000,
    }


def peak(call: Callable[[], Any]) -> int:
    gc.collect()
    tracemalloc.start()
    try:
        call()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 5000 or not 1 <= args.repeats <= 20:
        parser.error("bounded iterations/repeats required")
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"

    import asyncio
    from importlib.metadata import version

    from langchain_core.runnables import RunnableLambda
    from langchain_core.tools import tool

    from agent_reliability.experimental.instrumentation import CaptureLimits, instrument
    from agent_reliability.sdk import AgentReliability

    @tool
    def synthetic_tool(value: str) -> str:
        """Constant synthetic result, no I/O."""
        return "ok"

    def wrap(runnable: Any) -> Any:
        return instrument(
            runnable,
            sdk=AgentReliability(),
            agent_id="benchmark",
            name="Benchmark",
            version="1",
            tool_names=("synthetic_tool",),
            limits=CaptureLimits(max_retained_runs=2),
        )

    trivial = RunnableLambda(lambda value: value)
    fast = wrap(trivial)
    frequent = RunnableLambda(
        lambda value: [synthetic_tool.invoke("synthetic") for _ in range(20)]
    )
    high = wrap(frequent)
    large = RunnableLambda(
        lambda value: [synthetic_tool.invoke("synthetic") for _ in range(1200)]
    )
    bounded = wrap(large)

    async def cooperative(value: int) -> int:
        await asyncio.sleep(0)
        return value

    async_base = RunnableLambda(cooperative)
    async_instrumented = wrap(async_base)

    async def batch(target: Any) -> None:
        await asyncio.gather(*(target.ainvoke(i) for i in range(16)))

    cases = [
        (
            "trivial_runnable",
            "one invocation",
            lambda: trivial.invoke("synthetic"),
            lambda: fast.invoke("synthetic"),
            args.iterations,
        ),
        (
            "twenty_tool_calls",
            "one invocation with20tool calls",
            lambda: frequent.invoke(None),
            lambda: high.invoke(None),
            min(args.iterations, 50),
        ),
        (
            "concurrent_async",
            "batch of16cooperative invocations including event-loop setup",
            lambda: asyncio.run(batch(async_base)),
            lambda: asyncio.run(batch(async_instrumented)),
            min(args.iterations, 20),
        ),
        (
            "large_truncated_trace",
            "one invocation with1200tool calls",
            lambda: large.invoke(None),
            lambda: bounded.invoke(None),
            1,
        ),
    ]
    results = []
    for name, unit, plain, measured, count in cases:
        baseline = samples(plain, count, args.repeats)
        instrumented = samples(measured, count, args.repeats)
        results.append(
            {
                "scenario": name,
                "unit": unit,
                "uninstrumented": baseline,
                "instrumented": instrumented,
                "p50_overhead_percent": (
                    instrumented["p50_us"] / baseline["p50_us"] - 1
                )
                * 100,
                "uninstrumented_peak_bytes_one_call": peak(plain),
                "instrumented_peak_bytes_one_call": peak(measured),
            }
        )
    trace = bounded.traces[-1]
    assert len(trace.events) <= 2002 and not trace.complete
    assert bounded.status.active_runs == 0 and len(bounded.traces) <= 2
    report = {
        "environment": {
            "python": platform.python_version(),
            "os": platform.platform(),
            "architecture": platform.machine(),
            "logical_cpus": os.cpu_count(),
            "langchain_core": version("langchain-core"),
        },
        "method": {
            "timer": "perf_counter_ns",
            "repeats": args.repeats,
            "trivial_iterations_per_repeat": args.iterations,
            "warmup_calls_per_measurement": 3,
            "retained_trace_limit": 2,
            "tracemalloc": (
                "peak incremental allocation of one call; imports warm; "
                "prior retained traces may exist"
            ),
            "no_network_or_paid_models": True,
        },
        "results": results,
        "large_trace": {
            "captured_events": len(trace.events),
            "tool_calls_captured": trace.tool_calls,
            "complete": trace.complete,
            "diagnostics": {
                "dropped": trace.diagnostics.dropped,
                "orphans": trace.diagnostics.orphans,
            },
        },
        "limitations": [
            "synthetic local warm-process microbenchmark",
            "no absolute callback deadline or capacity estimate",
            "sequential baseline then instrumented may be affected by system drift",
            "high percentage overhead on trivial work is not hidden",
            "peak allocation is not process RSS or a hard byte guarantee",
        ],
    }
    rendered = json.dumps(report, indent=2)
    if args.output is not None:
        args.output.write_text(rendered + "\n")
    else:
        print(rendered)


if __name__ == "__main__":
    main()

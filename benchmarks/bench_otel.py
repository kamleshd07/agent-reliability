"""M3 OpenTelemetry bridge engineering baselines, not marketing claims.

Requires ``agent-reliability[otel,otel-test]``. Compares the M2.1 no-op path,
an API-only non-recording tracer, and an in-memory SDK recording path.
"""

from __future__ import annotations

import importlib.metadata
import platform
import statistics
import time
from collections.abc import Callable

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from agent_reliability.adapters.otel import OpenTelemetryRunContextBridge
from agent_reliability.domain import EvaluationOutcome
from agent_reliability.sdk import AgentReliability

BATCHES = 7
ITERATIONS_PER_BATCH = 5_000


def _measure(
    operation: Callable[[], None], *, after_batch: Callable[[], None]
) -> tuple[float, float]:
    samples: list[float] = []
    for _ in range(BATCHES):
        started = time.perf_counter()
        for _ in range(ITERATIONS_PER_BATCH):
            operation()
        elapsed = time.perf_counter() - started
        samples.append(elapsed / ITERATIONS_PER_BATCH * 1_000_000)
        after_batch()
    return statistics.median(samples), statistics.stdev(samples)


def _operations(sdk: AgentReliability) -> dict[str, Callable[[], None]]:
    def enter_exit() -> None:
        with sdk.run(agent_id="bench-agent", name="Bench", version="1"):
            pass

    def one_record() -> None:
        with sdk.run(agent_id="bench-agent", name="Bench", version="1") as run:
            run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)

    def nested() -> None:
        with (
            sdk.run(agent_id="a", name="A", version="1"),
            sdk.run(agent_id="b", name="B", version="1"),
            sdk.run(agent_id="c", name="C", version="1"),
        ):
            pass

    return {"enter/exit": enter_exit, "one record": one_record, "nested x3": nested}


def main() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    cases = {
        "M2.1 no bridge": (AgentReliability(), lambda: None),
        "OTel API non-recording": (
            AgentReliability(
                run_context_bridge=OpenTelemetryRunContextBridge(
                    trace.NoOpTracerProvider().get_tracer("benchmark")
                )
            ),
            lambda: None,
        ),
        "OTel SDK in-memory": (
            AgentReliability(
                run_context_bridge=OpenTelemetryRunContextBridge(
                    provider.get_tracer("benchmark")
                )
            ),
            exporter.clear,
        ),
    }

    print(f"Python: {platform.python_version()} ({platform.python_implementation()})")
    print(f"Platform: {platform.platform()}")
    print(f"opentelemetry-api: {importlib.metadata.version('opentelemetry-api')}")
    print(f"opentelemetry-sdk: {importlib.metadata.version('opentelemetry-sdk')}")
    print(f"Batches: {BATCHES}; iterations per batch: {ITERATIONS_PER_BATCH}")
    for case, (sdk, after_batch) in cases.items():
        for operation, callable_ in _operations(sdk).items():
            median, stdev = _measure(callable_, after_batch=after_batch)
            print(
                f"{case:24s} {operation:12s} "
                f"median={median:9.3f} us  stdev={stdev:8.3f} us"
            )
    provider.shutdown()


if __name__ == "__main__":
    main()

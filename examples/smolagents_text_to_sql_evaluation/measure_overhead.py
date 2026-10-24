"""Measure what Gentlity adds to one replayed run (no model latency involved).

Language: Python. Both loops replay the same recorded model responses through the real
upstream agent; the second also wraps every case in ``sdk.run`` and records four
evaluations. Timing is machine dependent, so this script prints numbers and is not
part of the byte-for-byte reports.

    python measure_overhead.py [repeats]
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from smolagents_text_to_sql_evaluation import harness
    from smolagents_text_to_sql_evaluation.replay import ReplayModel
else:
    from . import harness
    from .replay import ReplayModel


def main(repeats: int = 10) -> None:
    data = harness.load_cases()
    transcript = harness.load_transcript(harness.DEFAULT_MODEL_TAG)
    model_id = transcript["meta"]["model_id"]
    plain: list[float] = []
    wrapped: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        for case in data["cases"]:
            model = ReplayModel(transcript["cases"][case["id"]]["steps"], model_id)
            harness.execute_case(harness.CaseRun(case), model, 0.0)
        plain.append(time.perf_counter() - started)
        started = time.perf_counter()
        harness.run_cases(data["cases"], data["tolerance"], mode="replay")
        wrapped.append(time.perf_counter() - started)
    count = len(data["cases"])
    per_plain = statistics.median(plain) / count * 1000
    per_wrapped = statistics.median(wrapped) / count * 1000
    print(f"cases per pass: {count}; passes: {repeats}")
    print(f"agent only      : {per_plain:.2f} ms per case (median)")
    print(f"agent + Gentlity: {per_wrapped:.2f} ms per case (median)")
    print(f"added by Gentlity: {per_wrapped - per_plain:.2f} ms per case")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)

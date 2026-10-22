# Performance and resource limits (bounded local measurement)

**A measurement on one development machine, not a capacity claim.** `python scripts/p29_calibration_benchmark.py` builds a synthetic held-out split,
then times each stage. No network, no judge.

## Measured (macOS arm64, Python 3.11, 12 000 cases x 3 runs = 36 000 judgments, 5.3 MB split file)

| Stage | Result |
|---|---|
| load + validate dataset (strict JSON, schema, provenance, leakage) | 0.77 s |
| build judgment table | 0.015 s |
| `split_metrics` (headline + 4 strata + labelers) | 0.046 s |
| `repeatability` | 0.013 s |
| `build_assessment` (metrics + repeatability + document) | 0.062 s |
| `assess_admission` / per-call gate decision | 0.8 ms median, 0.82 ms p95 |
| assessment document size | 38 KB (constant in the dataset size) |
| peak RSS of the whole process | about 70 MiB |

**A defect found by this measurement and fixed:** the first version looked judgments up by scanning all rows, so `split_metrics` took 5.8 s and
`repeatability` 2.8 s for the same input (quadratic). The table is now indexed (`test_scaling.py` guards it at 20 000 cases x 3 runs).

## Limits (code constants; changing one is a code change)

| Limit | Value |
|---|---|
| manifest / split file / dataset | 64 KiB / 8 MiB / 25 MiB |
| cases per split / line length / nesting depth | 20 000 / 64 KiB / 8 |
| repetitions per example | 1 to 10 |
| assessment document accepted by `from_json` | 1 MiB |
| gate decision | recomputed per evaluated call (about 0.8 ms); it runs outside the recording gate on the caller's thread or event loop |

The byte cap binds before the case cap for cases of roughly 420 bytes or more (20 000 cases of the benchmark's size is 10.6 MB and is refused).
Provider-backed runs are bounded by the judge's own `JudgeBudget`, `JudgeLimits` and `max_concurrency`; this package adds none and the offline path
makes no provider call.

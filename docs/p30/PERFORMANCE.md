# Local automatic-instrumentation overhead study

Synthetic offline warm-process measurements, not throughput/capacity or production latency. No provider,
paid model, service or external trace was used. Raw recorded values: [PERFORMANCE_DATA.json](PERFORMANCE_DATA.json).
Reproduce with `python benchmarks/instrumentation.py --output results.json` in the selected-extra environment.

Environment: Python 3.11.17, LangChain Core 1.6.13, macOS26.7.1/arm64,15 reported logical CPUs. Standard-library
perf_counter_ns timer;5 repeats;3 warm-up calls per measurement; default200 trivial iterations/repeat,50 for
20-tool scenario,20 async batches,1 large trace. Baseline then instrumented sequentially; no isolation from
other local processes, confidence intervals or calibrated production workload. No monetary costs measured.

| Scenario / timed unit | Samples per arm | Baseline p50 µs | Instrumented p50 µs | Absolute increase µs | p50 overhead |
|---|---:|---:|---:|---:|---:|
| trivial_runnable | 1000 | 25.209 | 65.875 | 40.666 | 161.32% |
| twenty_tool_calls | 250 | 935.605 | 1160.937 | 225.332 | 24.08% |
| concurrent_async | 100 | 824.417 | 1405.771 | 581.354 | 70.52% |
| large_truncated_trace | 5 | 50235.750 | 62071.750 | 11836.000 | 23.56% |

Units: trivial is one Runnable invoke;20-tool is one invoke containing20 tool calls; async is a batch of16
cooperative invocations **including event-loop setup**; large is one invoke containing1200 tool calls.
Percentage overhead on trivial work is high and is not described as negligible. The large scenario intentionally
exceeds the capture limit, so it measures the drop path too. Only five large samples were recorded; its reported
p95/p99 are empirical order statistics near the maximum, not tail-latency evidence. Raw p50/p95/p99 remain available.

## Resource observation and limits

Two completed traces retained per wrapper during this study (default is8). The large scenario captured2002
events and999 tools plus its framework step, then reported201 dropped starts and201 unmatched terminal callbacks.
Capture remained explicitly incomplete; retained memory did not grow with all1200 tool spans. This is not an
execution limit: the customer application still ran all1200 tools.

Tracemalloc peak **incremental one-call allocation** (warm imports, prior retained traces may exist), bytes:

| Scenario | Baseline peak | Instrumented peak |
|---|---:|---:|
| trivial_runnable | 9660 | 14438 |
| twenty_tool_calls | 41306 | 61376 |
| concurrent_async | 124875 | 195763 |
| large_truncated_trace | 160410 | 998415 |

These are Python allocator peaks, not RSS, tenant capacity or hard byte ceilings. Event fields, admitted runs,
retention, spans/depth and aliases are bounded; caller-held snapshots, existing SDK/custom sinks and framework
internals are outside this collector bound. Callback work does no I/O but has no hard scheduling/lock deadline.

## Interpretation

GO for owner review of an experimental opt-in slice; no performance-SLO or negligible-overhead claim. Compare
against real customer workloads before wider adoption, measure streams/graphs only when supported, and repeat
across CPU/OS/framework versions. Sampling and lower capture limits can reduce work but change coverage; partial
capture must never be presented as complete. Release and publication remain owner gates.

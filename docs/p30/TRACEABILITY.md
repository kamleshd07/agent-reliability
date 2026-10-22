# Session 3 initial-slice requirement-to-evidence map

| Requirement | Implementation | Tests / evidence |
|---|---|---|
| Explicit opt-in, one framework, no patch | instrument / InstrumentedRunnable, optional adapter | enable/disable/repeated-initialization tests, clean import/artifact probes |
| Automatic run start/complete/fail/duration/identity | existing SDK session + normalized root | sync, exception identity, cancellation, nested/context tests |
| Tools and parent links | scoped callback collector with approved aliases | real tool sync/async; nested wrappers; sequence/parent checks |
| Model metadata and unknown tokens | explicit chat/LLM hooks; validated TokenUsage | fake chat known/unknown, malformed/ambiguous/legacy usage tests |
| Actual framework steps | chain hooks only | real LCEL/Runnable retry and duplicate tests |
| No automatic semantic PASS | existing explicit evaluation API only | no EvaluationRecorded on completion; explicit UNKNOWN; provenance offline example |
| Retry vs operation distinction | one SDK run per wrapper call, UUID spans | real with_retry, duplicates, retry-signal regression |
| Concurrency and context | owner-context SDK session, per-invocation locks |16async calls,20thread calls; reviewer24/32shared-config and async nesting attacks |
| Cancellation / exceptions / partial lifecycle | same exception returned; synthetic incomplete closure | cancellation, failure-class privacy, missing ends, orphan/depth/cap tests |
| No raw content / metadata / exception names | closed facts, fixed root classification | sentinel response/prompt/tool/log tests; poison repr attacks; HTTP payload exclusion |
| Malformed lifecycle cannot become complete | kind/parent/duplicate identity checks | security S1 original+expanded attacks and committed regression |
| Bounded memory/events/admission | CaptureLimits, reserved terminal slots, capped retention | callback flood, depth, admission/close-in-flight tests; actual allocator measurements |
| Failed capture degrades existing health | PARTIAL_EVIDENCE before SDK exit | callback/setup/finish fault tests; real existing exporter health submission |
| Existing HTTP indicator/schema/digest unchanged | existing exporter only, no new route | existing exporter regressions;4 emitted platform-model/digest checks; shared fixture/Node checks |
| Python 3.11–3.13/core0deps/extra isolation | optional pinned extra | matrix, wheel/sdist, no-extra and selected-extra install checks |
| Performance reported honestly | bounded offline benchmark | PERFORMANCE.md / PERFORMANCE_DATA.json; no capacity/negligibility claim |
| Design / implementation / security / validator independence | reviewer-owned reports | reviews/ARCHITECTURE_REVIEW, IMPLEMENTATION_REVIEW, SECURITY_REVIEW, INDEPENDENT_VALIDATION |

All test file names: `tests/unit/instrumentation/test_model_collector.py`,
`tests/integration/test_langchain_instrumentation.py`, `tests/unit/test_release_artifact_guards.py` plus unchanged
SDK/exporter/contract trees. Review test counts overlap and must not be summed as distinct coverage.

Deferred: remote P18/P20 producers, stream/batch, state/memory, pricing, second framework and full LangGraph.
These are broader P30 follow-ups, not silent acceptance claims for this initial vertical slice.

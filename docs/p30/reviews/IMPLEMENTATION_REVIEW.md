# Independent P30 implementation review

Reviewer: fresh Session 3 implementation reviewer. Date: 2026-10-22.

## Scope and method

Read the original Session 3 requirement, repository AGENTS.md, architecture and independent architecture review; inspected the framework-neutral model, collector and controller, optional LangChain adapter, dependency/CI changes and instrumentation tests. Checked the installed pinned framework's configuration and callback-manager implementation rather than assuming callback copying or exception handling behavior.

Implementation review used a separate copied repository and a newly installed Python 3.11.17 environment with `dev,langchain,http` extras. No platform source, original dirty repositories, customer application, cloud resources or author environment was modified. Reviewer additions were disposable tests outside the repository. This reviewer owns this report.

## Findings and assessment

No actionable BLOCKER, HIGH or MEDIUM implementation finding in the reviewed source snapshot.

- Explicit invocation wrappers reuse the existing SDK lifecycle on the calling context. Sync, async, nested and threaded paths keep separate collectors and stable SDK parent identity. Application return identity and original exception objects are preserved.
- The pinned callback manager copies both handler collections. Filtering adapter-owned inherited handlers on the copy avoids nested capture duplication while retaining caller handlers, metadata, tags and identity. Explicit `run_id=None` remains supported because the pinned public configuration normalizer removes null values before generating a framework root identity.
- Accepted spans retain terminal capacity; closed spans remain bounded deduplication entries until finish. Dropped starts, orphans, callback errors and unfinished spans are visible and degrade measurement health. Diagnostics saturate and no unbounded rejected-identity table exists.
- Callback exceptions are contained before framework logging. Chat start is explicitly implemented. Error classification at the SDK exit boundary uses a fixed class while preserving cancellation. No model/tool payload, response text or arbitrary metadata is retained in normalized events.
- Token availability remains explicit; absent, invalid or ambiguous totals are unknown. Captured model starts, framework retry signals and logical SDK invocations are distinct concepts. No automatic semantic evaluation or monetary estimate is introduced.
- Disable/close/admission behavior preserves customer work. Core imports do not import the optional framework until instrumentation setup; mandatory runtime dependencies remain empty.
- The stable SDK event union, HTTP exporter and wire contract are unchanged. Detailed spans remain local; this does not complete remote step/tool ingestion.

Minor documentation hygiene observations were sent to the author: update the architecture's pre-review status after its gate closes, and avoid embedding developer filesystem paths in public/distributed review material. These do not establish a code defect or grant publication approval.

## Independently executed validation

| Check | Actual result |
|---|---|
| Instrumentation unit and pinned real-framework integration files | 48 passed |
| Additional reviewer tests | 3 passed |
| Existing exporter/API/protocol/indicator/release/review regression subset | 435 passed |
| Strict mypy on source | Success: 70 source files |

The three additional tests verify shared callback-manager configuration across 24 threaded invocations, unchanged framework kwargs and explicit null run identity, and nested asynchronous wrapper parent/context behavior. The exporter subset ran the existing `test_experimental_http_exporter_api.py`, `test_p28_http_protocol.py`, `test_http_exporter.py`, `test_http_exporter_indicator_allowlist.py`, `test_http_exporter_release_regressions.py` and `test_http_exporter_review_regressions.py` files.

Disposable review evidence is under `/tmp/gentlity-p30-implementation-review.Gic4t6`: `focused.log`, `independent.log`, `http-regression.log`, `mypy.log`, installation logs and `test_independent.py`. Temporary paths are local evidence locations, not an enduring published artifact store.

## Gate and limits

**Implementation assessment: GO for the reviewed additive experimental slice, subject to final-source recheck and the remaining independent security/validation, full Python matrix, package and CI gates.** This report does not claim those other gates passed. It does not approve merge, release, production readiness or full P30 roadmap completion.

Limits remain explicit: pinned LangChain Core 1.6.13, invoke/ainvoke only, local detailed traces, no semantic correctness inference, no persistent termination recovery, no provider HTTP-attempt inference, no hard Python callback latency guarantee, customer-owned alias sensitivity and third-party tracing policies. Existing trusted SDK sinks retain their documented behavior. D14 remains OPEN; Phase B remains NO-GO.

## Final-source recheck

Refreshed the separate reviewer copy after the author signaled final source and documentation. Independently inspected the security S-1 correction: every terminal callback supplies its expected kind; mismatched terminals are partial, closed parents reject new children and conflicting duplicate identities increment error diagnostics. The correction preserves bounded state and application behavior. Reviewed the public guide, offline example, benchmark harness, recorded performance data, compatibility and traceability documents. The guide clearly identifies the feature as unreleased/experimental and detailed traces as local. Recorded overhead percentages agree with the raw JSON; empirical small-sample tail values and incremental allocation limits are disclosed.

- Final focused checks: **99 passed**, comprising the repository instrumentation and artifact-guard files plus three reviewer tests.
- Offline sync/async/tool/model/explicit-evaluation example: passed.
- Benchmark execution smoke (`--iterations 2 --repeats 1`): passed; 2,002 bounded events, 999 captured tools and explicit incomplete state. This was a harness check, not a replacement performance measurement.
- Final strict mypy: success, 70 source files.
- Runtime manifest matches the independent validator: `608e3554306ce8ffc965862606a0ee5c5d1de11eb99591151513f3e779cd8324`.
- Final independent full Python 3.11 run initially: **1 failed, 1,794 passed, 1 skipped** in 21.02 seconds. The failure is recorded below; it must not be described as a passing final suite.

### IR-1 — MEDIUM — New README link violates package-index safety

The new root README link uses repository-relative `docs/AUTOMATIC_INSTRUMENTATION.md`. Existing contract test `tests/contract/test_readme_links.py::test_root_readme_links_are_package_index_safe` fails because the README is also rendered outside GitHub on package indexes, where that link does not resolve correctly. Required correction: use the existing absolute HTTPS GitHub documentation-link convention and preserve the contract test unchanged. Author notified; independent recheck pending. No runtime defect or wire-contract change is implied.

Evidence: `final-focused.log`, `example.log`, `benchmark-smoke.json`, `final-mypy.log`, `final-full311.log` in the disposable review evidence directory above. The existing P29 configured-platform test remains the sole skip; no fresh platform/database round trip is claimed.

### IR-1 independent closure and final verdict

**IR-1 CLOSED.** The author changed only the new README target to the absolute HTTPS GitHub documentation URL. This reviewer refreshed the copied README and independently reran the unchanged contract file: **7 passed**. The corrected copied full Python 3.11 suite then passed **1,795 tests, 1 skipped** in 20.71 seconds. The initial failed log remains retained.

After the author added the final three dependency/no-global-effects regressions, this reviewer refreshed the entire final source again. Missing and unsupported dependencies are tested in fresh processes before any framework import; setup/disable/enable/close leave framework callables and tracing environment unchanged. Selected dependency/integration/README tests passed **48 tests**, and the final complete Python 3.11.17 suite passed **1,798 tests, 1 skipped, no failures** in 19.79 seconds (`final-full311-latest.log`). The skip remains the explicitly configured external P29 platform-model test. No test expectation or implementation was changed by this reviewer.

The architecture status now reflects its independently closed gate. Internal `docs/p30` material is explicitly excluded from source distributions, while the public guide and example remain available; the independent artifact validator has separately verified the complete package workflow. No platform source, stable SDK lifecycle/evaluation/exporter implementation or wire-schema change was introduced by the final correction.

**Final implementation recommendation: GO for owner review of this additive experimental local-capture slice.** No unresolved BLOCKER, HIGH or actionable MEDIUM implementation finding remains. Security and independently executed validation reports are separate evidence; required PR CI and owner review remain gates and are not presumed green by this report. This does not authorize merge, release, deployment, hosted readiness or full P30 roadmap completion. D14 OPEN; Phase B NO-GO.

## Final test-only coverage closure

After the runtime content remained unchanged, independently read and executed the four final test cases added for interpreter/application control signals, abrupt process termination and intermediate sampling: **4 passed, 39 deselected** in 0.37 seconds (`final-signals-sampling.log`). SystemExit and KeyboardInterrupt preserve the original exception instance, release admission and reset SDK context while recording the observed failure. The subprocess SIGTERM case emits only RunStarted and does not fabricate a completed terminal event. Two separately configured seed-0 wrappers make matching intermediate-rate admission decisions across different input sequences, consistent with admission preceding application outcomes. These tests do not imply crash recovery, durable flush, unbiased concurrent sampling or a changed runtime guarantee.

The earlier complete-suite count of 1,798 remains the actual independent full run before these four additions; it must not be relabeled as a later full-suite execution. The separately selected four additions pass. No additional implementation finding; GO-for-owner-review recommendation and all approval limitations remain unchanged.

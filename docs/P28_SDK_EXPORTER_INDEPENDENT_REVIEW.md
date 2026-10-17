# P28 SDK HTTP exporter — independent comprehensive review

Date: 2026-10-16 (workspace local date). Author: independent Codex reviewer context `/root/p28_independent_review`, which did not implement the exporter. This report is reviewer-authored. It records the original delivery, not approval of subsequent corrections.

Status: `P28_SDK_EXPORTER_REMEDIATION_REQUIRED`.

## Scope, authority and independence

Performed one comprehensive read-only implementation review against the attached original request, both repositories' AGENTS.md/CLAUDE.md, the SDK implementation report and owner decision record, final revision-16 SDK API contract and technical architecture, approval package/reconciliation, PC-2 D1/D4 decisions, permanent language-neutral contract, SDK source, tests, reference assets, packaging and CI. The later owner selections (UUID v4, RA-b, literal-only loopback, J2, P1 and L2) govern over historical draft alternatives. PC-2 extensible acknowledgements and event-only `conflict` versus terminal `deployment_identity_mismatch` remain binding.

No source, tests, fixtures, platform files or implementation report were edited by this reviewer. Only this findings report was authored. Reproductions used local mock transports or pure state cores, without external HTTP. No commit or external change was made. The coordinator began remediation after receiving findings; original source evidence is preserved at `<tmp>/p28-review-baseline/src/agent_reliability`. **All source line numbers below refer to that pre-remediation snapshot**, with the corresponding repository-relative path given.

The findings were sent promptly to the coordinator. Corrections require a different fresh independent context for targeted verification; this report does not assert that corrections are verified.

## Findings

| ID | Severity | Finding |
|---|---|---|
| R1 | HIGH | Response-body read errors erase already received authentication/rate-limit status and headers |
| R2 | HIGH | Both async workers can suspend all deadline processing and status publication |
| R3 | MEDIUM | Awaited async close returns before asynchronous transport disposal completes |
| R4 | MEDIUM | Default TLS trust excludes native Windows certificate stores |
| R5 | MEDIUM | Duplicate and corrected final-health submissions are admitted for one run |
| R6 | MEDIUM | Response cookies accumulate without a retention bound |
| R7 | LOW | Several specified operational diagnostics are absent or private-only |

No BLOCKER was found. Passing the delivered test suite does not resolve these independently reproduced defects.

### R1 — HIGH: known HTTP control effects disappear on body-read failure

**Evidence:** `src/agent_reliability/adapters/http_event_sink.py:259-282` and `506-538`. Both adapters call `Core.complete(status, body, Retry-After)` only after fully reading the stream. If iteration raises, the outer handler calls `complete(failure=...)` with default status 0 and no headers.

**Reproduction:** `<tmp>/p28_independent_repro.py`, run with `<tmp>/p28-sdk-validation/bin/python`. A `httpx.MockTransport` returns HTTP 403 with a `SyncByteStream` whose iterator raises `httpx.ReadError`. Configure `retry_max_attempts=1`, emit a valid `RunStarted`, then `flush(1)`. Observed sink `open`, terminal `RETRY_EXHAUSTED`, `error_code=retry_exhausted`, and uncertainty true. Required outcome is authentication pause, not ordinary-attempt exhaustion. The coordinator's sync/async 401/403/429 regression cases also independently failed against the original snapshot.

**Impact:** the client can keep sending after a received 403, treat 401 as ordinary failure instead of credential recovery, and bypass a received 429/Retry-After. Body-dependent 404/422 classification cannot be inferred from absent content, but known status/header-only effects must survive. A broken body must never fabricate an acknowledgement or error envelope.

**Correction:** retain the received status and Retry-After separately from body-read success. Apply status/header-defined outcomes even if the body is unreadable; use the documented malformed-body fallback for body-dependent classifications. Preserve uncertainty and late-response rules. Test both adapters with stream errors after headers, including a partially read body and 429 guidance.

### R2 — HIGH: async deadlines depend on a delivery worker returning

**Evidence:** `http_event_sink.py:350-352`, `374-380`, `475-483`, `506-538`; `_http_delivery.py:392-445`. Only worker activity or a mutating/publication API call advances `Core.tick`. The async `status` property correctly returns an immutable cached snapshot, but there is no independent timer task. With both workers awaiting responses, nothing checks expiry or republishes state.

**Reproduction:** `<tmp>/p28_independent_repro.py`. Create `AsyncHTTPEventSink` with `active_delivery_seconds=.03`, `maximum_residence_seconds=.05` and a mock 201 response whose `AsyncByteStream` awaits an unset `asyncio.Event`. Emit valid starts for two different runs, `await asyncio.sleep(.2)`, then read `status` without calling flush. Observed `queue_depth=2`, both records `SENT`, sink `open`, despite both budgets having expired. The owner loop remains responsive. The corresponding regression independently fails against original code.

**Impact:** active/residence bounds and diagnostic retention are not autonomously enforced; a caller must poll a mutating API. HTTPX read timeout bounds inactivity rather than total exchange duration, so a trickling server can extend the condition well beyond the ordinary per-read timeout. Expired async attempts also occupy the two workers until the network operation returns, preventing unrelated eligible work from progressing.

**Correction:** add a bounded owner-loop maintenance timer independent of delivery workers. Atomically advance timers/publish snapshots and cancel/release abandoned async network attempts without altering terminal records when a late result arrives. Keep two-request concurrency, per-run FIFO and sticky uncertainty. Test progress without `flush`, including both workers occupied, active and absolute expiry, and queued unrelated work.

### R3 — MEDIUM: async transport cleanup outlives awaited close

**Evidence:** `http_event_sink.py:420-443`. `close` schedules `_dispose` with `create_task` and returns immediately. `_dispose` gathers workers and only then awaits `AsyncClient.aclose`; the caller cannot await its completion through the public API.

**Reproduction:** `<tmp>/p28_review_more.py`, `run3`. Supply an `httpx.AsyncBaseTransport` whose `aclose` awaits `asyncio.sleep(.01)` then marks itself closed. An `asyncio.run` main creates an empty sink and awaits `close(1)`, then exits. Observed transport `closed=False`, `_cleanup.cancelled()=True` after loop shutdown. There was ample close budget; ordinary empty/mock disposal that completes synchronously does not expose this failure.

**Impact:** documented `await close` / async-context-manager usage can leave transport cleanup incomplete when the application closes its loop immediately afterward. Background cleanup exceptions can also become unobserved task errors.

**Correction:** await disposal within the original caller's remaining close budget, with cancellation-safe finalization and clear behavior when no budget remains. Repeated/concurrent closes must share cleanup and preserve the first deadline. Test a genuinely asynchronous `aclose`, immediate loop exit, cancellation and repeated close.

### R4 — MEDIUM: default trust is not the native system trust on Windows

**Evidence:** `http_event_sink.py:65-79`. With no explicit CA bundle, the adapter loads only OpenSSL's compiled cafile/capath. It never imports Windows `ROOT`/`CA` stores. If those compiled paths do not exist, `load_verify_locations(None, None)` raises and becomes `ConfigurationError(ca_bundle_invalid)` even though the caller supplied no CA bundle.

**Reproduction:** `<tmp>/p28_review_more.py`. Patch `ssl.get_default_verify_paths()` to retain its other fields but set `openssl_cafile` and `openssl_capath` to absent paths. `_client_options(None, None)` raises `ConfigurationError: ca_bundle_invalid`. This reproduces the missing-compiled-path branch; a live Windows host was not available. The source omission of native-store loading is direct evidence, and the coordinator's simulated native-Windows-store regression fails on the original snapshot.

**Impact:** the universal Python package's default TLS construction fails or lacks native trusted roots on normal Windows installations. Explicit CA bundles can work around it, but that does not satisfy the approved default-system-trust policy.

**Correction:** explicitly load the native Windows trust stores when applicable while retaining certificate/hostname verification and ignoring ambient SSL_CERT_FILE/SSL_CERT_DIR. Keep explicit-bundle behavior deterministic. Test native-store loading with no compiled paths and hostile ambient CA variables; do not claim a live Windows TLS certification from simulation.

### R5 — MEDIUM: immutable final health is unenforced

**Evidence:** `_http_delivery.py:712-737`; binding state at `Core.bindings` retains only parent/start time. Every `submit_measurement_health` call generates a fresh ID (unless supplied) and admits another closure record, without a per-run final-health marker. Contract section 9 explicitly requires duplicate or corrected final health to be rejected before enqueue; Architecture sections 12 and 14.3 permit exactly one final health submission per active binding.

**Reproduction:** `<tmp>/p28_health_repro.py`, with `PYTHONPATH=<tmp>/p28-review-baseline/src`. Create a pure Core, emit a valid start, submit healthy health, then degraded health containing `partial_evidence`. Both succeed. Queue contains the start and two different final-health payloads with distinct `meas_...` IDs. Explicit measurement IDs do not prevent admission either.

**Impact:** direct public capability use can publish multiple contradictory final assessments and consume closure reserve with duplicates. Normal SDK finish currently submits once, so the defect is narrower than every SDK run.

**Correction:** retain a bounded per-active-binding admission marker; set it only after successful final-health admission and reject subsequent duplicate/corrected submissions with a fixed local code. Clear it with binding release/close. A rejected first admission must remain retryable. Network retries must still reuse the original record/body/id.

### R6 — MEDIUM: cookies accumulate outside all exporter bounds

**Evidence:** `http_event_sink.py:153`, `345-347`, `254`, `503`. HTTPX clients retain their normal cookie jars. Removing the outgoing `Cookie` header suppresses transmission but does not prevent HTTPX extracting response `Set-Cookie` headers into its jar.

**Reproduction:** `<tmp>/p28_cookie_repro.py`, with baseline PYTHONPATH. The mock transport acknowledges 30 valid starts and sets a distinct 1 KiB cookie on each response. Runs are released and the queue drains. Observed `queue_depth=0`, `len(sink._client.cookies)=30`. This can continue independently of record, byte, binding, tombstone and diagnostic caps. The coordinator's sync and async regressions both independently fail against original code.

**Impact:** a long-lived exporter accumulates unbounded remote-controlled response data. Architecture section 11 and Contract section 12 specify no cookies; the current header removal satisfies only the transmission portion of that requirement.

**Correction:** prevent cookie acceptance/storage in both clients, preferably a reject-all cookie policy or equivalent reliable client hook. Do not rely on clearing a shared jar after responses, which can race concurrent workers. Test many distinct cookies, zero retained cookies and no outgoing Cookie header.

### R7 — LOW: operational diagnostics are incomplete

**Evidence:** `_http_delivery.py:609-612` increments `exception_type_substituted`, but `DeliveryStatusSnapshot`/`snapshot` never expose that counter. `release_run` at lines 500-511 silently returns for unknown runs without the specified `release_unknown_run` count. `adapters/event_sinks.py:85-97` has no `composite_no_capable_child` counter. `sdk/client.py:529-533` returns after an unstamped final health without the specified `final_health_unstamped` diagnostic (the clock exception itself is reported).

**Reproduction/assessment:** source inspection and a pure-core invalid exception-label substitution demonstrate that the private counter increases while no public snapshot field changes. Searching these fixed diagnostic names confirms the other counters/labels are absent. Required diagnostic homes are Architecture 14.1, 14.3, 14.10 and 17.5. Delivery correctness is preserved; this is an observability gap, not another protocol blocker.

**Correction:** expose/emit the fixed bounded counters through an appropriate additive public diagnostic surface, or explicitly disposition this LOW limitation in the completion report. Avoid introducing evidence, exception messages or unbounded labels.

## Baseline intermittent failure — INFORMATIONAL

`tests/unit/adapters/test_adapters.py:39-43` asserts that two random UUID-v4 strings cannot end in `0` then `1`. Those are valid independent random suffixes: probability `(1/16)*(1/16)=1/256` for every execution. `UuidRunIdGenerator.generate` simply returns `str(uuid.uuid4())`. The test file is unchanged by the exporter work (`git diff -- tests/unit/adapters/test_adapters.py` empty). The implementation report's two recorded UUIDs are valid v4 values satisfying that false-failure condition. This is a pre-existing flaky assertion, not an exporter regression or reason to disregard a different failure. It did not fail in this reviewer's executions. Recommend a separate deterministic UUID-format/version test or removal of the invalid suffix inference; no change was made here.

## Validation performed by this reviewer

Commands used Python 3.13.16 from the provided isolated environment and ran locally without live integration.

| Command / activity | Result |
|---|---|
| `PYTHONPATH=<tmp>/p28-review-baseline/src <tmp>/p28-sdk-validation/bin/python -m pytest -q tests/contract/test_p28_http_protocol.py tests/unit/test_http_exporter.py` | 334 passed, including all 58 original exporter tests and 276 protocol tests |
| `PYTHONPATH=<tmp>/p28-review-baseline/src <tmp>/p28-sdk-validation/bin/python -m pytest -q --ignore=tests/unit/test_http_exporter.py` | 766 original tests passed; 13 newly added coordinator regression cases failed against original source, covering R1–R6 |
| Local `<tmp>/p28_independent_repro.py` | R1, R2 reproduced; async cleanup initially observed pending |
| Local `<tmp>/p28_review_more.py` | R3 asynchronous-disposal cancellation and R4 absent-path behavior reproduced; synchronous-completing cleanup controls passed |
| Local `<tmp>/p28_health_repro.py` with baseline PYTHONPATH | R5 reproduced |
| Local `<tmp>/p28_cookie_repro.py` with baseline PYTHONPATH | R6 reproduced |

The two pytest executions cover all original 824 tests (the protocol tests overlap). The second invocation discovered the coordinator's regression file while remediation proceeded; those 13 failures are expected defective-baseline evidence, not a clean-suite claim. This reviewer did not rerun corrections or claim targeted verification. Python 3.11/3.12, lint/format/mypy, builds, installed artifacts, fixture drift and Node checks are coordinator/final-validation responsibilities; their earlier implementation-report results were inspected but are not relabeled as this reviewer's executions.

## Review coverage and positive evidence

Public APIs retain the existing synchronous EventSink shape and an additive optional health capability. Normal SDK paths isolate ordinary sink exceptions, submit final health after terminal admission and release bindings through cleanup. Sync state transitions use a lock; provider callbacks run outside it on a bounded dedicated daemon helper. Async owner checks reject foreign-loop mutations, with immutable cached status and scheduled release. Start identity checks cover all four local AgentIdentity fields; transmitted v2 identity uses the approved triple and no invented organization member.

Queue records/bytes include in-flight/held work; ordinary admission leaves the approved closure reserve. Both limits independently reject new admissions; no lossless closure guarantee is claimed. Binding caps, tombstones and history are bounded, apart from R6's independent cookie jar. Per-run head selection preserves FIFO and other eligible run heads can bypass ordinary backoff. Timer strict-equality tests, sticky uncertainty, late-result discard, separate throttling budgets, retry identity/body reuse, auth generations/baselines, same-token resume refusal, compatibility-neutral responses and explicit gate recovery were inspected. The missing autonomous async timer is R2.

HTTPS/loopback procedures and RA-a/approved RA-b use the shared data-only vectors. URL checks precede credentials; explicit proxy/CA selection, trust_env false, TLS verification, redirect refusal, header/cookie isolation intent, request cap, streamed response cap, strict acknowledgement parsing and fixed diagnostic labels were examined. Acknowledgements tolerate additional members without allowing them to repair required fields, preserve last-member-wins decoding, strict UTF-8/BOM handling and minimum nesting/integer-token cases. v1/v2 canonical byte/digest vectors pass. `conflict` remains event-only; identity mismatch freezes delivery and cancels others.

No further confirmed defect was found in frozen auth-provider behavior or repeated close deadline handling: mismatches abandon current reads; late provider results are discarded; the first close deadline is retained by subsequent closes. The L2 record's phrase “Closing/Closed reject resume” differs from inherited Architecture R05, which permits recovery while Closing; the implementation follows inherited closing recovery. Given the recorded compatibility condition, this is a documentation clarification, not a newly asserted owner-policy blocker. Normal released/unknown-run error labels also differ in wording from older diagrams without changing delivery safety.

Optional HTTPX remains behind the HTTP extra; normal core APIs do not import the transport module. Packaging and artifact-verification source preserve dependency-free base installation and installed-extra smoke checks. Existing tests are useful but missed the boundary cases above: passing aggregate counts are not a security/lifecycle completeness proof. Initial performance values and compatibility retry amplification remain unmeasured production assumptions, as the report accurately states.

## Remaining integration and release gates

After remediation, a fresh independent targeted reviewer must verify each original finding, baseline-red/fixed-green regressions, and preserved security/protocol behavior. No second comprehensive review is requested unless the corrections materially change architecture/security/public contracts.

Combined PC-1 + PC-2 integration remains required: real machine authentication and `evidence:ingest`; failed-machine no fallback; tenant/organization isolation and tenant-hidden 404; schema-v1/v2 ingestion/digests; identity mismatch and changed-identity replay race; durable PostgreSQL 201/duplicate 200; event-only conflict; compatibility pauses/recovery and whole-fleet sequencing; 429/Retry-After timing; lost acknowledgements and idempotency; real TLS/proxy/credential isolation; concurrent runs, queue headroom, autonomous expiry and shutdown/resource cleanup. Do not perform that integration or modify the platform in this task.

Release additionally needs per-instance approved PC-1/PC-2 build evidence (unknown build IDs fail the sequencing gate), required platform validation/reviews, applicable production workload measurements and normal release authorization. Native Windows TLS, hostile real proxy/resolver behavior, GitHub Actions, and unavailable Go/Java consumers are not certified by local mocks or the Node reference harness. No production-ready verdict, approval signature, commit or release is inferred.

## Coordinator dispositions received after original review

The coordinator reports R1–R6 remediated with focused regressions; those claims are intentionally left for the separate targeted verifier. For R7 LOW, the coordinator explicitly defers the incomplete diagnostic reasons/counters because they do not affect wire, delivery or commitment correctness and an added public snapshot surface would broaden this correction. This records the coordinator's disposition, **not independent verification or endorsement**. The coordinator also plans to clarify the L2 Closing-resume wording using the inherited compatibility rule, without changing the existing state transitions.

## Closure reference — separate targeted verification, 2026-10-16

Read the separately authored [targeted independent verification report](P28_SDK_EXPORTER_TARGETED_VERIFICATION.md) by fresh context `/root/p28_targeted_verification`. Its final verdict is **`P28_SDK_EXPORTER_VERIFIED_WITH_INTEGRATION_GATES`**. That verifier reports R1–R6 corrected, including a residual R3 cleanup-exception branch found and resolved during targeted verification; **351 targeted tests pass on corrected source and 17 focused regressions fail against the original baseline**. R7 remains an explicit coordinator LOW deferral, neither a fix nor owner acceptance.

This addendum is a bookkeeping reference to the separate verifier's assessment, not another review or independent certification of corrections by this comprehensive reviewer. The original findings, severities, reproductions and original-delivery **`P28_SDK_EXPORTER_REMEDIATION_REQUIRED`** verdict above remain unchanged. The combined PC-1/PC-2 integration, native-platform/live-TLS evidence, applicable production measurements, per-instance platform build evidence and release-authorization gates remain as stated above and in the targeted report. No live-integration, production-readiness or release approval is inferred.

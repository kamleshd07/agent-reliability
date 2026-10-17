# P28 SDK HTTP exporter — targeted independent verification

Date: 2026-10-16. Author: fresh independent Codex context `/root/p28_targeted_verification`, which neither implemented the exporter nor performed its comprehensive review.

Status: `P28_SDK_EXPORTER_VERIFIED_WITH_INTEGRATION_GATES`. This is a targeted recheck, not a second comprehensive review.

## Scope and authority

Read SDK and platform AGENTS.md/CLAUDE.md, the attached original user request, the independent review, coordinator remediation report, SDK owner decisions, implementation-report context, relevant final revision-16 SDK API contract and architecture sections, and PC-2 owner decisions D1/D4. Later recorded owner selections govern historical proposed alternatives. Inspected the actual remediation diff against `<tmp>/p28-review-baseline/src`, the focused regression tests and relevant existing exporter/protocol tests. Platform access was read-only. This verifier authored only this report; no source, tests, platform files or original reviewer report were edited, and no commit, external publication or live integration occurred.

## Individual findings

| Finding | Targeted assessment and evidence |
|---|---|
| R1 HIGH — status lost on failing response body | Corrected. Six sync/async 401/403/429 partial-body/read-error cases fail against original source and pass current. Received status and Retry-After survive; partial body is discarded rather than treated as an acknowledgement. Auth pauses and a 60-second rate gate are preserved without consuming the ordinary retry budget. Response-close exceptions cannot reduce a record twice. |
| R2 HIGH — async deadlines stall with both workers occupied | Corrected. Independent maintenance advances/publishes state while two requests hang. Focused tests demonstrate active expiry, cancellation of both attempts and reuse of workers to commit an unrelated run. An additional independent reproduction with active budget 1 second and residence .03 seconds expired both hung bodies after .12 seconds without flush/status mutation: queue zero, two cancellations, `residence_exceeded`, sticky uncertainty. No transport polling or public contract change was introduced. |
| R3 MEDIUM — awaited cleanup outlives close | Corrected after one targeted feedback/fix iteration. Slow asynchronous cleanup completes before loop exit within budget; timeout remains bounded, later close joins shared cleanup, and caller cancellation does not cancel shared cleanup. The residual unobserved-exception branch was independently reproduced, reported, fixed and reverified as described below. |
| R4 MEDIUM — native Windows trust omitted | Corrected on source and emulation evidence. With absent compiled paths, emulated CA/ROOT DER certificates load into a verified hostname-checking context. An independent variant sets hostile SSL_CERT_FILE/DIR and uses a SERVER_AUTH OID trust set; both native stores are enumerated and ambient files remain ignored. No real Windows host or Windows TLS handshake was available; this is portability correction evidence, not native-platform certification. |
| R5 MEDIUM — mutable/multiple final health | Corrected. Duplicate and changed final-health submissions are rejected before admission. Marker insertion follows successful admission only; queue-full rejection leaves first submission retryable. Successful retry marks the run; release clears it, and close clears all markers. The marker is bounded by active bindings; original record IDs/bodies remain stable for network retries. |
| R6 MEDIUM — cookie retention | Corrected. Both clients receive a reject-all CookieJar policy; twenty distinct 1 KiB response cookies leave each jar empty, with no outgoing Cookie header. This blocks acceptance rather than racing jar clearing across workers. |
| R7 LOW — incomplete structural diagnostics | Explicitly deferred by coordinator, accurately described in HTTP_EXPORTER.md and remediation report. Not fixed and not owner accepted. The limitation concerns substitution, unknown release, composite without capable child and unstamped final-health diagnostics. This is an adequate explicit LOW disposition under the requested workflow; delivery/protocol completeness must not be conflated with complete diagnostic coverage. |

### R3 residual issue and correction evidence

The first correction used `asyncio.wait` to join cleanup but never consumed its exception. Independently reproduced with a custom AsyncBaseTransport whose `aclose` raises `RuntimeError('private cleanup detail')`: `await close(1)` returned, cleanup was done with an unretrieved exception, and deleting the sink plus `gc.collect()` caused the loop exception handler to receive `Task exception was never retrieved`. This was the cleanup-exception branch already identified in original R3, not an expanded comprehensive review finding. The coordinator was notified before final disposition. The final `_dispose` catches ordinary transport-cleanup exceptions, increments the fixed `transport_cleanup_failed` counter and emits only that constant label, with no exception value or traceback. Logger-handler exceptions are isolated; control cancellation still propagates. The added focused regression passes current and fails original source. An independent rerun using both a throwing `aclose` and a throwing log handler verified completed cleanup with no stored task exception, one fixed counter increment, and no loop exception report after garbage collection. R3 is closed on this evidence; cleanup failure is observed/redacted rather than a claim that arbitrary transport disposal always succeeds.

## Commands and results

All pytest commands ran from `<workspace>/agent-reliability`, using the supplied Python 3.13 environment.

```text
PYTHONPATH=<tmp>/p28-review-baseline/src <tmp>/p28-sdk-validation/bin/python -m pytest -q tests/unit/test_http_exporter_review_regressions.py
```

Initial result: **16 failed in 8.00 seconds**, as expected against the defective original source. After the residual R3 regression was added, the exact same command was rerun: **17 failed in 8.05 seconds**, including the expected unretrieved raw cleanup exception on original source. These include the original thirteen finding cases and four later edge cases. The failed-admission retry test additionally references the new marker attribute and therefore its baseline failure alone is not proof of the original duplicate-health defect; the two duplicate/corrected-admission tests directly establish that defect.

```text
<tmp>/p28-sdk-validation/bin/python -m pytest -q tests/unit/test_http_exporter_review_regressions.py tests/unit/test_http_exporter.py tests/contract/test_p28_http_protocol.py
```

Initial correction result: **350 passed in 1.41 seconds** (16 new focused, 58 existing exporter, 276 protocol tests). The residual cleanup-exception issue above demonstrates why aggregate green tests did not alone close R3. After its correction, independently reran the exact same command: **351 passed in 1.46 seconds** (17 focused, 58 existing exporter, 276 protocol).

Additional Python heredoc reproductions used `<tmp>/p28-sdk-validation/bin/python -` and directly instantiated the public AsyncHTTPEventSink with HTTPX mock/custom transports. Independently confirmed: autonomous absolute expiry of two hung streams; native trust emulation with hostile ambient CA variables; cancellation of a close caller during cleanup followed by a successful later join; and the residual R3 exception behavior followed by its corrected behavior with an additionally failing log handler. No HTTP request left the process.

## Preserved behavior and limitations

The correction diff is limited to transport adapters and the per-binding final-health admission marker. It does not alter canonicalization, wire fields, parsing grammar, dependency bounds, identity checks or capacity/reserve values. Existing exporter and protocol tests cover preserved HTTPS/loopback policy, ambient configuration isolation, TLS verification, redirect gates, body bounds, credential redaction, event-only `conflict`, terminal `deployment_identity_mismatch`, acknowledgement extensibility and strict required fields, digest vectors, Retry-After grammar, FIFO/gates, late-result discard, uncertainty and close semantics. No material unresolved regression was found in the touched paths; the additional R3 issue raised during this targeted verification was corrected and reverified.

The pre-existing UUID assertion in tests/unit/adapters/test_adapters.py remains unchanged (`git diff -- tests/unit/adapters/test_adapters.py` empty). Rejecting valid independent UUID-v4 suffixes `0` then `1` gives a 1/256 false-failure probability. It was not exercised by this targeted selection and is not relabeled an exporter regression.

Coordinator final full-suite Python 3.11/3.12/3.13, static, packaging and Node results belong to the coordinator's final matrix; they are not this verifier's executions. Native Windows, real TLS/proxy behavior, live combined platform ingestion, unavailable Go/Java consumers and production workload measurements are not certified by local mocked evidence.

Combined PC-1 + PC-2 integration remains gated on real machine authentication and evidence:ingest scope, tenant/organization isolation and hidden 404, v1/v2 ingestion and digests, durable 201/duplicate 200, changed-identity replay race, event-only conflict and terminal identity mismatch, compatibility pause/recovery, rate-limit/Retry-After timing, lost acknowledgements/idempotency, TLS/proxy/credential isolation, concurrent bounds and shutdown. Per-instance approved build evidence and normal release authorization remain required. No owner approval, production-readiness claim or release is inferred.

## Verdict

`P28_SDK_EXPORTER_VERIFIED_WITH_INTEGRATION_GATES`. R1–R6 are verified corrected, including the residual R3 branch found during this targeted recheck. R7 remains an explicitly documented coordinator LOW deferral, not a fix or an owner acceptance. Local targeted evidence supports proceeding to the stated combined-platform integration and release gates; it does not certify live integration, native Windows operation or production readiness.

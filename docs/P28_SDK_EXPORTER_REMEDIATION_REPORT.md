# P28 SDK HTTP exporter remediation evidence

Date: 2026-10-16. Author: implementation coordinator `/root`.

One fresh independent context performed the comprehensive review. Its report
is `P28_SDK_EXPORTER_INDEPENDENT_REVIEW.md`, owned by that reviewer. This
coordinator does not edit or determine that report's findings or verdict.
A different fresh context performs targeted verification, not another full review.

## Confirmed findings and corrections

| ID | Severity | Correction | Focused regression evidence |
|---|---|---|---|
| R1 | HIGH | Preserve received HTTP status/Retry-After if body reading fails; discard partial body, apply status-class behavior; suppress response-close failures so one request has one outcome | Sync and async 401/403/429 failing streams retain auth/rate gates and 60-second guidance instead of exhausting ordinary attempts |
| R2 | HIGH | Independent native async maintenance publishes deadlines and cancels expired attempt tasks; two workers regain slots after their attempt expires | Both streams hung, no flush/status mutation: active expiry occurs, uncertainty retained, requests cancelled; later run commits |
| R3 | MEDIUM | Await shared async cleanup within remaining caller budget; timeout/caller cancellation does not cancel the shared cleanup; idempotent later close can join | Slow transport aclose completes before asyncio.run exits with available budget; stalled cleanup returns on timeout and later close joins |
| R4 | MEDIUM | Load native Windows CA/ROOT stores when available in addition to compiled OpenSSL paths; honor server-auth trust and keep CERT_REQUIRED/check_hostname | Emulated native store with absent compiled paths loads trusted DER certificate without environment fallback; no Windows host certification claimed |
| R5 | MEDIUM | Bounded per-binding successful-final-health marker; reject duplicate/corrected final health; set only after admission, clear at release/close | Duplicate and corrected records rejected; queue-full first attempt remains retryable and marker clears on release |
| R6 | MEDIUM | Reject-all cookie acceptance/return policy on both clients; keep outgoing Cookie removal as defense | Twenty unique 1 KiB response cookies per client leave jar empty and no outgoing Cookie header |

Implementation source changes are confined to
`src/agent_reliability/adapters/http_event_sink.py` and `_http_delivery.py`.
Regression tests live in `tests/unit/test_http_exporter_review_regressions.py`.
No wire fields, canonical algorithms, dependency ranges, queue/reserve values,
credentials or platform code were changed.

R1-R6 changes implement existing approved requirements. The added async
maintenance/request-task separation preserves native async transport, two
worker slots and the original serialized state core; it is not a new gate
or public contract. Async cleanup never promises that arbitrary uncooperative
custom transport code can be forcibly stopped. A zero/exhausted close budget
may leave cleanup pending; a later positive-budget close can join it while
the owner loop remains alive. Documentation now states this explicitly.

## Regression proof

The original source was copied before remediation to
`<tmp>/p28-review-baseline/src`. New focused cases were run before the
corresponding fixes: R1/R2 produced seven failures; R3-R6 produced six failures.
The comprehensive reviewer independently ran all thirteen against the original
snapshot and observed thirteen failures, while original SDK tests passed.
After correction, seventeen focused cases pass, including additional retry,
worker-reuse and bounded-cleanup edge cases. The targeted verifier must judge
these results independently; passing implementation tests alone is not closure.

Commands from the SDK root:

```text
<tmp>/p28-sdk-validation/bin/python -m pytest tests/unit/test_http_exporter_review_regressions.py -q
<tmp>/p28-sdk-validation/bin/python -m pytest tests/unit/test_http_exporter_review_regressions.py tests/unit/test_http_exporter.py -q
```

## LOW/informational dispositions

R7 LOW: deferred and documented in `docs/HTTP_EXPORTER.md`. Some structural
reason diagnostics are private or absent (substitution, unknown release,
composite with no capable child, unstamped final health). This does not change
wire evidence, commitment classification, uncertainty or pause/retry decisions.
Avoid adding a new public diagnostic API while fixing unrelated transport
correctness defects. Existing public delivery health remains usable; complete
structural-diagnostic coverage is not claimed. This is a coordinator disposition,
not a fabricated owner acceptance or reviewer endorsement.

The L2 Closing-resume wording discrepancy is clarified in the owner decision
record under its compatibility condition: preserve Architecture R01/R05
recovery during Closing, reject Closed/terminal ConfigurationFailed. No runtime
state change or new approval is claimed.

The unchanged UUID baseline test rejects valid random outputs ending `0` and
`1`, a probability of 1/256 for independent UUID-v4 draws. It remains unchanged;
report any occurrence separately from exporter regression results.

## Validation, targeted verification and gates

Final command matrix, targeted verdict and integration checklist are recorded
in the implementation report and the separately authored targeted-verification
report. No live platform integration, Go/Java conformance, commit, PR, deployment
or release is performed. Original platform/unrelated source changes remain
outside remediation.

## Targeted R3 follow-up

The fresh verifier reproduced one residual issue in the first R3 correction:
a failing `aclose` left an unobserved exception on the cleanup task. A new
regression failed before correction. `_dispose` now observes ordinary cleanup
exceptions, increments the fixed bounded `transport_cleanup_failed` counter,
and emits only that constant log label without exception content. A failing
application log handler is isolated. Caller cancellation remains a control
signal. The regression checks the task has no unobserved exception, garbage
collection produces no loop-error callback, and secret exception text is
absent from logs. Seventeen focused tests now pass; the targeted reviewer
must independently re-check this correction.


## Final independent disposition

Fresh verifier `/root/p28_targeted_verification` finalized
`P28_SDK_EXPORTER_TARGETED_VERIFICATION.md` with
`P28_SDK_EXPORTER_VERIFIED_WITH_INTEGRATION_GATES`: R1–R6 closed, including the
R3 follow-up; R7 explicitly deferred LOW. It independently ran 351 passing
current focused/exporter/protocol cases and observed all 17 focused regression
cases fail against the original snapshot. Its report owns that judgment; this
coordinator records the result. Final complete suites: 841 passed on each of
Python 3.11.17, 3.12.15 and 3.13.16. Ruff/format/strict mypy, Node references,
fixture drift, final wheel/sdist and isolated artifact/extra checks passed.
Remaining integration/native-platform/production/release gates are unchanged.

# P28 SDK HTTP exporter implementation report

Date: 2026-10-16. Implementation author: this Codex session.

Status: `P28_SDK_EXPORTER_VERIFIED_WITH_INTEGRATION_GATES`.

The original Prompt 1 implementation and self-validation evidence is retained
below as history. Current Prompt 2 review/remediation/validation evidence is
appended at the end. No live PC-1/PC-2 certification or release readiness is
claimed.

## Approval and baseline

Owner decisions are recorded in
[P28_SDK_EXPORTER_OWNER_DECISIONS_001.md](P28_SDK_EXPORTER_OWNER_DECISIONS_001.md):
Project owner, 2026-10-16, relayed through ChatGPT, no signature, SDK scope.
The owner supplied E3/E4/E6/E7/E9/E10/E11 starting values, adopted reviewed
requirements/recommendations under compatibility conditions, and explicitly
selected UUID v4, RA-b and the documented focused L2 gate specification in
follow-up answers. These close the earlier implementation gate report's
SDK blockers. No production workload target or performance certification was
invented. See that decision record for the pilot hypothesis/measurement plan.

Read SDK/platform AGENTS.md and CLAUDE.md, approval package/reconciliation,
revision-16 API contract and later PC-2 D1/D4 amendments, decision register,
architecture state/timing/auth/lifecycle rules, implementation plan,
language-neutral contract, reference vectors, SDK event/lifecycle/evaluator
code, packaging, CI and existing tests. Platform access remained read-only.
The newer owner selections qualify older proposed alternatives; they do not
retroactively approve every historical draft.

Initial SDK working tree contained unrelated `docs/ARCHITECTURE.md` changes
and untracked AGENTS.md/CLAUDE.md. Those files were not edited. The prior
blocked report is replaced by this current report, with the historical gate
and its resolution recorded here and in the owner-decision record.

A self-validation correction is explicit: one sentence in the focused L2
proposal incorrectly suggested redirects would not set uncertainty. Under
the owner's compatibility condition, the mandatory Architecture 17.2 marker
rule is retained: a sent redirect without a definite rejection sets it;
TLS verification failure before write does not. Gate transitions remain
those selected by the owner. No relaxed evidence-integrity rule is claimed.

## Changed files and functionality

| Files | Change |
|---|---|
| `src/agent_reliability/adapters/http_event_sink.py` | Sync/thread-safe and native async exporters; bounded streaming responses, explicit secure clients, trace-based first-write marker, close/resume/context lifecycle |
| `src/agent_reliability/adapters/_http_delivery.py` | Serialized shared admission/state core, exact identity mapping, capacity/reserve checks, bounded bindings/tombstones/diagnostics, retries, independent gates, credential generations and single-flight helper |
| `src/agent_reliability/adapters/_http_protocol.py` | v1/v2 canonical bytes/digests, strict acknowledgement parser, exact URL procedures, both RA grammars for conformance; runtime uses approved RA-b |
| `src/agent_reliability/ports/event_sink.py` | Additive optional HealthEvidenceSink; EventSink unchanged |
| `src/agent_reliability/adapters/event_sinks.py` | Composite capability fan-out with isolated children |
| `src/agent_reliability/sdk/client.py`, `sdk/context.py` | Optional failure handoff, final health after terminal admission, once-only release in cleanup including start-abort |
| `pyproject.toml` | Optional `http = ["httpx>=0.28.1,<1"]`; core dependencies remain empty |
| `tests/unit/test_http_exporter.py` | Mocked HTTP/state/security/concurrency/lifecycle tests |
| `tests/contract/test_p28_http_protocol.py` | Shared data-only fixtures, digest/ack/URL/RA conformance and manifest integrity |
| `tests/fixtures/p28/*` | Four byte-identical vendored platform JSON files and SHA-256/version manifest |
| `tests/compat/test_public_api_1_1.py` | Update signature pin for the explicitly approved additive D13 indicator keyword; omitted-argument behavior remains compatible |
| `scripts/verify_p28_fixtures.py` | Hash/version checks and optional read-only platform drift comparison |
| `scripts/verify_p28_reference.mjs` | Dependency-free Node byte/digest and acknowledgement reference verification |
| `scripts/verify_release_artifacts.py` | Base HTTPX-absence check and isolated installed HTTP-extra mocked delivery check |
| `.github/workflows/ci.yml` | Include HTTP extra for static analysis/tests; verify fixture manifest |
| `docs/HTTP_EXPORTER.md`, `README.md` | Installation, configuration, recovery, security, lifecycle and integration instructions |
| Owner-decision record and this report | Approval provenance, focused L2 specification, compatibility qualification, acceptance evidence |

New public APIs live in `agent_reliability.adapters.http_event_sink`:
`HTTPEventSink`, `AsyncHTTPEventSink`, `DeliveryDisposition`,
`DeliveryRecordStatus`, `DeliveryStatusSnapshot`, `EventDeliveryRejected`,
`ExporterClosed`, `ConfigurationError`, `ConfigurationFailedError`.
The new capability is `ports.event_sink.HealthEvidenceSink`.
`RunHandle.record_evaluation_failure` gains optional keyword-only `indicator`.
Exporters expose emit/health/release, status, flush/close, auth/schema/deployment/
endpoint resume and context management. Async emit/health methods remain
synchronous; flush/close/resume are awaited.

The full endpoint is configured; schema version is fixed at 2, with no silent
downgrade or invented wire member. Organization derives from machine auth.
One exact agent identity binds one deployment; sibling deployments sharing
that triple remain indistinguishable as approved by PC-2 I-1. Each logical
record keeps one UUID-v4 event id and identical request body across retries.

## Self-validation commands and results

Commands below run from the SDK repository unless noted. Temporary environments
and build artifacts are outside the repository. Dependency installation used
sandbox escalation after network access failed; no system Python environment
was modified. Initial Windows `.venv` artifacts were unusable on this host,
so isolated macOS environments were created.

| Command | Result |
|---|---|
| `<tmp>/p28-sdk-py311/bin/python -m pytest -q` | 824 passed; Python 3.11.17 |
| `<tmp>/p28-sdk-py312/bin/python -m pytest -q` | 824 passed; Python 3.12.15 |
| `<tmp>/p28-sdk-validation/bin/python -m pytest -q` | 824 passed; Python 3.13.16 |
| `<tmp>/p28-sdk-validation/bin/ruff check .` | Passed |
| `<tmp>/p28-sdk-validation/bin/ruff format --check .` | Passed |
| `<tmp>/p28-sdk-validation/bin/mypy src` | Passed; strict, 46 source files |
| `<tmp>/p28-sdk-validation/bin/python scripts/verify_p28_fixtures.py --platform-root ../agent-reliability-platform` | Four hashes/versions passed; vendored bytes equal current platform files |
| `node scripts/verify_p28_reference.mjs` | 76 canonical byte/digest vectors and 74 acknowledgement vectors passed without either Python package |
| `<tmp>/p28-sdk-validation/bin/python -m build --no-isolation --outdir <tmp>/p28-sdk-artifacts` | Wheel and sdist built successfully with hatchling 1.32.4 |
| `<tmp>/p28-sdk-validation/bin/python scripts/verify_release_artifacts.py --wheel <tmp>/p28-sdk-artifacts/agent_reliability-1.2.1-py3-none-any.whl --sdist <tmp>/p28-sdk-artifacts/agent_reliability-1.2.1.tar.gz` | Metadata/contents, dependency-free base import/examples, sdist install, HTTP-extra mocked delivery, OTel extra/example and downstream strict mypy passed |

Environment setup used `uv --cache-dir <tmp>/p28-uv-cache venv` and
`uv ... pip install --python <environment>/bin/python -e '.[dev,otel-test,http]'`;
3.11/3.12 runtimes were installed with `uv ... python install 3.11 3.12
--install-dir <tmp>/p28-python --no-bin`. Python 3.13 came from Homebrew.
The first isolated `python -m build` failed to fetch hatchling in the sandbox;
escalated isolated builds passed, then the final build used cached dependencies
with `--no-isolation`. No failed check was counted as passing: development runs
found the slots declaration, fixture harness handling, legacy detail field,
README link and formatting issues, which were corrected before final checks. A further R5 regression check reproduced and
fixed deadline precedence for permanent non-acknowledgement responses; all
non-ACK outcomes now apply response gate effects and then deadline precedence.

One final Python 3.12 run had 823 passing tests and one failure in the
unchanged `tests/unit/adapters/test_adapters.py::TestUuidRunIdGenerator::test_ids_are_not_sequential`:
it asserts two random UUIDs must not end in `0` and `1`, which occurred for
`59df4c43-4e8e-4194-b560-4a4c85018e60` and
`b5f48b5b-a165-4a10-a948-4a6dd3627681`. The assertion has a 1/256 chance of
rejecting legitimate UUID-v4 output. It was not altered; the full rerun passed
824 tests. This intermittent baseline test remains a known limitation.

The focused suite contains 58 exporter tests. An earlier 43-test coverage run
measured 88% combined statement/branch coverage in the delivery core and 72%
in the transport adapter (84% combined); this is a diagnostic snapshot before
the final additional tests, not a final coverage claim or completeness proof.

## Contract and acceptance evidence

- I02: native sync/async transport and unchanged EventSink tested; no mandatory
  network dependency; installed HTTP extra and old public APIs validated.
- I03/I08: credential redaction/token bounds; single-flight timeout/late result;
  401/403 recovery and generation races; explicit TLS trust with ambient proxy/
  CA settings ignored; URL rejection before provider reads; redirect refusal;
  64 KiB body cap; malformed UTF-8/BOM/JSON/acknowledgement fixtures; PID guard.
- I04: transient exhaustion/idempotency/uncertainty, RA-b 429 gate and distinct
  throttle budget, compatibility pause with neutral responses, J2 legacy
  classification, strict timer equality, auth-refresh/403 overlap and L2
  threshold/resume tested. Workload/rate certification remains outside evidence.
- I05: queue records/bytes, closure reserve, threaded runs, no binding leaks,
  bounded tombstones, shutdown abandonment, discarded late responses and
  async HTTP cancellation tested.
- I06/I07: all 71 frozen v1 and five v2 canonical byte/digest vectors pass;
  all 74 acknowledgement vectors pass, including additional members;
  65 base loopback, 35 HTTPS and 23 Retry-After cases executed. A2-3 is applied
  separately from base loopback syntax; RA-b's ra-006 difference is explicit.
  All vendored platform fixtures remain unchanged. SDK capability failure/final
  health flow and both permanent 409 classifications are tested.
- I10/I11: API/security/recovery/installation documentation and artifact smoke
  checks provided. No frozen platform acceptance criteria were edited.
- I09/I12: live combined integration and separate independent review remain
  outstanding; this report does not mark all P28 milestone criteria passed.

## Known limitations and remaining integration gates

No unresolved owner selection blocks this SDK implementation. Initial settings
are engineering settings, not production SLOs. Pilot measurements and approved
E1/E2 production targets remain future evidence. Authenticated proxy credentials
are not accepted by this API; explicit proxies without userinfo and explicit CA
bundles are supported. No live malicious proxy/resolver or real TLS endpoint
certification is claimed; HTTP tests use mocks as requested.

A sync transport that blocks cannot be forcibly interrupted: close returns on
its deadline and up to two daemon workers finish/time out later. One hung
credential provider retains at most one daemon helper until it returns; it
cannot delay close/process exit. Async workers use cancellation and dedicated
provider result handoff to the owner loop. Users must close while their loop
is running. There is no durable spool or process-death delivery guarantee.

The remote fixture-drift CI job requires a published platform manifest/access
mechanism; only SDK hash CI and an executed local read-only drift check are
provided. Platform CI/files were not changed. GitHub Actions was not run.

Go: `command -v go` found no toolchain. Java: `java -version` reported no runtime.
Neither Go nor Java consumer conformance was executed. Node reference results
cover canonical bytes/digests and acknowledgements, not a full HTTP client or
published OpenAPI validation. No Go/Java/TypeScript SDK certification is claimed.

After PC-1/PC-2 are combined, run live machine auth/scope/organization/no-fallback
checks, tenant-hidden 404, deployment mismatch and racing replay classifications,
PostgreSQL durable 201/200/conflict/idempotency, v1/v2 digest parity, unsupported
schema and mixed-fleet pause/resume, 429 timing, lost acknowledgements/retries,
TLS/proxy credential isolation, concurrent-run FIFO, capacity and shutdown.
Release requires platform-first per-instance build evidence (E15/G1), production
validation as applicable and independent review. No shared TEST/production,
PC-1/PC-2 source, migrations, commits, pushes, PRs, deployments or releases
were changed or performed.


## Prompt 2 — independent review and remediation (2026-10-16)

One fresh independent comprehensive reviewer (`/root/p28_independent_review`)
confirmed two HIGH (R1/R2), four MEDIUM (R3–R6) and one LOW (R7) findings.
No BLOCKER was found. The reviewer-authored
[P28_SDK_EXPORTER_INDEPENDENT_REVIEW.md](P28_SDK_EXPORTER_INDEPENDENT_REVIEW.md)
records original source evidence and reproduction; the implementation author
does not edit or dictate that verdict. All six HIGH/MEDIUM corrections are implemented and independently verified
by the separate fresh context `/root/p28_targeted_verification`. This was
targeted verification, not a second comprehensive review.

[P28_SDK_EXPORTER_REMEDIATION_REPORT.md](P28_SDK_EXPORTER_REMEDIATION_REPORT.md)
maps each finding to its fix and regression evidence. Known status/Retry-After
survives body-read errors; native async maintenance expires and cancels hung
attempts; close joins cleanup within budget; native Windows stores supplement
compiled system CA paths without environment discovery; each binding admits
one immutable final-health record; both clients reject cookie storage.
Seventeen focused regression cases cover those findings and correction edges.
The independent reviewer observed all thirteen original reproductions failing
against the saved defective source. Neither platform fixtures nor wire/digest
rules changed.

R7 LOW diagnostic coverage is explicitly deferred, not reported fixed or
owner-approved. Missing/private structural counters do not change delivered
wire evidence, commitment, uncertainty or pause/retry decisions. The HTTP API
documentation now states this limit. L2 Closing-resume wording is clarified
under the recorded compatibility condition without changing state transitions.

### Current validation matrix

All commands executed from the SDK repository. Final source checks:

| Command | Result |
|---|---|
| `<tmp>/p28-sdk-py311/bin/python -m pytest -q` | 841 passed; Python 3.11.17 |
| `<tmp>/p28-sdk-py312/bin/python -m pytest -q` | 841 passed; Python 3.12.15 |
| `<tmp>/p28-sdk-validation/bin/python -m pytest -q` | 841 passed; Python 3.13.16 |
| `<tmp>/p28-sdk-validation/bin/python -m pytest tests/unit/test_http_exporter_review_regressions.py -q` | 17 passed after corrections; all seventeen fail against the original source; the original thirteen directly cover R1–R6 |
| `<tmp>/p28-sdk-validation/bin/ruff check .` | Passed |
| `<tmp>/p28-sdk-validation/bin/ruff format --check .` | Passed |
| `<tmp>/p28-sdk-validation/bin/mypy src` | Passed; 46 source files |
| `node scripts/verify_p28_reference.mjs` | 76 digest/byte and 74 acknowledgement vectors passed |
| `<tmp>/p28-sdk-validation/bin/python scripts/verify_p28_fixtures.py --platform-root ../agent-reliability-platform` | Four hashes/versions and byte-identical platform comparison passed |
| `<tmp>/p28-sdk-validation/bin/python -m build --no-isolation --outdir <tmp>/p28-sdk-review-artifacts` | Final corrected wheel/sdist built |
| `<tmp>/p28-sdk-validation/bin/python scripts/verify_release_artifacts.py --wheel <tmp>/p28-sdk-review-artifacts/agent_reliability-1.2.1-py3-none-any.whl --sdist <tmp>/p28-sdk-review-artifacts/agent_reliability-1.2.1.tar.gz` | Metadata/contents, base dependency isolation/examples, sdist, HTTP extra mocked delivery, OTel extra and downstream strict typing passed |
| `git diff --check` | Passed |

The complete suites include mocked HTTP, concurrency/lifecycle, digest/ack,
Retry-After and URL security tests. No baseline UUID flake occurred in these
Prompt 2 complete runs; the original invalid random-suffix assertion remains
unchanged and can still fail with probability 1/256. The historical observed
failure is recorded above and independently assessed in the review report.

### Remaining integration and release gates

Do not perform live integration in this task. The combined PC-1 + PC-2 tests
must cover:

1. Real machine credentials, `evidence:ingest`, failed-machine no fallback.
2. Tenant/organization isolation and tenant-hidden deployment 404.
3. Schema-v1/v2 ingestion and frozen canonical digests.
4. Exact deployment identity mismatch and both changed-identity replay race outcomes.
5. Durable PostgreSQL 201 and identical replay duplicate 200; event-only conflict.
6. Compatibility classification, mixed-fleet pauses and explicit recovery.
7. 429/Retry-After timing, missing/invalid guidance, sink-wide gating.
8. Lost acknowledgements, uncertainty and identical-id/body retries.
9. Real TLS verification, proxy/CA/redirect isolation and credential redaction.
10. Concurrent runs, per-run FIFO, queue/closure limits, autonomous expiry and shutdown cleanup.

Native Windows trust was exercised through store emulation, not an actual
Windows host. Go (`command -v go`) remains absent; Java (`java -version`)
reports no runtime. No Go/Java or live platform certification is claimed.
Remote fixture drift CI, GitHub Actions execution, platform-first per-instance
build evidence, production workload targets/measurements and release approval
remain gates. A zero/exhausted async close timeout may leave cleanup pending;
a later positive-budget close can join it before the owner loop exits.

Platform tracked diff and status were compared byte-for-byte to the Prompt 2
baseline and remain unchanged. No commits, pushes, PRs, merges, deployments,
releases or shared TEST/production changes were made. The pre-existing
`docs/ARCHITECTURE.md` and AGENTS.md/CLAUDE.md changes remain untouched.


### Final targeted verdict and correction closure

The separately authored
[P28_SDK_EXPORTER_TARGETED_VERIFICATION.md](P28_SDK_EXPORTER_TARGETED_VERIFICATION.md)
returns `P28_SDK_EXPORTER_VERIFIED_WITH_INTEGRATION_GATES`. R1–R6 are closed on
independent evidence. R7 remains an explicitly deferred LOW limitation; it is
not labeled fixed or owner accepted. The original comprehensive report keeps
its original-delivery findings and verdict rather than rewriting history.

The fresh verifier ran the current focused/exporter/protocol selection:
**351 passed**, comprising 17 review regressions, 58 original exporter tests
and 276 shared-fixture tests. With
`PYTHONPATH=<tmp>/p28-review-baseline/src`, all 17 review regressions
failed against original source as expected. The verifier notes that one
failed-admission marker test references the new attribute, so the duplicate/
corrected-health tests provide the direct defect proof for R5.

Targeted verification caught a remaining R3 branch in the initial correction:
a cleanup exception was not consumed. A new red/green regression and an
independent reproduction now show it is observed; only the constant
`transport_cleanup_failed` label is emitted, with raw transport exception
content kept out of event-loop/log diagnostics. A failing application log
handler is also isolated. The final complete 841-test suites and artifact
validation above were run after that correction.

No additional comprehensive review round was performed. There are no open
BLOCKER/HIGH/MEDIUM findings and no unresolved owner decision identified by
this review. This is integration readiness under the enumerated gates, not
end-to-end certification or deployment/release authorization.

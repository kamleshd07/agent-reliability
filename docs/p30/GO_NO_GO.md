# Session3 P30 initial slice — owner-review gate

## Scope and recommendation

**GO for owner review only when required CI passes on the final PR head.** Local implementation, independent
architecture/implementation/security review and independent validation are complete with no unresolved BLOCKER,
HIGH or actionable MEDIUM finding. Final exact-head checks, PR URL and head SHA are recorded on the PR rather
than guessed before the commit exists. This document does not approve merging or releasing the SDK.

This is an experimental initial LangChain Runnable vertical slice, not completion of every broader P30
capability. D14 OPEN; Phase B NO-GO. No platform/SDK-stable-wire or production infrastructure change.

| Delivered | Intentionally deferred |
|---|---|
| Opt-in invoke/ainvoke wrapper; enable/disable/close | Streams, batches and graph/checkpoint-specific semantics |
| Existing SDK root lifecycle/identity and nested context | Extra frameworks and automatic semantic evaluation |
| Normalized bounded run/step/tool/model events | Raw content capture and arbitrary metadata |
| Approved identifiers and explicit token availability | Monetary cost/pricing or inferred token estimates |
| Local details; existing explicit outcome/lifecycle export unchanged | P18/P20 remote detail producer, state/memory capture |
| Bounded diagnostics, health degradation and honest overhead report | Hosted/customer capacity or production latency claims |

## Actual verification

Author full SDK runs: Python 3.11.17, 3.12.15 and 3.13.16 each **1,802 passed, 1 skipped**, 96% coverage.
The skip is the pre-existing P29 external platform-model test requiring explicit environment configuration;
it is not an instrumentation skip or a pass. Final focused instrumentation/artifact-guard suite: **103 passed**.
Ruff check/format (303 files) and mypy (70 source files) passed. Independent Node contract reference:
76 canonical and 74 acknowledgement vectors passed. Four published fixture hashes match current platform main.

Independent implementation reviewer: full Python 3.11 suite **1,798 passed / 1 skip** before four final boundary
cases, then all four additions passed separately. Independent validator: frozen full Python 3.13 suite
**1,802 passed / 1 skip**; Python 3.12 full **1,795 passed / 1 skip** before the final additions, which were
separately exercised. Complete artifact verification and clean imports/installs passed. Security reviewer:
72 instrumentation/attack cases and 377 exporter/protocol regressions passed. Counts overlap; do not sum them.

Author wheel/sdist and complete artifact verification passed: core no-extra, sdist quickstart, HTTP mocked delivery,
selected-extra offline sync/async tools/model/explicit evaluator, OTel example and downstream strict mypy.
Four actual emitted v2 envelopes validate against current platform request/domain models and match all four
canonical digests;200current-platform unit schema/API tests passed without a DB or service. This does not
constitute a fresh PostgreSQL E2E or new Session2 operational-run verification.

## Findings and fixes

- AR1–3 MEDIUM design findings: nested callback ownership/configuration, partial-evidence health, callback
  containment/chat fallback. Design independently rechecked before implementation.
- S1 MEDIUM: wrong terminal kinds, conflicting duplicate starts and starts under closed parents could fabricate
  complete capture. Fixed with kind/identity/parent checks, regression tests and independent original/expanded attacks.
- V1 MEDIUM: internal report files entered sdist because the intended exclusion was absent. Added directory
  exclusion and planted guard test; independent rebuilt artifacts and full verifier passed.
- IR1 MEDIUM: new README relative guide link violated package-index-safe contract. Fixed to absolute URL;
  independent unchanged contract and final full suite passed.
- V2 LOW: lint/format issues fixed and independently checked.

Reports under reviews/ are written by their independent reviewers and not edited by the author/coordinator.

## Performance and remaining limitations

Measured local warm p50 overhead:161.32% trivial Runnable,24.08%20-tool call,70.52%16-call async batch,
23.56%1200-tool truncated trace. See PERFORMANCE.md and raw JSON for absolute numbers, units, allocator peaks,
sample counts and caveats. No negligible-overhead, throughput ceiling, SLO or capacity claim.

Customer-supplied logical aliases can still contain secrets despite grammar; third-party tracing and trusted SDK
custom sinks/diagnostics keep their own contracts. Callback/lock scheduling has no hard wall-clock deadline;
hidden provider retries cannot be counted; process death can lose terminal facts; caller-held snapshots are not
bounded by the wrapper. Missing token usage remains unknown. Local details have no remote P18/P20 producer.

## Next owner decisions and rollback

Approve/reject merge of the focused experimental slice after final CI. Any release/version bump/PyPI publication
is a separate owner decision. Broader framework/stream/state/memory/P18/P20 producer work needs its own reviewed
scope and language-neutral wire contract where applicable. No Phase B or production authorization is implied.

Rollback: disable/close the wrapper or call the original Runnable; no global patches, database migrations,
provider configuration or platform rollback is required. Uninstall the optional extra if no longer needed.
Disable/close does not cancel in-flight application work. Retained snapshots already held by the caller remain
caller-owned. Core stable API and already published1.3.0 artifacts remain unchanged.

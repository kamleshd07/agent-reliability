# Session3 initial automatic instrumentation — implementation evidence

Branch: session3/p30-automatic-instrumentation. Worktree: gentlity-s3-sdk. Base: SDK main
b65374d0b2aaed2d06c563f738ca840e840956b9. Final PR/head and exact-head CI appear on the PR and final external
verification record. No merge, tag, publication, deployment or platform edit is authorized/performed.

## Components

- `experimental/instrumentation/model.py`: immutable closed-schema events/traces, TokenUsage, resource bounds.
- `collector.py`: scoped UUID-to-span normalization, reserved terminal slots, ordering, kind/parent/duplicate
  integrity, synthetic incomplete closure and saturated diagnostics; no framework/payload/export dependency.
- `controller.py`: explicit lifecycle/admission/sampling/retention, existing SDK context reuse, sync/async wrapper,
  unchanged returned objects/application exceptions, fixed failure classification, PARTIAL_EVIDENCE before SDK exit.
- `adapters/langchain_instrumentation.py`: exactly pinned optional public hooks; copied caller/inherited configuration,
  nested ownership, explicit inline chat callback, token numeric allowlist, callback error containment and safe tool aliases.
- Public guide, offline fake-model/tool/explicit-evaluation example, bounded performance harness, fixture checks,
  package/no-extra/selected-extra probes and CI extra coverage.

## Verification and evidence

GO_NO_GO.md contains actual final counts and exact limitations; TRACEABILITY.md maps requirements to tests.
External author logs/JSON/JUnit and original-work status inventories are retained in the Session3 evidence directory.
PERFORMANCE_DATA.json is the actual recorded microbenchmark output, not estimates. No paid model or external
tracing backend was contacted. Framework/packaging dependencies were downloaded through normal test installation.

The unchanged SDK baseline passed 1,733 tests / 1 skip. Final suites passed 1,802 tests / 1 skip on all three
supported Python versions, with 96% coverage.
Failed intermediate logs are preserved: HTTP test fixture initially omitted required environment and then read
payload kind at the wrong envelope level; fixed test setup, not exporter behavior. Independent findings and
initial reproductions are preserved in reviewer-owned reports. No test was weakened to produce GO.

## Compatibility and isolation

No stable SDK module or HTTP implementation code is changed. Existing EventSink union/evaluator semantics,
indicator authorization, v1 golden digests and v2 producer identity are unchanged. No source release version bump.
Core dependency list remains empty. Detailed traces do not use a second export path. No proprietary platform
change; external current-main archive validates request models/digests and200unit schema/API cases only.
See COMPATIBILITY.md and PRESERVATION.md. No existing dirty files were overwritten or deleted.

## Review gates

Architecture: AR1–3closed before code. Implementation: IR1closed by independent contract/full-suite recheck.
Security: S1closed by original plus expanded adversarial execution. Validation: V1/V2closed independently.
No unresolved BLOCKER/HIGH/actionableMEDIUM. Final CI is required; PR remains for owner review only.
D14 OPEN; PhaseB NO-GO.

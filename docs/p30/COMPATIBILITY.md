# Compatibility evidence and boundaries

Baseline SDK origin/main b65374d0b2aaed2d06c563f738ca840e840956b9 (released 1.3.0); platform origin/main
805b9c718f370aea784143359a7d6e8b62ea81b2 (PR62/64 merged). Original dirty checkouts are unchanged.
No platform, stable SDK run/evaluator/event union or existing HTTP implementation file is modified.
No release version bump or package publication is authorized by this work.

## Verified

- Full supported-Python SDK matrix including existing stable API and exporter regressions; exact final counts in GO_NO_GO.
- Published data-only contract fixture manifest unchanged and byte-compared against an archive of current platform main:4 hashes match.
- Independent Node reference:76 canonical byte/digest vectors and74 acknowledgement vectors pass.
- Actual instrumented-run exporter exercised with MockTransport: existing schema2 lifecycle, explicit evaluator
  result/provenance and partial measurement health only; no execution detail payload/export path added.
- Four emitted envelopes validate against current-platform EvidenceEnvelopeV2 and its domain conversion; all
  four platform canonical digests equal SDK digests. This uses an isolated read-only source archive, no service,
  database connection, shared resource or platform edit.
- Current platform unit schema/API subset:200 passed, one existing Starlette warning, no database or service. This is not a new deployed E2E claim.
- Wheel/core clean install has no runtime dependencies; neutral imports work without LangChain, HTTPX or OTel.
  Selected-extra wheel example runs sync/async tools/models and explicit evaluator integration. Full artifact
  verification includes HTTP mock delivery, OTel example and downstream strict typing.

Existing HTTP identity policy is stricter than local logical aliases: agent_id/environment are lower-case
machine keys of at most63 characters; version is bounded120. Configure the wrapper's identity to exactly match
the existing sink's expected agent/deployment binding. Local aliases do not widen that wire contract. No tenant,
deployment or provider identity is inferred from framework metadata.

## Explicitly not verified or not implemented

No hosted deployment, real credential/identity provider, fresh PostgreSQL round trip or Session2 operational-loop
execution in this SDK-only slice. Existing platform CI/merged implementation and unchanged envelope contracts
are baseline evidence, not new production validation. The pre-existing P29 platform-model test is skipped when
its explicit external configuration is absent; it is not presented as passing.

P18/P20 detail transport remains deferred and cannot be inferred from local trace capture. No streams/batch,
full LangGraph semantics, second framework, semantic auto-evaluation, state/memory or pricing support. Unsupported
framework versions fail at setup; upgrade requires new pinned conformance tests and review. Existing customer
third-party tracing and trusted custom sinks keep their own privacy/behavior contracts.

## Supported LangChain range (exporter slice, 2026-11-08)

The `langchain` extra is `langchain-core>=1.0,<2` (previously `==1.6.13`). The adapter, wrapper and exporter suites
(`tests/integration/test_langchain_instrumentation.py`, `test_langchain_execution_export.py`, `tests/unit/instrumentation`) were run
on a fresh Python 3.13 environment per release: **1.0.0, 1.2.31, 1.6.13, 1.7.6: 104 passed each**. With `langchain` 1.4.9 and
`langgraph` 1.2.20 added, a real `create_agent` agent test and the documented example pass (106 passed, 2 skipped there because the
skips are langchain-less guards). `langchain-core` 0.3.86 is refused at setup. Type-checking the adapter with the extra installed:
`mypy src` reports no issues, which resolves the earlier "7 optional-extra mypy findings" (they were missing-import errors only).
Releases between the tested ones are not individually tested. A LangChain callback-semantics change in a future 1.x release would
surface as failing tests in this matrix; there is no automatic CI matrix over every release.


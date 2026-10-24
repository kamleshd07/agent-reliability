# Independent P30 architecture review

Reviewer: fresh Session 3 architecture reviewer. Date: 2026-10-22.
Scope: owner Session 3 instruction, repository AGENTS.md, proposed `docs/p30/ARCHITECTURE.md`, existing SDK lifecycle, context, event union, measurement health and diagnostics, current approved roadmap P30 scope, installed pinned LangChain Core callback implementation. No implementation was authorized by this review before findings were addressed. No platform or implementation files edited.

## Assessment

The additive experimental wrapper, explicit enable/disable lifecycle, reuse of SDK sessions, optional LangChain Core dependency, local bounded normalized traces and unchanged exporter are an appropriate first vertical slice. Local detailed traces are a deliberate initial scope limitation, not completion of the full roadmap's P18/P20 producer outcome. The report and quickstart must say detailed steps/tools/tokens do not yet appear in Gentlity. Existing SDK root lifecycle and explicit evaluations may still use the existing exporter. No wire or stable API change is needed for this slice.

LangChain Core public Runnable callbacks support a credible local deterministic test strategy without a hosted service. Exact initial dependency pinning is conservative and acceptable; support for other versions must not be implied. Grammar-restricted identifiers remain customer-approved aliases, not a guarantee against secret content. Existing customer-controlled sinks and external framework tracing remain independent trusted boundaries.

## Findings requiring design clarification

### AR-1 — MEDIUM — Scope inherited callbacks and preserve caller configuration

Nested wrappers inherit callbacks; naïvely appending handlers can make an inner callback appear under multiple SDK run identities and inflate counts. Overwriting a caller-supplied `run_id`, mutating a shared callback manager, or losing user callbacks changes application behavior.

Required correction: document public pinned configuration merge/copy behavior, preserve caller callbacks and run UUID, and establish one per-invocation collector ownership policy. The author's proposed removal of inherited **own adapter handlers only** on a copied manager before adding the inner handler is acceptable provided external callbacks/parent propagation are preserved. Test actual nested wrappers, shared caller configuration under concurrent invocations, existing callback managers and lists, and correct per-run model/tool counts. Invalid unsupported configuration must not trigger a second application invocation.

### AR-2 — MEDIUM — Incomplete capture and measurement health

The proposal marks local traces incomplete but initially does not state whether existing run health becomes degraded after collector failure, rejected child spans, truncation or missing lifecycle events. Reporting healthy evidence after failed automatic capture is misleading.

Required correction: monotonically mark existing run `PARTIAL_EVIDENCE` before session exit when an admitted capture becomes incomplete, or explicitly define and justify separate local/HTTP health scopes. The existing reason is already supported; no new wire literal is needed. Intentional sampling/admission bypass needs its own documented semantics, not fabricated PASS or fabricated runs. Test emitted health and local completeness after floods, callback failures and missing terminals.

### AR-3 — MEDIUM — Callback privacy requires containment before framework logging

Installed `langchain_core/callbacks/manager.py::handle_event` logs `repr(e)` for escaping callback exceptions even when `raise_error=False`. Its chat-model `NotImplementedError` fallback formats messages with `get_buffer_string`; merely ignoring a default base callback is insufficient for the stated no-content-inspection boundary.

Required correction: explicit chat-start override; no raw callback exception may escape adapter-owned callback entry points. Prefer synchronous `BaseCallbackHandler` with `run_inline=True` for the short bounded collector path in both sync and async execution. Keep framework-provided payloads transient and do not format them. Tests should include hostile payload/exception sentinels, forced collector failures, captured framework logs and unchanged application exception identity. Document that customer-enabled LangSmith/other callbacks are not disabled or privacy-controlled by this integration.

## Other implementation acceptance conditions

- Exception sanitization at SDK session exit must preserve cancelled classification as well as re-raising the original application exception. Existing `RunSession` otherwise exports exception class names and forwards them to an optional context bridge.
- Callback UUID deduplication, reserved terminal capacity and bounded orphan handling must remain bounded after saturation; no unbounded tombstone/pending-parent table.
- Duplicate callback signals and observed framework retry signals are not provider HTTP attempts. Tests must exercise the real pinned retry wrapper, not only direct callbacks.
- Token fields must be actual bounded integers (not booleans); ambiguous usage stays unknown. Model latency includes framework callback overhead, not a provider-network guarantee.
- Explicit evaluation should be demonstrated through the existing active `RunHandle`, with UNKNOWN preserved and no automatically generated evaluator provenance.
- Disable/close races must not alter work already running; closed wrappers must not repopulate retained traces.
- Performance and allocation measurements are required evidence, not a pre-implementation negligible-overhead assertion.
- The supported surface is invoke/ainvoke; streams, batches, graphs, process termination flush and arbitrary-thread context propagation remain clearly excluded.

## Review gate

No BLOCKER or HIGH design finding. AR-1 through AR-3 are actionable MEDIUM clarifications to close in the architecture before substantial implementation. Independent implementation, security and separately executed validation remain required. This review does not approve merge, release, platform contract changes or hosted readiness. D14 OPEN; Phase B NO-GO.

## Evidence

- `src/agent_reliability/sdk/client.py`: context-owned lifecycle, exception classification, existing health delivery.
- `src/agent_reliability/sdk/context.py`: explicit recording and active run context.
- `src/agent_reliability/domain/measurement_health.py`: existing PARTIAL_EVIDENCE reason.
- `src/agent_reliability/ports/events.py`: unchanged four-event stable union.
- `src/agent_reliability/sdk/diagnostics.py`: existing diagnostic trust boundary.
- `pyproject.toml`: zero mandatory runtime dependencies.
- Installed pinned dependency under `<workspace>/gentlity-s3-evidence/venv311/lib/python3.11/site-packages/langchain_core/callbacks/{base,manager}.py` inspected directly. Official reference URLs in the architecture could not be rendered by the web tool (markdown content type); this assessment relies on the installed pinned implementation rather than assuming those pages were inspected successfully.

## Independent design re-check

The author updated the design during this review. Independently re-read the updated architecture:

- AR-1 CLOSED at design level: copied configuration, preserved caller callbacks/identity and scoped inherited adapter filtering are now explicit in API/package boundaries; concrete nested/config tests remain implementation acceptance gates.
- AR-2 CLOSED at design level: owning-context PARTIAL_EVIDENCE marking before session exit now covers callback failures, truncation, orphan events and unfinished spans. Intentional sampling and admission bypass are documented as uninstrumented calls; absent token usage remains unknown rather than failed evaluation.
- AR-3 CLOSED at design level: explicit chat start, inline callbacks, internal exception containment and third-party tracing boundary are stated.

**Architecture gate: GO to implement this additive experimental vertical slice.** No unresolved actionable design finding. This is not implementation validation, owner merge approval, full P30 roadmap completion or a release recommendation. The implementation and security reviews must verify the concrete tests and failure behavior above rather than treating written design as evidence of working code.

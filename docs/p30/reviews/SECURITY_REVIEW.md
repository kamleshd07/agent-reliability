# P30 independent adversarial security review

Reviewer: fresh independent security context. Date: 2026-10-22.

Scope: owner Session 3 instruction, repository AGENTS.md, architecture and independent architecture review, experimental instrumentation model/collector/controller, optional LangChain callback adapter, existing root lifecycle and HTTP export boundaries. This reviewer changes only this report in the SDK worktree. No platform, SDK implementation, resources, release or hosted environment changes.

## Initial finding

**S-1 — MEDIUM — Malformed lifecycle callbacks can be reported as complete evidence.**

Initial independently executed reproduction: start a tool span at UUID X, send `on_llm_end(None, run_id=X)`, then finish the collector. The tool is marked completed and `ExecutionTrace.complete` is true. The handler/collector do not validate the terminal callback kind against the stored start kind. Separately, close a chain span and then start/complete its child tool; the collector accepts a child of an already closed parent and again reports complete evidence. A conflicting duplicate start reusing one UUID for different kinds is likewise silently treated as a harmless duplicate.

Impact: malformed or incompatible framework signals can appear complete and avoid PARTIAL_EVIDENCE marking. This does not fabricate semantic evaluation results or establish a cross-tenant access path, but violates the promised fail-visible incomplete-capture semantics.

Required correction: validate kind and parent ownership consistently, distinguish a conflicting duplicate from an exact duplicate, and mark invalid sequences partial without changing the application invocation, result or exception. Add regressions at the callback boundary, not only collector internals. Recheck required after author remediation.

## Independently executed initial checks

External reviewer-owned fixtures and evidence: `/tmp/gentlity-s3-security-review/`.

- `probe.py`: reproduced wrong-kind terminal and child-after-parent-close complete traces.
- `test_adversarial.py`, initial nine-case run: **7 passed, 2 failed**, with both failures reproducing S-1. XML `adversarial-initial.xml`.
- Passing attacks: poisoned raw payload objects whose `str`/`repr` raise; malformed and oversized callback identities; 20,000 tool callbacks bounded to 12 events with max_spans=5; unknown cross-collector parent IDs; forced callback exception containment without secret logging; 32 concurrent threaded invocations sharing caller configuration; unapproved sensitive tool identifiers.
- Repository instrumentation tests independently executed during author development: **59 passed, 1 failed**. The failing newly added HTTP regression indexed a nonexistent `kind` member; this was reported to the author rather than treated as an exporter defect. XML `instrumentation-initial.xml`.
- Subsequent expanded tests overlapped author changes and observed transient callback/collector signature mismatches. Those results are retained as `adversarial-initial-expanded.xml` and are not final verification evidence.

## Reviewed boundaries and residual limitations

Identifier grammar is bounded ASCII, not secret detection. Customers must configure non-sensitive agent/name/version/environment/provider/model aliases and explicitly approve any emitted tool names. Framework-supplied model identifiers, exception class names/messages, arbitrary metadata and raw inputs/outputs are not copied into normalized trace events. The optional adapter's explicit chat-start override avoids the framework's message-to-prompt fallback; callback exceptions are contained before framework logging.

No new detailed-event exporter or wire schema is introduced. Detailed tool/model/token traces are local; existing lifecycle and explicit evaluations continue through the existing SDK exporter and indicator policy. Existing HTTP exporter source/policy files are unchanged in the reviewed diff. UNKNOWN does not become PASS and execution completion is not proof of outcome correctness.

LangSmith, user callbacks, custom SDK sinks, framework internals and application code remain separate trust boundaries. This adapter does not disable existing third-party tracing or attest that framework callbacks are truthful. Process termination may lose pending evidence. Python lock scheduling and trusted existing synchronous SDK sinks have no hard latency guarantee. These limitations must remain visible in customer documentation.

## Initial gate (superseded by final recheck below)

**Pending remediation and independently executed final recheck at initial review.** No BLOCKER or HIGH finding identified in the reviewed scope. S-1 remains actionable MEDIUM until corrected and verified. This review does not authorize merge, release, hosted readiness or production use. D14 remains OPEN; Phase B remains NO-GO.

## Final independent remediation recheck

**S-1 CLOSED.** After the author signaled stable source, this reviewer reran the original and expanded external adversarial tests unchanged. All 11 passed. The callback adapter now supplies the expected span kind at every terminal hook; the collector rejects a wrong-kind terminal, rejects starts whose captured parent is already closed, and distinguishes conflicting duplicate kind/framework-parent/approved-component from an exact duplicate. These failures affect partial-capture diagnostics, allowing the controller's existing PARTIAL_EVIDENCE propagation rather than claiming complete capture. No application retries or raw logging were introduced by the fix.

Final independently executed commands used the prepared Python 3.11 environment at `gentlity-s3-evidence/venv311` with the current worktree's `src` on PYTHONPATH. External reviewer tests and all result XMLs have been preserved at `<workspace>/gentlity-s3-evidence/security-review/`.

- Reviewer attacks plus repository instrumentation suites: **72 passed, 0 skipped, 0 failed** (`final-security.xml`): 11 independent adversarial cases plus 61 repository cases.
- Existing indicator-policy, exporter review and release regressions, language-neutral HTTP protocol and experimental API compatibility: **377 passed, 0 skipped, 0 failed** (`exporter-policy.xml`). These use the repository's local mock/fake fixtures; no paid model or hosted ingestion calls were made.
- Inspected implementation changes: exporter, SDK lifecycle and SDK context files remain unchanged. Core dependency isolation and full Python-version validation are separate independent-validator gates; this review does not substitute its Python 3.11 result for those checks.

**Final security recommendation: GO for owner review of the additive experimental local-capture vertical slice.** No unresolved BLOCKER, HIGH or actionable MEDIUM security finding in this scope. The documented trust boundaries and deferred detailed-event transport remain limitations, not guarantees of hosted readiness. Owner approval, all remaining implementation/validation/CI gates and the PR review are still required before merge. No release or production approval is implied. D14 OPEN; Phase B NO-GO.

Reviewed instrumentation source digest: `be469efedee43aba471211d8abb36f97f8885499fa816b094f0e8d30c6c9f8ff` (SHA-256 over sorted neutral module paths followed by adapter path, each encoded as path + NUL + file bytes + NUL). Subsequent implementation changes require targeted recheck.

## Pre-PR final source and public-guide recheck

Independently reread the final controller, callback ownership/terminal hooks and collector S-1 defenses after formatting changes. The final identity dictionary literal preserves the same validated fields; no weakening of the reviewed privacy or lifecycle checks was found. Final runtime-source digest using the same method is `29dda2dd2dba8e91790d52e971e7675b5f228a6605a86e4fc87afb45342601e2`.

Reran all 11 unchanged reviewer attacks plus repository instrumentation suites against that source: **72 passed, 0 skipped, 0 failed**, recorded in `gentlity-s3-evidence/security-review/final-pr-security.xml`. S-1 remains CLOSED.

Reviewed `docs/AUTOMATIC_INSTRUMENTATION.md`: its no-raw-content statement is expressly scoped to this capture path; customer callbacks/sinks and external tracing are separate boundaries; configured aliases are not guaranteed secret-free; provider/model labels are configuration assertions; execution completion is distinct from explicitly evaluated outcomes; detailed traces remain local; UNKNOWN and partial-health semantics remain explicit. Unsupported surfaces, bounded capture, snapshots retained by customers, process-death loss and absence of hard callback wall-clock guarantees are disclosed. No new unsupported privacy or production-readiness claim found.

Internal review/architecture files under `docs/p30` are excluded through the build configuration. The separate artifact validator owns execution and whole-artifact leakage verification; this security recheck does not replace that evidence or claim it independently executed those artifact tests. Likewise, reported platform model/digest compatibility and Python 3.12/3.13 runs belong to their respective validators rather than these Python 3.11 security results.

**Final recommendation unchanged: GO for owner review of the experimental local-capture scope, subject to the remaining CI/PR gates.** No new security findings; no merge/release/hosted approval. D14 OPEN; Phase B NO-GO.

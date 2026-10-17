# Gentlity repository instructions

## Permanent language-neutral HTTP contract rule

Gentlity's public HTTP ingestion and control-plane contracts MUST remain language-neutral. Python may implement a contract, but Python dataclasses, Pydantic models, exception names, enum internals, serializer defaults, or SDK behavior MUST NOT define the protocol.

For every public HTTP contract:

- Treat the published OpenAPI document and referenced JSON Schemas, together with the normative contract documentation, as the source of truth. Specify fields, JSON types, required/optional/null behavior, bounds, formats, enum wire literals, and validation independently of source code.
- Specify canonical JSON and hashing rules explicitly, including Unicode handling, numeric representation, timestamps, UUIDs, null versus absent members, and object-member ordering. Preserve schema-v1 canonical digest bytes and golden digests across upgrades.
- Use stable machine-readable error codes and documented HTTP status semantics. Do not expose language-specific exception or enum implementation details as protocol requirements.
- Use standard HTTP authentication and authorization. Document idempotency, retries, rate limits, `Retry-After`, timeouts, wire versions, compatibility, and deprecation behavior.
- Maintain data-only, language-independent positive, negative, boundary, request/response, and digest fixtures reusable by Python, Go, Java, and TypeScript implementations.
- Require bidirectional conformance: the Python SDK and platform must pass the published contract fixtures, but neither implementation may redefine the contract through its current behavior.

Any intentional wire-contract change requires an explicit version/compatibility decision and corresponding schema, documentation, fixture, and conformance-test updates. Do not implement or approve a public HTTP design that requires consumers to inspect Python source.

## Two-prompt execution policy

Apply this workflow to every new Gentlity milestone, epic, implementation package and development stage. Claude Code and Codex follow the same workflow. The number of user prompts should normally be two, even if the agents perform several internal review-and-fix iterations.

### Prompt 1 - complete the original requirement

The implementation agent MUST:

1. Read the requirement, roadmap, relevant ADRs and existing code.
2. Resolve ambiguities and document assumptions; escalate decisions that require owner approval.
3. Produce the required design and architecture.
4. Implement the approved scope when implementation is authorized.
5. Write unit, integration, negative, security and compatibility tests appropriate to the change.
6. Update documentation and acceptance-criteria traceability.
7. Run available validation and test suites.
8. Perform an internal self-check and fix identified defects.
9. Produce an evidence-based completion report.

Do not stop after producing a design if implementation is authorized and all prerequisite gates are satisfied. Do not bypass required human approvals.

### Prompt 2 - independent review, remediation and final verification

The coordinator MUST:

1. Launch a separate reviewer agent with an independent execution context.
2. Review the entire delivered scope against original requirements, architecture, security, compatibility and acceptance criteria.
3. Record all findings with severity, evidence and reproduction steps.
4. Return findings to the implementation agent.
5. Fix every actionable finding, including regression tests.
6. Ask the independent reviewer to re-check the corrections.
7. Repeat internal review/fix/re-verification within this same prompt until: all BLOCKER and HIGH findings are closed; all actionable MEDIUM findings are closed; LOW findings are fixed or explicitly dispositioned; acceptance criteria and required tests pass; and no material regressions remain.
8. Produce a final review report containing evidence, unresolved risks and the exact release/approval gate.

Do not manufacture a clean verdict or impose an artificial limit on internal review iterations. The reviewer's report is written by the reviewer; the author and the coordinator never edit it or dictate its verdict, and an author never reviews their own corrections.

If a finding requires a human policy decision, an unavailable external dependency, or an inaccessible test environment, stop at that gate and report it rather than guessing.

### Permanent engineering rules

- Python-first backend and SDK; TypeScript for the UI.
- Language-neutral HTTP contracts and shared conformance fixtures (see the language-neutral HTTP contract rule above).
- Preserve tenant isolation, security, backward compatibility and evidence integrity.
- No unsupported production-readiness claims.
- No commits, pushes, PRs, merges, deployments or releases without explicit authorization.
- Do not infer human approval.
- Keep review findings and corrective changes auditable.

### Completion standard

A stage is complete only when its acceptance criteria are satisfied, required reviews are resolved, and all mandatory approval gates have passed.

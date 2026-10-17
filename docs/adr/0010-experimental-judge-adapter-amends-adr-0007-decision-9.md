# ADR-0010: Experimental LLM-judge adapter namespace (amends ADR-0007 decision 9)

## Status

Accepted - gate G-C of the P29 V1 package, **owner-approved on 2026-10-16 by
explicit owner instruction** (the owner's own message of that date approved
"G-C: the proposed SDK ADR amendment to ADR-0007 decision 9, within the
existing documented P29 V1 scope"). The approval is **unsigned**: the approver's
identity and the approval time are **not recorded**, and none is inferred. It is
not a cryptographic signature, not a security approval, and not a release
authorization.

- **Number provisional.** The owner did not assign an ADR number. `0010` is the
  next free sequential number in this directory and may be renumbered by the
  owner.
- **Scope of the approval.** Only what is stated in the Decision section below,
  i.e. the documented P29 V1 scope (design package `P29-DESIGN-001`: option A for
  P29-D01 to P29-D13, P29-D09 conditional on SG-1 to SG-6). Anything outside it
  (managed judge, P28 wire/schema/platform changes, P28 contract revision 16,
  P28-D14, ADR-0023 Appendix A.2, shared-environment use, publication, release)
  is **not** covered. The independent review (P29-S12-AC02) is still outstanding.
- This ADR is the amendment drafted by stage S00. The earlier draft wording
  "states it is Proposed" (P29-S00-AC01) was written before the owner's G-C
  approval and is superseded by this status line; the original ADR-0007 text is
  not edited (see below).

References: [ADR-0004](0004-instrumentation-failure-isolation.md),
[ADR-0005](0005-instrumentation-initialization-degraded-mode.md),
[ADR-0007](0007-evaluator-architecture-and-provenance-semantics.md),
[ADR-0009](0009-measurement-health-and-policy-boundary.md); the P29 design package
(`P29-DESIGN-001`: native evaluation architecture, evaluation contract,
implementation plan, security/privacy review, calibration and test strategy,
owner decisions 001) in the platform repository `docs/roadmap/P29/`.

## Context

ADR-0007 decision 9 states: "Include only equality and typed predicate
evaluators. No global registry, plugin discovery, remote calls, timeout
machinery, or LLM adapter is added." That was correct for M4: the M4 evaluators
are deterministic, local and in-process, and judge semantics (privacy,
non-determinism, remote failure, provenance) were deliberately deferred
(`docs/ROADMAP.md` M4: "LLM-as-judge remains deliberately deferred until a later
adapter milestone can define its privacy, nondeterminism, remote-failure, and
provenance semantics").

P29 is that adapter milestone. Semantic dimensions (answer correctness,
groundedness, instruction adherence, safety policy, task-completion evidence)
cannot be evaluated by equality or typed predicates. A model-backed evaluator
needs (a) an adapter that talks to a customer-supplied model and (b) timeout
machinery around that remote call. Both are excluded by decision 9 as written, so
decision 9 must be amended before implementation (design package, architecture
section 4.3).

The remaining ADR-0007 decisions hold and are relied on: evaluator identity is
caller-declared and never hashed (3), `EvaluatorRunner` catches `Exception` only
and reduces failures to a value (5, 6), `UNKNOWN` means a completed judgment
lacked evidence and an execution failure is never `PASS`, `FAIL` or `UNKNOWN`
(7), input is never retained, copied, rendered or placed in events (10).
ADR-0004 (failure isolation, `Exception` versus `BaseException`; its principle
carried forward by ADR-0005) and ADR-0009 (measurement health and the
application policy boundary) govern failure isolation and health and are not
changed.

## Decision

Decision 9 of ADR-0007 is amended, for the purposes below only, as follows. All
other decisions of ADR-0007 (1 to 8, 10, 11) are unchanged.

1. **Experimental adapter namespace.** A model-backed judge evaluator lives in
   a new, explicitly **Experimental** namespace,
   `agent_reliability.experimental.judge` (P29-D01 option A). It follows the
   Experimental policy in `docs/VERSIONING.md`: it may change in a minor
   release with prominent release notes, and it is promoted to a stable
   namespace only by a later documented decision after pilot calibration. It is
   not part of the stable inventory of `docs/GA_CONTRACT.md`.
2. **LLM adapter allowed, inside that namespace only.** The namespace may
   contain a rubric/value-type layer, a provider-neutral provider protocol, and
   an `LLMJudge` (async) / `SyncLLMJudge` (sync) evaluator that call a
   **customer-supplied** provider object. The SDK ships no default provider, no
   vendor client, no credential or environment access and no network client in
   the core namespace.
3. **Timeout machinery allowed, inside that namespace only.** The judge may
   enforce a per-attempt timeout, a total evaluation deadline, bounded retries
   and a token/cost budget around the provider call. No timeout machinery is
   added to `EvaluatorRunner`, `RunHandle`, the deterministic evaluators or any
   existing module.
4. **`EvaluatorRunner` is unchanged.** The judge satisfies the existing
   `AsyncEvaluator`/`SyncEvaluator` structural protocols and runs through the
   existing runner. Any judge failure is an exception (a `JudgeError` subclass)
   that the runner already reduces to `EvaluationExecutionFailure(stage=EVALUATION,
   exception_type=<class name>)`. `BaseException` (cancellation, interrupts)
   still propagates (ADR-0004, ADR-0007 decision 6).
5. **Provenance.** A model-backed judge always declares `deterministic=False`.
   Rubric, model label, prompt-template id and decision policy travel only in the
   existing `EvaluatorIdentity` fields (name, version, `configuration_id`;
   P29-D02 option A) as caller-declared, human-readable labels in the
   `[A-Za-z0-9._-]` grammar that every layer accepts. The library does not hash
   configuration into identity (decision 3 holds); a local rubric fingerprint may
   exist but is never exported.
6. **No registry, plugin discovery or import-by-string.** Unchanged from
   decision 9: no global registry, no entry points. Rubrics are data and
   providers are constructed explicitly by the application.
7. **No new wire.** The judge adds no HTTP endpoint, payload kind, field, enum
   literal, schema version, error code or digest input (P29-CON-01). It only
   produces values that the existing `record_evaluation` /
   `record_evaluation_failure` paths already accept. The failure vocabulary
   travels as `exception_type` text with no new failure stage (P29-D04 option A).
8. **Content stays local.** Raw evaluated content is sent only to the
   customer-configured provider and is never retained, logged, hashed,
   serialized or exported by the SDK (decision 10 holds). A managed judge that
   receives raw content is out of scope (P29-D11 option A).
9. **Dependencies.** Core `dependencies = []` is unchanged. Any provider adapter
   or extra is subject to P29-D12 (option A: examples only, no extras).
10. **Failure never becomes a verdict.** Timeout, provider failure, invalid or
    oversize output, input limit, budget or overload never yields `PASS`, `FAIL`
    or `UNKNOWN`. `UNKNOWN` arises only from a completed judgment or a
    deterministic pre-check (ADR-0007 decision 7 holds).

## Alternatives Considered

- **Keep decision 9 and ship no judge.** Rejected for P29: semantic dimensions
  cannot be measured by equality or typed predicates.
- **Place the judge in a stable namespace.** Rejected (P29-D01): judge behavior
  is non-deterministic and the rubrics are uncalibrated; a stable label would
  overstate the contract.
- **Extend `EvaluatorRunner` with timeout machinery.** Rejected: it would change
  a stable class and spread remote-call semantics into deterministic evaluation.
- **Specialized per-dimension judge classes with embedded prompts.** Rejected:
  rubric edits would need releases and could change behavior under an unchanged
  class name (ADR-0007: class names are never identity).
- **Bundle vendor provider clients as extras.** Rejected for V1 (P29-D12):
  smallest support surface; providers are customer code.
- **Typed identity fields or new failure stages on the wire.** Rejected for V1
  (P29-D02, P29-D04): no contract change.

## Consequences

The SDK gains an experimental, provider-neutral, stdlib-only judge adapter
without changing any stable module. Judge results are explicitly labelled
non-deterministic and carry caller-declared identity. Customers own provider
choice, data-processing terms and calibration; the SDK states no accuracy claim.
Aggregation consequences on the platform (failures leave the SLI denominator,
UNKNOWN excluded, run-level cross-indicator health, gate reach) are existing
behavior, documented in the P29 design package, and unchanged by this ADR.

Operational consequences of the decisions above, recorded after the independent review (they narrow nothing and add no decision):

- **Sync timeouts are best effort.** A blocking provider cannot be interrupted; the judge classifies an overrun as `JudgeTimeoutError` after the call returns and discards the late reply
  (its reported tokens are then not counted against a budget). The provider's own client timeout is the real bound; an optional bounded-daemon-thread wrapper is available inside the same namespace.
- **Customer sinks run inside the recording gate.** Evidence is handed to the existing `RunHandle` under one gate per scope, so sinks and diagnostic handlers invoked by the handle must be
  non-blocking and must not re-enter the scope (re-entry raises `RuntimeError`). "Recorded" means handed to the handle; a sink that raises is isolated by the handle (ADR-0004) and the judge cannot detect the drop.

## Security Impact

Raw content may be sent to a provider the customer chose; the SDK documents this
egress, sends only the roles a rubric requires, never reads credentials or the
environment, never chains provider exceptions into diagnostics by default, and
keeps exception messages constant. Prompt injection through evaluated content is
mitigated (per-call random delimiters, trust labels, strict output schema, closed
code set), not eliminated. See the P29 security and privacy review.

## Performance Impact

Provider calls add remote latency and cost owned by the customer; bounded by
configurable limits and budgets. Library overhead is unmeasured until the S12
benchmark; no figure is claimed. The deterministic M4 path is unaffected.

## Compatibility Impact

Additive and experimental only. No stable module, signature, enum value, event,
wire member or default changes. `dependencies = []` is unchanged. Existing compat
snapshots are unchanged; a new snapshot covers the experimental namespace.

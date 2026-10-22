# Design proposal (NOT implemented): calibration provenance for the Gentlity platform

Status: **DESIGN ONLY.** Approved by the owner for design (OD-S4-3, Option 1: machine-readable provenance metadata) and, for section 6, OD-S4-4 (design; implementation deferred); see
[OWNER_DECISIONS_S4.md](OWNER_DECISIONS_S4.md). It is **not** approval to implement or deploy anything. This pull request changes **no** wire member, HTTP contract, platform code,
schema, API or migration; it does not modify the platform repository; it does not touch `MeasurementHealth`. Any future implementation needs its own design review, version
and compatibility decision, schema, fixtures and conformance tests (repository rule: public HTTP contracts are language-neutral and fixture-driven).

## 1. Architecture principle

**Gentlity must adapt to an organization's existing AI infrastructure, not force the organization to redesign its systems to adopt Gentlity.**

Consequences for this and every later ingestion or evaluation design:

* **Interoperate first:** accept evidence through OpenTelemetry/OTLP-shaped paths as well as the native SDK; map to the same vendor-neutral evidence contract.
* **Framework-neutral interfaces:** no requirement to adopt a particular agent framework, judge library or provider.
* **Customer-controlled data planes:** calibration datasets, raw judged content and signing keys stay in the customer's environment; Gentlity receives identifiers, counts and
  digests only.
* **Minimal integration overhead:** a customer with an existing evaluator pipeline attaches calibration provenance as optional, bounded metadata; absence of it is a defined,
  explainable state, never an error and never PASS.
* **Privacy by default:** no raw prompts, responses, rubric text or case text in telemetry; opt-in for anything provider-bound.
* **Vendor-neutral evidence contracts:** the contract is published as OpenAPI/JSON Schema with data-only fixtures usable from Python, Go, Java and TypeScript; no Python behaviour
  defines the protocol.

## 2. Problem

Today the platform sees a judge's evidence only as `evaluator.name` (rubric id), `evaluator.version` (rubric version), `configuration_id` and `deterministic = false`. The Session 2 guard
(`decide_guard`) separates evaluator identities and refuses mixed methodology, but cannot tell a calibrated judge from an uncalibrated one, and a silent provider-side change that
does not alter `configuration_id` is invisible. When the SDK-side admission hook skips an evaluation, the platform sees only absence and cannot tell why. Customers therefore cannot
see whether a reliability measurement is trustworthy or degraded, or why.

## 3. Approved direction (Option 1): optional, bounded, versioned calibration provenance

Carry, **per evaluator identity and per window of evidence**, a small content-free record, as an optional member of the evaluator provenance in a new, explicitly versioned evidence
schema (an additive wire change decided on its own):

| Member | Meaning | Bounds |
|---|---|---|
| `calibration.status` | one of `calibrated`, `uncalibrated`, `insufficient_reference_evidence`, `calibration_expired`, `incompatible`, `demonstration`, `ungated` | closed enum |
| `calibration.behaviour_digest` | SHA-256 of the judge behaviour (template, limits, engine revision, configuration); **no raw prompt** | 64 hex |
| `calibration.assessment_digest` | SHA-256 of the assessment that supports the status (absent when none exists) | 64 hex |
| `calibration.policy_digest` | SHA-256 of the caller's policy that produced the status | 64 hex |
| `calibration.signed` | whether the assessment HMAC was verified **by the producer** (a claim, see section 5) | boolean |
| `calibration.model_declaration` | customer-declared provider/model id/model version (identifiers only) | bounded identifier grammar |
| `calibration.observed_model` | provider-observed identity, **when and only when** the provider returned one (section 6) | optional; absent = unknown |

Skipped evaluations carry **no outcome** and no PASS/FAIL. Instead the SDK would emit a bounded *evaluation-skipped* observation with a closed reason code, so the platform can
distinguish "no traffic" from "judge not admitted":

`calibration_uncalibrated`, `calibration_no_evidence`, `calibration_expired`, `calibration_incompatible`, `calibration_demonstration`, `admission_error` (the SDK's current codes).

This is a *new observation kind*, not a new outcome value. Missing evidence stays missing evidence.

## 4. How the platform would use it (eligibility is a platform decision)

* **Provenance and comparability preserved.** Calibration metadata is *additional* provenance. It must not change how evaluator identity is grouped; the existing guard sees only `configuration_id`, which covers
  the model label, template id, minimum confidence, repeats and citation rule but **not** the limits, engine revision or template digest; the behaviour digest would make those changes
  visible as a distinct identity without altering how identities are grouped today.
* **Eligibility for SLO windows is decided by the platform, per SLO policy**, from the stored metadata: e.g. a policy may admit only `calibrated` judge evidence into a semantic SLO window,
  exclude `uncalibrated`/`ungated` judge evidence, and show the exclusion as a named reason. This mirrors the SDK gate but does not trust it: the platform recomputes eligibility from
  the metadata it stored.
* **No change to PASS/FAIL/UNKNOWN meaning, to `MeasurementHealth`, or to the deterministic-evaluator path.** Calibration status is neither a health signal nor an outcome (the three are
  different: *agent outcome correctness* is what the evaluator said, *measurement health* is whether evidence collection was complete, *calibration status* is whether this evaluator's
  verdicts are trusted for this purpose). Overloading health with calibration would repeat the problem owner decision OD-10 forbids.
* **No silent rewriting of history.** Eligibility is evaluated when evidence is evaluated and recorded in the evaluation record (Session 2 `operational_evaluation_records`-style, with
  the policy and metadata identities); a later change of policy or status does not alter past records. A re-evaluation, if ever offered, creates a new record and says so.
* **Guard interplay.** Excluded judge evidence reduces determinate counts, so the existing minimum-sample, no-data and recovery rules apply unchanged (absence never recovers an alert).

## 5. Signed-assessment verification and trust ownership

* The assessment's HMAC key belongs to the **customer** (customer-controlled data plane). Gentlity does not hold it and cannot verify the signature; it can only store the producer's
  claim (`calibration.signed`) and the digests. Treating that claim as authoritative would let any producer assert `calibrated`.
* Options for a future design (to be decided in review, not here): (a) platform treats calibration metadata as *informational* provenance and applies eligibility only from
  customer-configured trust (credential-scoped: a machine credential may be authorised to assert calibration for a deployment); (b) customer-registered **public verification keys** with
  asymmetric signatures (a change from the SDK's current symmetric HMAC); (c) a customer-hosted verification service. Each has key-management, rotation and revocation costs.
* Whoever can assert `calibrated` is a **trust owner** and must be an explicit, audited role; separation of "uploads datasets" from "approves calibration" (not available in the
  local SDK) belongs here.

## 6. Provider-observed model version (OD-S4-4, design only)

* The judge provider contract (`ProviderReply`) carries no model metadata, so the SDK cannot know which model answered; provider/model/version are today **customer declarations**.
* Proposal: an **optional** `model_version_observed` (and optionally `model_id_observed`) on `ProviderReply`, default `None`, populated by a provider adapter *only when the provider's
  response states it*. It would be recorded in the judgment table and compared by the fingerprint **separately** from the declared identity.
* Rules: never invent or infer an observed version; `None` means *unknown* and is preserved as unknown (not equal to any version); observed and declared are distinct fields; a
  mismatch between declared and observed is itself a drift indicator; the field is bounded by the identity grammar; no raw response content is stored.
* Compatibility to evaluate before any change: `ProviderReply` is a frozen dataclass in an Experimental API (an added defaulted field is additive, but the compat snapshot, the fixture
  vectors and third-party providers must be checked); the stable HTTP contract is untouched.

## 7. Customer-visible explanations and auditability

* Each excluded or skipped evaluation yields a **named reason** visible beside the SLO (for example "judge evidence excluded: calibration expired on 2026-09-30; last assessment digest ...").
* The record stores identities (policy digest, assessment digest, behaviour digest, reason code, time), never content, so an auditor can re-derive the decision from the stored metadata
  and the customer's own assessment document.
* The explanation must separate the three questions: *what did the evaluator say*, *was evidence collection complete*, *is this evaluator trusted for this use*.

## 8. Multi-language and vendor-neutral requirements

* Schema + OpenAPI + JSON Schema for the metadata, with data-only fixtures: positive, negative, boundary (unknown enum values, oversized digests, absent members), and digest vectors;
  conformance for Python, Go, Java and TypeScript SDKs, and a mapping for OTLP attributes (a fixed attribute namespace, bounded values) for producers that cannot use a native SDK.
* Forward compatibility: unknown `status` values from a newer producer must degrade to *ungated/unknown-status* handling, never to `calibrated`.
* The behaviour digest's *inputs* are SDK-implementation specific (template, limits, engine revision); other SDKs define their own behaviour digest over their own behaviour. The platform
  compares digests for equality only, never interprets them.

## 9. Constraints any option must keep

UNKNOWN is not PASS; missing evidence is not proof of reliability; evaluator failure is not agent failure; judge disagreement is not agent failure; deterministic evaluations and
historical SLO results are never rewritten; the guard stays asymmetric (absence never recovers an active alert); calibration status never enters `MeasurementHealth`.

## 10. Decisions and reviews needed before any implementation

A separately reviewed design (architecture, security, compatibility) and an explicit owner decision on: the trust-ownership model (section 5), the wire-version decision, the OTLP mapping,
and the platform eligibility semantics. Nothing in this document is scheduled.

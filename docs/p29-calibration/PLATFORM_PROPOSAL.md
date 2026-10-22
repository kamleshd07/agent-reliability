# Proposal (not implemented): carrying calibration status to the platform

Status: **PROPOSAL ONLY. Requires its own design review and owner approval (OD-S4-3).** Nothing here is built; no wire member, API, schema or migration is added
by Session 4, and Session 2 production semantics are unchanged. `MeasurementHealth` must not be used for this (owner decision OD-10).

## Problem
Today the platform sees a judge's evidence only as `evaluator.name` (rubric id), `evaluator.version` (rubric version), `configuration_id` (model label, template,
min confidence, repeats, citations) and `deterministic = false`. The Session 2 guard (`decide_guard`) separates evaluator identities and refuses mixed methodology,
but it cannot tell a calibrated judge from an uncalibrated one, and a silent provider-side model update that does not change `configuration_id` is invisible.
When the SDK-side admission hook skips a run, the platform sees only absence.

## Options (for a later review)
1. **Provenance attribute.** Add optional, bounded `evaluator.calibration` {`status`, `behaviour_digest` prefix, `assessment_id`} to the schema-v2 evaluation record
   (additive wire change, new schema version decision, fixtures, OpenAPI, conformance). The guard could then exclude `status != calibrated` judge evidence from
   SLO windows as a distinct, explainable reason, and customers would see why a measurement is degraded.
2. **Encode in `configuration_id` only.** No wire change: callers put a calibration epoch / model version into `model_label`. Visible to the existing methodology
   rule, but not machine-readable status and easy to forget.
3. **SDK-only (this slice).** Admission hook; the platform sees absence. Honest but opaque to the customer dashboard.

## Constraints any option must keep
UNKNOWN is not PASS; missing evidence is not proof of reliability; evaluator failure is not agent failure; judge disagreement is not agent failure; deterministic
evaluations and historical SLO results are never rewritten; the guard stays asymmetric (absence never recovers an active alert).

## Decision needed from the owner
Choose option 1, 2 or 3 and authorise a design cycle for the platform side.

# Judge fingerprint: what a calibration applies to

`JudgeFingerprint` (module `agent_reliability.experimental.calibration.fingerprint`) identifies the configuration a calibration
was measured on. It is **additive**: `EvaluatorIdentity` (name = rubric id, version = rubric version, configuration id) and the
P28 wire are unchanged. A display name such as `model_label` never implies equivalence.

## Components

| Component | Source | Notes |
|---|---|---|
| `rubric_id`, `rubric_version`, `rubric_fingerprint`, `dimension` | the bound judge's rubric (`rubric.fingerprint()` is a SHA-256 of the canonical rubric) | rubric text changes change the fingerprint |
| `template_id`, `template_digest` | `judge.behaviour` | digest of the prompt as the real builder renders it for fixed probe rubrics, nonce and parts (with/without citations, with the repair variant) plus the output schema id, reason bound and requested temperature. A template edit that forgot to change `jp1` still changes the digest. |
| `limits_digest` | `JudgeLimits` of the bound judge | timeouts, attempts, repair attempts, input/output bounds change failure and abstention behaviour |
| `repeats`, `min_confidence`, `capture_reason`, `require_citations`, `configuration_id` | the bound judge's policy and composed identity | `configuration_id` = `<model_label>.<template>.mc-<..>.rp<..>.ct<..>` |
| `implementation_version` | `agent_reliability.__version__` | recorded and shown in `diff()`, **not** part of the digest: a patch release does not force re-calibration |
| `model` = `ModelDeclaration(provider, model_id, model_version|None)` | **caller declaration** | always displayed; compared separately |

`behaviour_digest` = SHA-256 of the canonical JSON of the behaviour components (everything except `implementation_version` and the
model declaration). **Equivalent = equal `behaviour_digest` and equal `ModelDeclaration`.** The fingerprint is derived from the bound
evaluator (`JudgeFingerprint.for_evaluator`), never typed in; a `CalibrationGate` re-derives it and `IndicatorBinding` rejects a
gate that is not bound to its evaluator.

No raw prompt, rubric text, case text or credential is captured: the artefact holds identifiers and digests only.

## What it cannot detect (stated limitation)

The judge never observes which model answered (`ProviderReply` has no model metadata). Provider, model id and model version are
declarations, so **a silent provider-side model update is undetectable** by this design. Mitigations: (1) expiry (`validity_days`),
(2) re-calibration, (3) put the model version in `model_label` so it reaches `configuration_id`, the Session 2 platform guard's
methodology check and the behaviour digest. An additive `ProviderReply.model_version_observed` would close part of the gap but changes the
judge API (owner decision OD-S4-4, not implemented).

## Dataset and report linkage

An assessment records the dataset id, version, manifest SHA-256, split, derived label provenance (with counts per provenance) and the
rubric binding. A dataset whose rubric id/version/dimension differs from the judge's makes the status `incompatible`.
Assessment documents carry a plain SHA-256 and an optional HMAC-SHA256 over their canonical body.

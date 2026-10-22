# Security and privacy: calibration and admission (author's analysis; independent review in `reviews/`)

## Assets and boundaries

Calibration involves sensitive inputs and outputs of the evaluated agent. The package is local and stdlib-only: no network, no
environment reads, no secrets, no provider calls of its own. Raw case text exists only in the customer's dataset files and in memory.
Every derived artefact (assessment, admission decision, fingerprint, leakage report, comparison, drift) contains identifiers,
counts, digests of configuration (never of content) and bounded enums.

## Controls

| Threat | Control | Test |
|---|---|---|
| Raw content in artefacts, logs, errors, reprs | content-free artefacts; `ReferenceCase`/dataset reprs show ids only; errors name rules not values; leakage reported as ids and counts (no content digests, which are dictionary-reversible) | `test_no_artefact_contains_case_content`, `test_error_messages_never_contain_case_content`, `test_provider_error_text_never_reaches_the_table` |
| Hostile dataset files (huge, nested, duplicate keys, NaN, overflowed numbers, traversal, symlink, FIFO) | the file is opened with `O_NOFOLLOW | O_NONBLOCK`, the size cap is checked on the opened descriptor (`fstat`) and the read is chunked and bounded; line/case/depth caps; integers limited to 18 digits and floats to finite values; strict JSON; plain file names beside the manifest; symlinks refused; schema validation | `test_dataset.py`, `test_schemas.py` |
| Dataset tampering / poisoning after review | manifest SHA-256 pinned by the caller (`expected_manifest_sha256` required); per-split SHA-256; derived (weakest) provenance; leakage detection; held-out only | `test_the_manifest_digest_must_be_pinned...`, leakage tests |
| Forged or altered assessment | schema + fingerprint-consistency validation at parse; SHA-256 digest; optional HMAC-SHA256 (stdlib `hmac`, `compare_digest`); policy can **require** verified integrity | `test_a_tampered_assessment...`, `test_a_forged_digest...`, hostile-mutation test |
| Misuse of status (admitting a different judge, an expired or future-dated assessment, a looser policy) | gate derived from the bound evaluator and rejected by `IndicatorBinding` for any other; status recomputed with the clock on every call; future-dated assessments never calibrate; policy summary and `below_starting_point` printed with every decision; synthetic/demonstration/calibrated rules enforced at policy construction | `test_runner_and_gate.py`, `test_admission.py`, `test_policy.py` |
| Prompt injection inside evaluated samples | existing judge prompt framing (nonce-delimited, trust-labelled blocks; judged content never in the system message); adversarial stratum reported separately; `max_adversarial_pass_on_fail` criterion | existing P29 prompt tests; `adversarial_defects_passed` |
| Hook misbehaviour | fail closed (`admission_error` skip); `BaseException` propagates; no content in the reason | `test_a_failing_or_malformed_hook_fails_closed_without_leaking` |
| Resource exhaustion | caps above; O(1) indexed lookups (a quadratic scan was found and fixed); bounded repetitions (1-10) | `test_scaling.py`, [PERFORMANCE.md](PERFORMANCE.md) |
| Hidden spend / external transmission | none in this package; `collect_judgments` calls only the caller's judge, whose opt-in provider, budgets, limits and retry policy apply unchanged; tests use scripted providers | no-network assertion in the walkthrough test |

## Residual risks and limits (not controlled)

* **Provenance is an attestation.** Anyone who can write the dataset can declare `human_adjudicated`. Mixed provenance is derived, counts are
  shown, inter-labeler agreement gates interpretation, but nothing proves labels are human.
* **A signature is not a provenance proof.** The HMAC shows the record is unchanged since signing by a key holder; it cannot show that a real judge
  run on the named dataset produced the numbers.
* **Policies that do not require verified integrity cannot calibrate.** `CalibrationPolicy` refuses `require_verified_integrity=False` unless it is `demonstration_only`, because an unsigned record can be forged by anyone who can write the file (editing the counts and recomputing the public SHA-256 is enough). The HMAC is domain-separated; there is no key id (key management is the caller's).
* **Unsigned records.** The plain digest detects accident only. Without the HMAC key anyone with file access can forge a record; there is no CLI that
  prints a status from an arbitrary file (cut from the slice for this reason), and `require_verified_integrity` makes an unverified assessment uncalibrated.
  HMAC key management is the caller's.
* **No authorization model.** The SDK is a local library: "who may upload datasets" versus "who may approve calibration" is a platform or process
  control, not provided here. There is no approval attestation in this slice.
* **Label contamination.** A calibration set that includes the judge's own outputs ("LLM-labelled human data") or content the provider model was trained
  on defeats the measurement. Public synthetic fixtures may appear in future training data and must never gauge a real model.
* **Held-out reuse.** Trying many configurations against one held-out set is uncontrolled multiple testing; `heldout_attempt` makes it visible only.
* **Silent model updates** are undetectable (see [PROVENANCE_SPEC.md](PROVENANCE_SPEC.md)).
* **Exact intervals assume independent examples**; clustered data (several examples per conversation) understates uncertainty.
* **LLM-judging-LLM.** The judge shares blind spots with the judged model, is sensitive to prompt wording and to position/verbosity, hosted models are
  non-stationary, and agreement between judges is not correctness. Calibration measures one configuration on one distribution at one time.
* **Gate coverage.** Only bindings with `admission=` are gated. Direct `LLMJudge` use, `run.record_evaluation`, and bindings left at `None` are ungated
  (counted by `ungated_model_backed`); see OD-S4-2.
* **A skipped judge leaves run health HEALTHY.** By design (owner decision OD-10: measurement health is not a gate input; an inadmissible judge is not an evaluation failure). Expiry or fingerprint drift therefore silently removes the judge evidence; only the local `admission_skipped` counter and observer report show it, and SG-5 must alert on it.
* **Absence is visible only locally.** A skipped judge produces missing evidence on the platform, indistinguishable from no traffic until OD-S4-3.

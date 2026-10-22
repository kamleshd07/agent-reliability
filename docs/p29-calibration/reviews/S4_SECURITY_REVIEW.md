# S4 independent adversarial security review: draft PR #10 (p29 judge calibration)

Reviewed head: 0bde58d22a790f69465b8b0421fdb8021124a7f3 (src diff vs the first-reviewed ba2523d is empty; all attacks were run on a `git archive` extract of ba2523d, so they apply unchanged).
Reviewer environment: own extract + own venv under the scratchpad; the author's worktree was only read via `git diff`/`git archive`. No network, no real credentials.

## Verdict: APPROVE_WITH_FIXES
No BLOCKER and no HIGH found. The core trust decision (HMAC-verified, fingerprint-bound, clock-recomputed, fail-closed hook) held under every attack I ran. There are 4 MEDIUM and several LOW/INFO items; the doc claims in SECURITY_AND_PRIVACY.md row 15 and some residual-risk statements need correcting.

Scope limits (honest): I reviewed the calibration package, the coordinator hook, packaging and docs. I did not run the full 202-test suite beyond confirming it passes (202 passed). I did not review `_stats.py` / `metrics.py` numerics in depth (read-only skim, no fuzzing); item (4) prompt injection was assessed by reading only (see S4-L5); item (6) credential hygiene by reading + grep only.

## What was run vs only read
Run (scripts in `.../scratchpad/atk/a1.py a2.py a3b.py a4.py a5.py`):
- a1: ~30 mutations of a signed assessment (tamper, sha-only re-sign, naive/odd timestamps, future dataset date, uppercase digests, trailing newline in ids/digests, empty/unicode integrity, swapped model, train split, bool/float/giant/NaN counts, provenance claims).
- a2: hostile assessment JSON (1M-deep arrays, 100k-deep objects, 5000-digit ints, duplicate keys, NaN, >1MB), regex timing on 1MB strings, hostile dataset lines (CRLF, U+2028, BOM, deep, huge int, duplicate keys), 20 000-case load, leakage-evasion matrix.
- a3b: gate binding to another evaluator, odd/raising hooks, policy mutation, pickle, wrong key/unsigned, naive/bad clocks, canary grep over repr/str/explain/as_dict/to_json, error-message canary checks.
- a4: parent-dir symlink, manifest symlink, hard link, FIFO, TOCTOU swap between lstat and read, label-rule probes.
- a5: admission hook over `evaluate` (async), `submit`, blocking hook, run health, coverage counters.
- `uv build` (wheel + sdist) and listing of contents.
Only read: SECURITY_AND_PRIVACY.md claims, coordinator diff, `_stats`/`metrics`/`behaviour`, example script network behaviour (no network imports seen in the calibration package; not exhaustively traced).

## Findings

### S4-M1 MEDIUM: `require_verified_integrity=False` lets any file writer forge "calibrated"
Repro (a1): take a valid assessment, edit `metrics.headline.counts.support_fail=10**30` (or `dataset.label_provenance`, `leakage_clean`), recompute only the public SHA-256 (`integrity.sha256`), build `CalibrationAssessment`, `assess_admission` under `human_policy()` (verified-integrity off) gives `calibrated` / `integrity=unverified`. Same for "claim human_adjudicated provenance". With `require_verified_integrity=True` the same forgery is rejected (control held).
Impact: a non-demonstration policy that is a legitimate "calibrating" policy can disable the only tamper-proof check. `below_starting_point` merely lists it informationally. Anyone who can write the assessment file then controls admission.
Fix: make `require_verified_integrity=False` allowed only with `demonstration_only=True` (PolicyError otherwise), or make a sha-only record never reach `CALIBRATED`.

### S4-M2 MEDIUM: dataset size caps are enforced after the read, and TOCTOU is possible between lstat and read
`dataset._read_bounded`: `os.lstat` then `path.read_bytes()`, then re-checks length. Repro (a4): monkeypatch-free equivalent: replace the split file with a symlink to a 200 MB file after lstat; `read_bytes` follows it, the whole file is read into memory, and only then "exceeds its size cap" is raised. Replacing with a FIFO would block forever; with `/dev/zero` unbounded memory (I did not run that one to avoid OOM; follows from the code). Contents remain hash-pinned, so no integrity impact; this is DoS only and requires write access to the dataset directory.
Contradicts SECURITY_AND_PRIVACY.md row 15 ("caps checked before reading ... symlinks refused").
Fix: `os.open(..., O_RDONLY|O_NOFOLLOW|O_NONBLOCK)`, `fstat` on the fd (regular file, size), then `os.read` at most `limit+1` bytes. Also refuse parent-directory symlinks if "no symlinks" is a stated rule (a4: a symlinked parent directory is accepted; harmless because of hash pins, but the doc claim is wrong).

### S4-M3 MEDIUM: leakage detection is trivially evaded; `leakage_clean=true` is over-trusted
`_normalise` = NFKC + casefold + whitespace collapse. Repro (a2), same text in two splits reported `clean=True` for: added trailing period, zero-width space (U+200B), soft hyphen (U+00AD), Cyrillic homoglyph. Detected: case/whitespace, fullwidth forms. Near-duplicates and paraphrases are not attempted. A dataset author (or a lazy contamination) can place held-out items in train/calibration undetected, inflating the assessed metrics, and the assessment records `leakage_clean: true` which the admission criterion `no_split_leakage` treats as a hard guarantee.
Also: a dataset with only a held-out split trivially has `leakage_clean=true`.
Fix: strip Unicode category Cf/Mn and punctuation in the normalised key, fold confusables for at least a known set, rename the claim to "no exact/normalised-exact duplicates detected" in the assessment and docs; require both a held-out and a non-held-out split (or record `cross_split_checked=false`) before `leakage_clean` can be true.

### S4-M4 MEDIUM: skipping is invisible to run health; expiry silently removes all judge evidence (denial of evidence)
Repro (a5): async `evaluate` and `submit` both honour the hook (0 provider calls, 0 recorded events). Run `measurement_health` stays `healthy`; the only trace is the `admission_skipped` counter in `coverage()` and an observer report. When a calibration expires (time passes, no attacker needed) or the fingerprint drifts, every judge indicator quietly produces nothing and dashboards show no degradation. An attacker who can influence only the clock source of the gate (injected `clock`) or can cause fingerprint drift (e.g. model_label change) can induce this. By design (documented as "missing evidence, not PASS") but the residual risk statement understates it: nothing alerts.
Fix: surface a bounded `admission_skipped` condition to `MeasurementHealth` (as degraded, not failed) or at least add an observable event/log-safe metric; document an operator runbook.

### S4-L1 LOW: dataset-level inputs accepted without sanity checks in assessments
- `dataset.created_at` in the future (2099) is accepted; `dataset_current` is met for negative age (a1). Add `dataset_created_at <= created_at <= now+skew`.
- Assessment `created_at` earlier than `dataset.created_at` not checked.
- Counts accept absurdly large ints (10**30) and no cross-field consistency (counts vs rates vs n_labelled) is validated; only matters for unsigned records (see M1).
Fix: add range maxima to schema and a consistency validator.

### S4-L2 LOW: JSON Schema `pattern` uses `re.search` with `$`, which accepts a trailing newline
Repro (a1): `dataset.dataset_id + "\n"` and `hmac_sha256 + "\n"` pass `CalibrationAssessment(...)` schema validation (dataset loader's own `_ID.fullmatch` is stricter, so loader is fine). Does not bypass admission (digests are then compared unequal), but it breaks the language-neutral contract in CLAUDE.md: other validators (`\z` semantic / Go / Rust) would reject what Python accepts.
Fix: use `\Z` in published patterns or `fullmatch` in `_jsonschema`.

### S4-L3 LOW: adjudication rules let `human_label` contradict unanimous labelers
Repro (a4): labels `[a:pass, b:pass]`, `adjudication=third_reviewer`, `human_label=fail`, `label_provenance=human_adjudicated` is accepted. Unique labeler ids are the only independence check: `alice`/`alice2` count as two reviewers ("sock puppets"). Provenance is an attestation (documented) but the rules give a false appearance of cross-checking; `inter_labeler_agreement` is computed from `labels` while metrics use `human_label`, so they can disagree arbitrarily.
Fix: for non-`none` methods other than a real disagreement require a recorded reason; at minimum document that adjudicated `human_label` is unconstrained.

### S4-L4 LOW: sdist ships internal-style P29 calibration reports
`pyproject.toml` sdist excludes list was extended for earlier P29 internal reports, but `docs/p29-calibration/{GAP_ASSESSMENT,PLATFORM_PROPOSAL,TRACEABILITY_MATRIX,PERFORMANCE}.md` are shipped (confirmed by `uv build`). Content contained no secrets or local paths that I saw, but PLATFORM_PROPOSAL.md is an internal "owner decision" document. Wheel is clean: only `agent_reliability/experimental/calibration/*.py` + three schema JSONs; no fixtures, no docs; `dependencies = []` unchanged. Synthetic fixtures `tests/fixtures/p29_calibration/demo/*` do ship in sdist (public, synthetic, acceptable).
Fix: add those docs to the sdist exclude list, or decide they are public.

### S4-L5 LOW/INFO: prompt injection in samples (read-only assessment)
Adversarial-stratum accounting is driven by the dataset's own `difficulty` field, not by content; injected text in a case cannot change the stratum or pipeline decisions (no content is parsed beyond hashing/normalising). The injection risk lives in the existing judge framing (nonce-fenced prompt, unchanged by this PR), and calibration measures it only as far as the author labelled adversarial cases. A dataset author can mislabel adversarial cases `clear` to lower the adversarial-defect count; this is poisoning under the attestation model (hash-pinned manifest protects only against post-review change).

### S4-I1 INFO: in-process tampering is outside the model but not blocked
`object.__setattr__(policy, "min_examples", 1)` after gate construction changes admission (a3: the decision remained `calibrated` with the policy mutated); `pickle` of a `CalibrationPolicy` bypasses `__post_init__`. A `CalibrationPolicy` subclass can override fields. `AdmissionVerdict` subclasses can return different `allowed` on successive reads (the coordinator reads it twice). `IndicatorBinding.admission` accepts any object with the two methods. All require code execution in the process (already full trust). Note for docs only; optionally snapshot `allowed`/`reason_code` once in `_prepare`.

### S4-I2 INFO: signed assessment attests the key holder, not the run
`build_assessment` accepts any `JudgmentTable` whose fingerprint field the caller supplies; nothing proves the judge produced the rows. `heldout_attempt` is self-reported. HMAC key is a bare shared secret with no domain separation prefix/key id (key-confusion risk if reused for other HMACs; minimum length 16 bytes only). Fix: prefix the HMAC input with a domain tag (e.g. `b"gentlity.calibration-assessment/1\n"`) and record a `key_id`.

### S4-I3 INFO: blocking/slow hook stalls the event loop
a5: a hook that sleeps 1 s blocked the asyncio loop 1.01 s (hook is called synchronously in `_prepare`). Documented in the protocol docstring; ok.

## Attacks that FAILED (control held)
- Unsigned/sha-only-forged/wrong-key assessment under `require_verified_integrity=True`: `uncalibrated` (a1, a3).
- Tamper without re-signing: `integrity=mismatch`; swapped model declaration in a signed record: mismatch (a1).
- Naive and date-only timestamps rejected by schema; future-dated `created_at` rejected (`not_future_dated`); ancient dataset date expired; split `train` rejected; claiming synthetic provenance under a human policy not calibrated.
- Uppercase hex digests, empty `integrity`, non-ASCII `hmac_sha256`, bool/float/negative/NaN counts rejected by the schema.
- Gate bound to another evaluator rejected by `IndicatorBinding`; bad/naive/non-datetime clocks raise `ValueError` (and the coordinator turns hook exceptions into `admission_error` skip, fail closed). Odd return values (None/True/dict) are mapped to a skip per the code and test. `BaseException` propagates by design before any lock or state is touched, so no state leaks.
- Hook is applied on `evaluate_sync`, async `evaluate` and `submit` (0 provider calls, 0 recorded events when skipping); the counters are lock-protected.
- Hostile JSON: 1M-deep arrays/100k-deep objects, 5000-digit ints, duplicate keys, NaN, >1 MB all rejected in ~0 s without crash; schema regexes are linear (1 MB string search 0.0 s); BOM, deep and duplicate-key dataset lines rejected; CRLF and U+2028 handled safely; 20 000-case dataset loads in 1.1 s.
- Manifest pin mandatory and checked before parsing; manifest symlink refused; FIFO refused statically; hard links harmless (content hash-pinned); path traversal blocked by plain-name rule.
- Privacy: canary planted in case text, labeler id, case id and label value did not appear in repr/str/explain/as_dict/to_json/gate repr/error messages (a3); error messages state rules only and `__cause__` is suppressed; `CalibrationCase` refuses copy/pickle (`TypeError`), so content cannot be serialised by accident.
- Packaging: zero runtime dependencies; wheel contains no fixtures/docs.

## Residual risk statements versus reality
- "Caps checked before reading; symlinks refused" (SECURITY_AND_PRIVACY row 15): not accurate (S4-M2).
- "Leakage detection" is described as protective; it is exact + NFKC-normalised match only (S4-M3).
- "Misuse of status ... future-dated" holds for assessment time, not dataset time (S4-L1).
- Missing-evidence-as-safe-default is true for PASS semantics but is not visible in run health (S4-M4).
- Model declaration, provider-side model drift, and label provenance are attested; the doc says so, and this matches reality.

## BLOCKER/HIGH list
None.

## Cleanup
No background processes left; large temp file removed; scratch artefacts remain under the scratchpad only.


---

# Re-check at f68b1e9

Method: fresh `git archive` of f68b1e9af195f50ef99d1b133c468a0219feda89 (extract `.../scratchpad/y`), earlier attack scripts re-run against it (`atk2/a1,a2,a3b,a4,a5`) plus new ones (`atk2/b1..b4`). `tests/unit/experimental_calibration` + `experimental_judge`: 773 passed (with `PYTHONPATH=src`). `uv build` could not run (offline), so the sdist exclude list was verified by reading `pyproject.toml`, not by listing the artifact.

## Per-finding status
| ID | Status | Evidence |
|---|---|---|
| S4-M1 | CLOSED | `human_policy(require_verified_integrity=False)` now raises `PolicyError` (also via `dataclasses.replace`). Unsigned record under a calibrating policy and `hmac_key=KEY`: `uncalibrated / integrity_verified violated`. Un-prefixed legacy HMAC no longer verifies; domain-separated one does. Demonstration-only unsigned can never reach `calibrated` (`insufficient_reference_evidence`). Gate without key for a verifying policy raises at construction. |
| S4-M2 | CLOSED (with documented residual) | FIFO, `/dev/zero`, `/dev/null`, symlinked file: `DatasetError` (fstat on the opened descriptor, non-blocking open, no hang). Swap-to-FIFO immediately before open: refused. File growing between fstat and read (+20 MB): read capped at limit+1, peak RSS about 61 MB. 300 MB file: refused before reading. Symlinked parent directory is accepted, and the docs now say so (row 15). Hash pins unchanged. |
| S4-M3 | CLOSED for what it claims; one weak spot (S4-N1) | New normalisation catches intra-word ZWSP/soft-hyphen, punctuation, digit separators, bidi/tag characters, NBSP/ideographic space, hyphen-join, part reordering. Homoglyph still undetected, and `DATASET_SCHEMA.md` lines 59-60 and the `_normalise` docstring say so ("clean" = no *detected* overlap), so no overclaim there. Held-out-only dataset: signed assessment is `insufficient_reference_evidence` via `leakage_checked_against_other_splits`; with a `train` split it is `calibrated`. A forged `leakage_checked_against: ["train"]` record is rejected (unsigned fails integrity). |
| S4-M4 | OPEN-ACCEPTED (documented residual) | Behaviour unchanged (a5: async skip, 0 provider calls, 0 events, health `healthy`; counter and observer report only). SECURITY_AND_PRIVACY line 45 now states it plainly. See disposition below. |
| S4-L1 | CLOSED | Giant ints (10**30), >18-digit ints, overflow floats refused at strict JSON; inconsistent counts, future dataset date (`dataset.created_at` 2099) and tampered metrics now raise `AssessmentError: internally inconsistent`; policy ints capped at 10**9. |
| S4-L2 | CLOSED | `dataset_id+"\n"`, `sha256+"\n"`, `hmac_sha256+"\n"` all rejected by schema validation. (The check only fires for patterns ending in `$`; all current patterns do.) |
| S4-L3 | CLOSED (unanimous case); residual INFO | Unanimous `pass,pass` + `third_reviewer` + `human_label=fail` now rejected ("contradicts unanimous labels"); unresolved now needs disagreeing labels. Labeler-id independence (`alice`/`alice2`) is still unverifiable: it is an attestation, as documented. |
| S4-L4 | CLOSED (read only) | Exclude list now covers GAP_ASSESSMENT, PLATFORM_PROPOSAL, TRACEABILITY_MATRIX, COMPATIBILITY_REPORT, GO_NO_GO and `reviews/`. Not verified by building the sdist. |
| S4-L5, S4-I1, S4-I2, S4-I3 | unchanged INFO | I2: HMAC domain separation now present (partial fix); no `key_id`. I3: blocking hook still stalls the loop (1.01 s), documented. |

Earlier "failed attacks" re-run and still held: tamper/mismatch, swapped model, bad clocks, wrong key, BaseException propagation, hostile JSON (deep/wide/dup/NaN/bigint), canary privacy (no canary in repr/explain/as_dict/to_json/errors), async `evaluate` and `submit` both gated.

## New findings
- S4-N1 LOW: `leakage_checked_against_other_splits` is satisfied by the mere presence of any other split. Repro (`atk2/b4.py`): a signed assessment whose dataset has a 1-case, unrelated `train` split reaches `calibrated`. The criterion does not require a non-trivial other split (e.g. minimum cases, or that the other split is the one used for tuning), so it proves "a comparison was run", not "the tuning data was compared". The held-out-only gap is closed; the trivial-train gap is not. Fix: report the compared case counts and add a policy minimum (or document that the criterion is presence-only).
- S4-N2 INFO: `ENGINE_REVISION` is a manual constant. The fingerprint now covers parser/retry/aggregation changes only if a maintainer bumps it; the pinning test is a dev-time guard, not a runtime one. Acceptable, but state in docs that an unbumped behaviour change is undetectable at runtime.
- S4-N3 INFO: punctuation removal makes `a_b` and `a b` differ (`ab` vs `a b`) and can join words; harmless for leakage detection (only affects whether a trivially altered copy is flagged, tested variants flagged).
- No new HIGH/BLOCKER surface found in `_check_consistency` (iterative stack walk, no recursion; parse of 1 MB hostile JSON stays ~0 s).

## Consistent-but-false records
Agreed: crafting an arithmetically consistent but false assessment without the HMAC key can no longer reach `calibrated` because calibrating policies now require verified integrity (M1), so it is out of scope. With the key it is not a vulnerability: the key holder is the attesting party (documented trust model; the signature never proved the judge ran, see S4-I2). Note the consistency check does not tie `rates` to `counts` across blocks; irrelevant for the above reason, but it means the arithmetic check is a hygiene measure, not a security boundary.

## Disposition on S4-M4 (HEALTHY on skip, OD-10)
Acceptable for this PR, as an owner decision, provided: (1) it stays documented (it is), (2) the local counters/observer reports remain the signal, and (3) the platform-side visibility proposal (PLATFORM_PROPOSAL option 1) stays tracked, because until then an expired calibration is a silent evidence outage that no dashboard shows. I would not accept it for any GA/non-Experimental promotion without a visible signal.

## Updated verdict: APPROVE
No BLOCKER/HIGH. M1, M2, M3 (as claimed), L1-L4 closed; M4 is an accepted documented residual; open items are LOW/INFO only (N1, N2, I-series). Suggested but non-blocking: address N1 and verify the sdist exclusions by an actual build in CI.

# P29 V1 SDK implementation log (part 1: S00-S04)

Status: running log, local workspace only (`<workspace>/agent-reliability-p29`, baseline in
P29_WORKSPACE_BASELINE.md (relocated; see docs/DESIGN_RECORDS.md)). Written by the implementing agent. **Nothing here is independently
verified, reviewed, committed, released or deployed.** Status words: IMPLEMENTED = code and tests exist and pass locally in this workspace
(author-run); PARTIAL; NOT STARTED. They are not the architecture-section-0 labels VERIFIED or RELEASED, which this log does not claim.

Authorization (owner message of 2026-10-16, quoted by the task): P29-D01..P29-D13 option A; P29-D09 conditional on SG-1..SG-6 before pilot use;
G-A package and plan; G-C the proposed SDK ADR amendment to ADR-0007 decision 9 (within the documented P29 V1 scope); implementation and local
verification of the V1 SDK stages. Not approved: P28 contract revision 16, P28-D14, ADR-0023 Appendix A.2, any P28 wire/schema/platform change,
shared TEST/production deployment, publication/release, commits/pushes/PRs/merges. The approval record is unsigned; no approver or time is recorded.

Environment: CPython 3.11.17 / 3.12.15 / 3.13.16 (uv 0.13.1 venvs under `~/.venvs-p29`), ruff 0.17.1, mypy 2.4.0, pytest 9.1.1.

## Summary of checks (author-run, 2026-10-16)

| Check | Command (from the workspace root, `V=~/.venvs-p29/py3.XX/bin`) | 3.11 | 3.12 | 3.13 |
|---|---|---|---|---|
| lint | `$V/ruff check .` | pass | pass | pass |
| format | `$V/ruff format --check .` | 214 files formatted | same | same |
| types (strict) | `$V/mypy src` | no issues, 58 files | same | same |
| tests | `$V/python -m pytest -q -p no:cacheprovider` | 1322 passed | 1322 passed | 1322 passed |

Baseline before P29 was 856 passed; P29 part 1 adds 466 tests. Existing tests are unmodified and pass. `$V/python scripts/verify_p28_fixtures.py` is unaffected.
Coverage of the new package (author-run, `pytest --cov=src/agent_reliability/experimental`): 95% line+branch overall (`values.py` 99%, `core.py` 99%, `_engine.py` 99%,
`rubric.py` 91%, `provider.py` 82%; the uncovered lines are mostly defensive type-error branches).

New test counts: unit S01 rubric 91, S01 values 82, S01 identity grammar 37, S02 core 19, S03 judge 51, S04 sync 9; contract vectors 148; property 7;
security 11; compat 11. Total 466.

## Files created or changed

Created: `docs/adr/0010-experimental-judge-adapter-amends-adr-0007-decision-9.md`;
`src/agent_reliability/experimental/judge/{__init__,errors,values,rubric,identity,provider,core,budget,_engine,judge,sync,testing}.py`;
`tests/fixtures/p29/{manifest,rubric_valid,rubric_invalid,judge_output_vectors,mapping_vectors,prompt_golden_jp1,failure_mapping_vectors,privacy_planted}.json`;
`tests/fakes/p29_judge.py`; `tests/unit/experimental_judge/{__init__,test_s01_rubric,test_s01_values,test_s01_identity_grammar,test_s02_core,test_s03_llm_judge,test_s04_sync_judge}.py`;
`tests/contract/test_p29_judge_vectors.py`; `tests/property/test_experimental_judge_properties.py`; `tests/security/test_experimental_judge_privacy.py`;
`tests/compat/test_experimental_judge_api.py`; `docs/P29_WORKSPACE_BASELINE.{md,sha256}`; this log.

Changed (documentation only): `docs/adr/0007-...md` (Status paragraph only, pointing to ADR-0010, body untouched, same practice as ADR-0004),
`docs/adr/README.md` (index rows), `docs/VERSIONING.md` (Experimental namespace paragraph), `docs/GA_CONTRACT.md` (Experimental namespace entry).

No existing source module is modified (guarded by `tests/compat/test_experimental_judge_api.py::test_no_existing_source_module_is_modified_by_p29`, which compares every
baseline `src/` file with `docs/P29_WORKSPACE_BASELINE.sha256`); `sdk/evaluator_runner.py` is additionally hash-pinned in
`test_p29_s03_runner_is_unchanged_by_the_judge`. `dependencies = []` unchanged; no extra added; `pyproject.toml` untouched. No existing compat snapshot touched.
`agent_reliability/experimental/__init__.py` is untouched (it still exports nothing; the judge is a sub-package).

## S00 - SDK ADR amendment (documentation only) - IMPLEMENTED (documentation review only, per plan)

| Criterion | Evidence |
|---|---|
| P29-S00-AC01 ADR cites ADR-0004, ADR-0007, ADR-0009 and the package; states it is Proposed | ADR-0010 "References" cites ADR-0004, 0005, 0007, 0009 and the P29 design package. **Deviation:** status is `Accepted`, not Proposed, because the owner approved G-C on 2026-10-16 (unsigned; approver and time not recorded; number provisional) |
| P29-S00-AC02 owner dispositions for P29-D01 and P29-D11 recorded; ADR states provider extra subject to P29-D12 and no wire member (P29-D02, P29-D04) | Status and Decision items 1, 5, 7, 8, 9 of ADR-0010 cite P29-D01, D02, D04, D11, D12; dispositions are in the owner record `P29_OWNER_DECISIONS_001.md` |
| docs/VERSIONING.md / GA_CONTRACT.md experimental entry (plan section 4) | both edited; GA_CONTRACT states "unreleased, not part of any stable inventory" |
| Test | documentation review only; no automated test beyond the compat snapshot referenced from GA_CONTRACT |

Open: ADR number is provisional (0010, next free); G-A/G-C approval records are unsigned.

## S01 - Value types and validation - IMPLEMENTED

Files: `values.py`, `rubric.py`, `identity.py`, `errors.py` (error taxonomy defined here, frozen by S03-AC02), `__init__.py`.

| Criterion | Tests |
|---|---|
| AC01 rubric loader accepts all `rubric_valid.json`, rejects each `rubric_invalid.json` with `ValueError`; immutable | `test_s01_rubric.py::test_p29_s01_ac01_*` (18 valid and 58 invalid fixture cases, JSON/file loader, immutability, source-mutation isolation) |
| AC02 identity composition satisfies both grammars | `test_s01_identity_grammar.py::test_p29_s01_ac02_*` (17 vectors against SDK `_OPAQUE_ID`, platform pattern copy and exporter `_OPAQUE`; `1.0.0+build5`, `v1:rc`, `a/b`, 128/129/200/201 chars; exporter pre-check acceptance; `model_label`/`salt` rejection; `deterministic` is always `False`: `test_s03_llm_judge.py::test_p29_s03_ac01_*`); property `test_identity_accept_iff_intersection_and_implies_all_grammars`, `test_identity_length_boundary` |
| AC03 request validation and config ranges; monetary budget without prices rejected | `test_s01_values.py::test_p29_s01_ac03_*` (role multiplicity, empty/over-32 parts, NUL, trust promotion, bool-as-int, NaN/inf, ranges); the "provider not declared `reports_tokens`" half of CON-11 is `test_s03_llm_judge.py::test_p29_s03_ac05_budget_requires_token_reporting_provider` |
| AC04 no `to_dict`; redacted repr/str; pickle/copy refused | `test_s01_values.py::test_p29_s01_ac04_*`; property `test_request_repr_never_contains_generated_text` |
| AC05 fingerprint stable; `pinned_fingerprint` mismatch raises at construction | `test_s01_rubric.py::test_p29_s01_ac05_*` |
| AC06 `dependencies = []`; no network/httpx/vendor import; existing snapshots unchanged and pass | `test_experimental_judge_api.py::test_core_dependencies_remain_empty_and_no_entry_points`, `::test_existing_compat_snapshots_are_unchanged_by_p29`; `test_experimental_judge_privacy.py::test_pg3_importing_the_namespace_pulls_in_no_network_or_vendor_library` |

Deviations / decisions (see also the consolidated list below): `JudgePolicy.min_confidence` defaults to `None` (rubric value), not `MEDIUM`; `salt` uses the intersection grammar with
alphanumeric boundary characters; rubric loader resolves and requires an `unknown` code for every required non-answer role.

## S02 - Sans-IO core and fixtures - IMPLEMENTED

Files: `core.py` (prompt builder `jp1`, nonce, strict parser, verdict mapper, pre-check, repeat aggregator, reply interpretation); fixtures `judge_output_vectors.json`, `mapping_vectors.json`,
`prompt_golden_jp1.json`, plus `rubric_*` and `privacy_planted.json` (see "Fixtures").

| Criterion | Tests |
|---|---|
| AC01 prompt golden, byte for byte | `test_p29_judge_vectors.py::test_p29_s02_ac01_prompt_golden_byte_for_byte` (8 cases incl. redraw, delimiter lookalikes, role filtering, repair line, demotion) |
| AC02 parser accepts exactly valid vectors, rejects invalid with `JudgeInvalidOutputError` | `::test_p29_s02_ac02_ac03_parser_vectors` (60 cases: fenced, duplicate members, extra members, trailing text, wrong types, code not in rubric, verdict/code mismatch, depth 9, NaN/Infinity, citations, reason) |
| AC03 bounds at and beyond | `test_s02_core.py::test_p29_s02_ac03_*` (reply chars, reason 300, citations, depth 8/9, huge nesting) |
| AC04 nonce redraw; structure cannot be altered; untrusted always labelled; nothing in system message | `test_s02_core.py::test_p29_s02_ac04_*`; property `test_nonce_never_appears_in_any_part`; security tests |
| AC05 mapping vectors incl. confidence downgrade and repeats disagreement | `::test_p29_s02_ac05_mapping_vectors` (21 cases) |
| AC06 missing/empty required role yields pre-check UNKNOWN, no provider call | `test_s02_core.py::test_p29_s02_ac06_*`; vector `precheck-missing-context` (0 provider calls) |

Parser round trip: property `test_parse_round_trip`.

## S03 - Async LLMJudge, provider protocol, fake provider - IMPLEMENTED

Files: `provider.py` (`ProviderCall`, `ProviderReply`, `ProviderFinish`, `JudgeProvider`, `SyncJudgeProvider`, `CallableProvider`, `CallableSyncProvider`), `budget.py`
(`BudgetTracker`), `_engine.py` (sans-IO control-flow generator shared by both drivers), `judge.py` (`LLMJudge`), `testing.py` (`FakeProvider`, `FakeSyncProvider`, `HANG`, `judge_reply`,
`fixed_nonces`; not exported from the namespace root), `failure_mapping_vectors.json`.

| Criterion | Tests |
|---|---|
| AC01 `AsyncEvaluator`, `deterministic is False`, runs unchanged through `EvaluatorRunner.evaluate_async` | `test_s03_llm_judge.py::test_p29_s03_ac01_*` |
| AC02 every fault yields `EvaluationExecutionFailure(stage=EVALUATION, exception_type=literal)`, never a result | `test_p29_judge_vectors.py::test_p29_s03_ac02_failure_matrix_through_runner_async` (28 cases, R04-R13 except R14 which is S05); `test_s03_llm_judge.py::test_p29_s03_ac02_*`; property `test_outcome_is_exactly_result_or_failure_and_never_from_a_failure` |
| AC03 per-attempt timeout and total deadline on a virtual clock; `CancelledError`/BaseException propagate | `test_p29_s03_ac03_*` (virtual-clock loop in `tests/fakes/p29_judge.py`; KeyboardInterrupt itself is exercised on the sync driver in `test_p29_s04_keyboard_interrupt_propagates_and_failures_are_clean`, a `BaseException` subclass on the async driver) |
| AC04 retries only timeout/unavailable/rate-limited; full-jitter bounds; `retry_after` honoured and clamped; refusal/generic/limit not retried; invalid output uses `repair_attempts` only | `test_p29_s03_ac04_*` and the vectors |
| AC05 budget refuses before any provider call (R13), counts only provider-reported tokens | `test_p29_s03_ac05_*` |
| AC06 no request text in message, `__cause__`, `__context__`; `retain_cause=False` default | `test_p29_s03_ac06_*`, `test_experimental_judge_privacy.py` |
| AC07 only rubric roles reach the provider | `test_p29_s03_ac07_*` |
| AC08 over-limit input rejected, never truncated; `repeats=2/3` multiply calls exactly and follow CON-07 | `test_p29_s03_ac08_*`, vectors `repeats-*` |

R14 (`JudgeOverloadedError`) is defined (class, literal, snapshot) but is only raised by the S05 coordinator; it is not yet exercised through a fault.

## S04 - Sync driver - IMPLEMENTED

Files: `sync.py` (`SyncLLMJudge`; `CallableSyncProvider` is in `provider.py`).

| Criterion | Tests |
|---|---|
| AC01 `SyncEvaluator`; parity with async on every `judge_output_vectors`, `mapping_vectors`-driven and `failure_mapping_vectors` case | `test_p29_judge_vectors.py::test_p29_s04_ac01_sync_driver_parity_with_async` (28 cases) and `::test_p29_s04_ac01_parity_over_output_and_mapping_vectors` (all `gr-cit` output vectors); `test_s04_sync_judge.py::test_p29_s04_ac01_*`. Parity is structural: both drivers run the same `_engine.JudgeEngine` generator |
| AC02 late reply after the deadline yields `JudgeTimeoutError` and is discarded; no `asyncio.run` anywhere in the namespace (static check) | `test_s04_sync_judge.py::test_p29_s04_ac02_*`, `::test_p29_s04_no_asyncio_run_anywhere_in_the_namespace` (AST) |

## Fixtures (P29-CON-15)

`tests/fixtures/p29/` with a `manifest.json` of SHA-256 hashes (same layout as `tests/fixtures/p28/manifest.json`, checked by
`test_p29_judge_vectors.py::test_p29_fixture_manifest_hashes_match`). Present: `rubric_valid`, `rubric_invalid`, `judge_output_vectors`, `mapping_vectors`,
`prompt_golden_jp1`, `failure_mapping_vectors`, `privacy_planted`. **Not present (S09):** `wire_expectation_vectors.json`. The fixtures were produced by throwaway generator scripts and are
committed-as-data only; `prompt_golden_jp1.json` is a golden of the implementation's own output (hand-reviewed once, circular by nature; template changes must change `template_id`).
Each case has `id`, `input`, `expected`, `note`; every file carries a `schema` of the form `gentlity.fixture.*/1` (a P29 convention, not a platform contract).

## Deviations, interpretations and open questions (for the owner / reviewer)

1. ADR status `Accepted` instead of "Proposed" (S00-AC01), ADR number 0010 provisional (owner assigns), ADR-0007 Status paragraph edited (not its body).
2. `JudgePolicy.min_confidence: Confidence | None = None` (None defers to the rubric `min_confidence`). The contract sketch shows `= Confidence.MEDIUM` which would silently override a stricter rubric.
3. Token budgets also require `reports_tokens=True` (the contract states it for the monetary budget); otherwise a token budget would never trigger. `reports_tokens` is an attribute read with
   `getattr(provider, "reports_tokens", False)`, not a member of the `JudgeProvider` protocol.
4. `repeats > 1` requires `judge_disagreement` in the rubric's `unknown` codes (judge construction raises `ValueError`); CON 4.4 only mandates `low_confidence`, CON 8 lists `judge_abstained` and
   `judge_disagreement` as always present. `judge_abstained` is not enforced.
5. Repeat aggregation precedence: PASS and FAIL both present gives `judge_disagreement` even if an UNKNOWN is also present; otherwise the first UNKNOWN decision; otherwise (same outcome) the first call's
   code. Per-call confidence downgrade happens before aggregation. First captured `reason` wins. The contract text does not order these cases.
6. Missing-input rule: a required non-answer role is missing when no part of that role has non-empty text (zero length; whitespace-only counts as present, since stripping is not language-neutral).
   Code per role: explicit `missing_input_codes`, else the dimension default for that dimension's primary role; any other required role must be mapped explicitly or the rubric is invalid. The loaded rubric stores the resolved
   mapping so that equivalent documents have the same fingerprint. If several are missing the first in declared order wins.
7. `salt` accepts empty or the intersection grammar (alphanumeric first and last), not just the charset `[A-Za-z0-9._-]` of CON 9.
8. Nonce redraw is capped at 1000 draws (then `RuntimeError`); unreachable with `secrets`. A nonce source returning anything but 16 lowercase hex characters raises `ValueError`.
9. Extra API beyond the contract sketch, needed by part 2: `LLMJudge/SyncLLMJudge.evaluate_detailed()` returning `JudgeEvaluation(decision, stats, reason_text)`; content-free `JudgeStats` also attached to a raised `JudgeError` as `.stats`;
   `BudgetTracker` (shared budget object; `JudgeBudget` stays a pure config value); injectable `nonce_source`, `jitter`, and (sync) `monotonic`, `sleep`. All are Experimental.
10. A dimension mismatch or non-request value raises `ValueError`/`TypeError` from the judge as the contract says; through a bare `EvaluatorRunner` that becomes an execution failure with that `exception_type`.
    The S05 coordinator must validate before calling the runner so that these stay unrecorded programmer errors.
11. The "total length <= 6000" rubric rule is implemented but cannot be violated independently (12 criteria x 500 characters = 6000), so it has no separate invalid vector.
12. TOML rubric loading ("may" in CON 2.1) is not implemented.
13. `MIN_ATTEMPT_SECONDS = 0.001` is the smallest remaining time worth an attempt; the contract refers to "the attempt's minimum" without a value.
14. Tests of the sync driver use a manual clock; the async driver tests use a virtual-time event loop. Real-time behaviour under load, GIL effects and event-loop blocking are unmeasured.
15. `tests/compat/test_experimental_judge_api.py` includes two guard tests that read `docs/P29_WORKSPACE_BASELINE.sha256` (skipped when absent). They are scaffolding for the P29 workspace and
    must be revisited when the work is merged on top of a different baseline.
16. The plan names S00 `docs/ROADMAP.md` / README / `docs/EVALUATE.md` / `scripts/verify_release_artifacts.py` changes for later stages (S06, S12); none was made in part 1.

## Not started (part 2): S05 .. S12

S05 coordinator and `EvaluationScope`, S06 reference rubrics/examples/docs, S07 (optional), S08 (optional), S09, S10, S11, S12: NOT STARTED.
Pre-built pieces part 2 can use: `SamplingPolicy.decide`, `JudgeOverloadedError`, `BudgetTracker`, `evaluate_detailed`/`JudgeStats`, `FakeProvider`/`FakeSyncProvider`, the virtual-clock loop and `FakeMonotonic` in
`tests/fakes/p29_judge.py`, and the baseline hashes of `sdk/context.py`, `sdk/evaluator_runner.py`, `ports/event_sink.py` in `P29_WORKSPACE_BASELINE.md` section 1.2 for P29-S05-AC09(d).

---

# Part 2 (S05 onward). Entries are appended after each stage.

Owner/coordinator note (2026-10-16): G-A and G-C are recorded owner-approved in the platform governance docs; deviations 2, 3, 4 and 7 of part 1 are accepted as implementation
interpretations and are documented for the independent reviewer (no further owner loop). The ADR number 0010 stays provisional.

## S05 - JudgeCoordinator and EvaluationScope - IMPLEMENTED (author-run)

File: `src/agent_reliability/experimental/judge/coordinator.py` (`JudgeCoordinator`, `IndicatorBinding`, `EvaluationScope`, `EvaluationDisposition`, `JudgeObserver`,
`JudgeInvocationReport`, `CoverageReport`, `IndicatorCoverage`). Tests: `tests/unit/experimental_judge/test_s05_coordinator.py` (37), `test_s05_recording_gate.py` (8).
Helpers added to `tests/fakes/p29_judge.py` (`HealthSink`, `OverlapHandle`, `LegacyHandle`).

| Criterion | Evidence |
|---|---|
| AC01 sampling | `test_p29_s05_ac01_*` (pure, 5-sigma statistical bound over 20 000 ids, rate 0/1, NaN/negative/>1 rejected, unsampled records nothing and is observed) |
| AC02 dedupe | `test_p29_s05_ac02_*` |
| AC03 limits | `test_p29_s05_ac03_*` (peak concurrency equals `max_concurrency`; `max_pending` sheds with `JudgeOverloadedError` failure evidence; per-run bound; parameter bounds) |
| AC04 consistency under 64 | `test_p29_s05_ac04_no_lost_updates_across_64_tasks_in_separate_runs`, `test_p29_s05_ac09_*` (nonces unique, counters consistent) |
| AC05 cancel/drain | `test_p29_s05_ac05_*` (cancel records nothing and propagates, provider await cancelled, no leaked tasks; drain timeout records `JudgeTimeoutError` while the run is open; sync late completion discarded) |
| AC06 shared budget | `test_p29_s05_ac06_*` (documented overshoot bound `max_concurrency x per-call usage`) |
| AC07 reports | `test_p29_s05_ac07_*` |
| AC08 recording paths | `test_p29_s05_ac08_*` (real `RunHandle` with `HealthEvidenceSink`; handle type without `indicator=`; EventSink-only; degraded; closed; deterministic rejection) |
| AC09 serialization | `test_p29_s05_ac09_*`: (a) 64 asyncio evaluations and 64 `evaluate_sync` from 8 threads and a mixed run against one handle through `OverlapHandle` and `HealthSink` (overlap counters 0, exactly-once, health equals union of marked reasons), (b) provider and observer never run on a thread that is inside a record call, (c) late completion discarded, (d) hash guard of `context.py`, `evaluator_runner.py`, `event_sink.py` against the baseline manifest, (e) sink delay of 2 ms inside the gate while `max_concurrency` is still reached |

Design notes and deviations: capability detection (`indicator=`) is per handle type with a process-wide cache, made when the scope is created (not at coordinator construction, because the handle type is only known
then). `JudgeInvocationReport` has one extra field, `failure_evidence_delivered`, to carry "failure evidence not delivered". The async entry points (`evaluate`, `submit`) accept async evaluators only and
`evaluate_sync` sync evaluators only (TypeError otherwise, unrecorded). A dimension mismatch, unknown indicator or wrong type is a `ValueError`/`TypeError` before any state change. Cancellation of the
scope (`CancelledError` at exit) records nothing; a drain timeout records `JudgeTimeoutError` for unfinished work. `CoverageReport` (counters) is the local SG-3/SG-5 report; it has no "healthy" member by design.
`max_pending` counts evaluations waiting for a concurrency slot. Not run: any load test; timings in tests are real-time with small sleeps (5-20 ms) and virtual clocks only in S03 tests.

## S06 - Reference rubrics, example providers, documentation - IMPLEMENTED (author-run)

Files: `src/agent_reliability/experimental/judge/rubrics/*.json` (five reference rubrics as package data), `reference.py` (`load_reference_rubric`, `REFERENCE_RUBRIC_IDS`),
`examples/judge_providers.py` (EXAMPLE code: customer callable, OpenAI-compatible, Anthropic-compatible, local-runtime loopback; stdlib only; injected `post_json`; never imported by the package),
`examples/judge_fake_provider.py` (offline demo: PASS, FAIL, UNKNOWN, failure, coverage), `tests/fixtures/p29/reference_rubric_cases.json` (26 cases), docs: `docs/EVALUATE.md` section
"LLM-judge evaluators (EXPERIMENTAL)" (privacy statement, PASS meaning per dimension, SG-1..SG-6, cohort/identity, calibration, local-model walkthrough), README paragraph, ROADMAP note,
`scripts/verify_release_artifacts.py` (wheel must contain the judge package and the five rubric files; base-wheel probe loads them; edit is additive and sits on top of the P28 overlay edits).
Tests: `tests/unit/experimental_judge/test_s06_reference_and_examples.py` (AC01 5+26, AC02, AC03 subprocess run, AC04 static import and extras check, AC05 docs check, example provider shapes/error mapping).
AC05 is documented as manual; nothing contacts a model or network. README links stay package-index-safe (absolute https). Not run: the real-model walkthrough.

## S07 - Executor driver for stuck sync providers (optional) - IMPLEMENTED (author-run)

`executor.py` (`ExecutorSyncProvider`): daemon helper threads, bounded count (`max_threads`, beyond it `JudgeProviderUnavailableError`), deadline gives `JudgeTimeoutError`, late result discarded.
Tests `test_s07_s08_optional.py::test_p29_s07_*`. It is low-risk, uses only the standard library and changes no existing module. A thread blocked in the provider cannot be interrupted (documented in the module).

## S08 - StructuredOutputEvaluator (optional) - IMPLEMENTED (author-run)

`structured.py` plus `_schema.py` (shared `is_json_type`/`check_members`, now used by the judge-output parser as well; the 60 parser vectors still pass). Deterministic (`deterministic=True`), None gives UNKNOWN,
malformed configuration raises at construction. Reason codes `structured-output.valid|invalid|no-data` are a P29 convention. Tests `test_p29_s08_*`.

## S09 - P28 wiring and cross-repository conformance - IMPLEMENTED for the capture/mock-transport path (author-run); live delivery NOT EXERCISED

Files: `tests/fixtures/p29/wire_expectation_vectors.json` (16 cases: the two contract section 11 examples, pass/unknown/pre-check/invalid-output, and all 10 failure classes), `tests/contract/test_p29_wire_conformance.py`.
Sink exercised: the working-tree `HTTPEventSink` (P28 exporter, uncommitted, **the D-1 TLS fix is present in this working tree**, identical to the original tree's; an earlier version of this text wrongly said "unfixed", corrected after the re-sync) over `httpx.MockTransport`. The report makes **no** claim about TLS-verification handling or about delivery to a real platform.
No platform code is imported into the SDK. The cross-repository check (AC03) runs the platform's `EvidenceEnvelopeV2` model in a separate scratch virtualenv (`P29_PLATFORM_ROOT` and `P29_PLATFORM_PYTHON`,
`PYTHONDONTWRITEBYTECODE=1`, `python -B`) against `<workspace>/agent-reliability-platform-integration/src` (read-only; its `git status --porcelain` line count was 51 before and after). Without those
environment variables the test is skipped and must be read as NOT_EXERCISED.
AC01/AC02: vectors incl. provenance `deterministic=false`, reason codes, `evaluation_execution_failure` with indicator, final health `unavailable`; an EventSink-only sink gets no failure payload (local health only).
AC04/AC05: planted strings and injection never reach any request body, snapshot repr, coverage report or diagnostic; no member can be added. AC06: P28 fixtures, exporter sources and P28 documents are hash-identical to the baseline.
Decision recorded: the P28 platform parity vectors (`v2_digest_vectors_specification_only.json`) are exporter-owned and are not duplicated; the platform V2 model check replaces them for P29 payloads.

## S10 - Local calibration harness - IMPLEMENTED (author-run)

Files: `calibration.py` (`CalibrationCase`, `load_cases`, `run_calibration`, `run_calibration_async`, `CalibrationReport`, `compare_reports`, `ReportComparison`, `wilson_interval`), `schemas/calibration-case.schema.json`,
`schemas/calibration-report.schema.json` (package data), `_jsonschema.py` (stdlib subset validator that rejects unsupported keywords), fixture `calibration_known_confusion.json` (21 synthetic cases, hand-computed expectations),
`tests/unit/experimental_judge/test_s10_calibration.py` (33). `JudgeEvaluation` gained `confidence` (lowest across repeats) so the confidence-calibration metric can be computed (local only).
AC01 schemas validated both ways; AC02 every metric of the strategy section 5 that is computable from the dataset (confusion matrix with a separate FAILURE column, FN/FP/over-confident, abstention overall and by human class,
accuracy on answered, precision/recall, judge-human agreement and Cohen's kappa, repeatability by `repetitions`, confidence calibration, failure counts by class, token/latency summaries) matches hand-computed values;
AC03 adversarial and borderline slices are separate and the injection fixtures are in the dataset; AC04 planted strings absent from the report JSON, repr and case repr, fingerprint/model label/template id recorded;
AC05 `compare_reports` lists flipped `case_id`s and net FN/FP/UNKNOWN/FAILURE change and has no verdict field (tested by field name); AC06 sockets are monkeypatched to fail during a run and a static import check applies.
Interpretations: slices are headline (clear + ambiguous), borderline, adversarial; "answered" means the judge returned PASS or FAIL; fewer cases than the 12 matrix cells (3 human labels x 4 judge columns) means
`insufficient_for_rates` and counts only (also for kappa); the confusion matrix uses the first repetition. Not implemented: citation-validity (needs a human spot-check set) and judge-judge agreement across two live judges
(only between two reports via `compare_reports`). The harness never uploads or writes a dataset; it writes nothing at all (the caller decides what to do with `to_json()`).

## S11 - Pilot end-to-end (SDK-side artifacts only) - PARTIAL (local artifacts IMPLEMENTED; platform criteria NOT_EXERCISED)

Files: `examples/judge_pilot_demo.py` (scripted fake judges, two-question scenario plus a stopped provider, JSON-lines capture of the exporter's envelopes over a mocked transport),
`examples/judge_pilot_replay.py` (dry-run validation by default; `--post` only on explicit request, https or loopback only), `docs/P29_PILOT_RUNBOOK.md` (prerequisites, commands, expected output, fallbacks,
semantic limits, SG-1..SG-6 status), `tests/unit/experimental_judge/test_s11_pilot_artifacts.py` (4; the POST path is tested only against an in-process loopback stub).
Not done by design: any run against a platform, shared TEST or production; PL1; P3/P4/P6/P7 reads. SG-1..SG-6 status is in the runbook: none of the pilot conditions is satisfied.

## Phase 4 - measurement integrity - IMPLEMENTED in SDK scope (author-run)

`tests/unit/experimental_judge/test_phase4_measurement_integrity.py` (22 tests): failures of all 10 classes never become outcomes (coordinator level, failure evidence only, coverage shows execution failures only);
UNKNOWN never becomes PASS (property tests over `map_verdict` and `aggregate_repeats`, end-to-end low-confidence); 99 failures plus one PASS shows reliability 1.0 beside 1% determinate coverage and 99% failures;
no member of the coverage/comparison/report classes names a health/ok/score/verdict value; budget exhaustion and overload are visible in observer, coverage and failure evidence; one failure marks the whole run
`UNAVAILABLE` through the existing recorder (`MeasurementHealthReport` has no indicator dimension) and a separate run stays `healthy`; SG-1 defaults pinned; a grep-style scan finds no accuracy/calibration/readiness claim in
README, EVALUATE, ADR-0010, GA_CONTRACT, VERSIONING, ROADMAP, the judge package, the examples and the P29 usage/runbook documents (the scanner is itself tested to catch claims).

---

# Consolidated status after part 2 (author-run; independent verification NO; pilot-ready NO; released NO)

The earlier section "Not started (part 2): S05 .. S12" above is superseded by this table.

| Stage | Status | Notes |
|---|---|---|
| S00 | IMPLEMENTED | ADR-0010 (status Accepted by owner G-C instruction, unsigned, number provisional), VERSIONING/GA_CONTRACT entries |
| S01 | IMPLEMENTED | |
| S02 | IMPLEMENTED | |
| S03 | IMPLEMENTED | |
| S04 | IMPLEMENTED | |
| S05 | IMPLEMENTED | single per-scope `threading.Lock` recording gate |
| S06 | IMPLEMENTED | five uncalibrated reference rubrics (package data), example providers (example code), docs; local-model walkthrough documented, manual and NOT run |
| S07 | IMPLEMENTED (optional) | |
| S08 | IMPLEMENTED (optional) | |
| S09 | IMPLEMENTED for the capture / mocked-transport path; platform model check executed read-only; live delivery NOT_EXERCISED | exporter D-1 fix present in the uncommitted working tree (nothing committed) |
| S10 | IMPLEMENTED | |
| S11 | PARTIAL | SDK-side local demo, JSON-lines capture, replay validator and runbook only; every platform criterion NOT_EXERCISED; all SG conditions NOT SATISFIED for a pilot |
| S12 | PARTIAL | traceability matrix and user docs done; benchmark NOT RUN; independent review BLOCKED; release gate BLOCKED |
| Phase 4 | IMPLEMENTED in SDK scope | see `test_phase4_measurement_integrity.py` |

Counts: 69 criteria: PASS 59, PARTIAL (SDK-side PASS, platform part NOT_EXERCISED) 3, NOT_EXERCISED 5, BLOCKED 2, FAIL 0 (`docs/P29_ACCEPTANCE_MATRIX.md`). Test totals: 1523 passed on 3.11, 3.12 and 3.13 (platform check enabled), 856 pre-existing tests unchanged
(`docs/P29_TEST_EVIDENCE.md`).

## Part 2 deviations, interpretations and open points (for the independent reviewer)

1. Part 1 deviations 2, 3, 4 and 7 (min_confidence default `None`; token budgets need `reports_tokens`; `repeats > 1` needs `judge_disagreement`; salt grammar) are accepted by the coordinator as implementation interpretations and are kept.
2. Capability detection of `indicator=` is per handle type, performed when the scope is created (the handle type is unknown at coordinator construction), with a process-wide cache.
3. `JudgeInvocationReport.failure_evidence_delivered` is an extra field; "delivered" means "handed to the handle together with the indicator". Whether the sink forwards it depends on the sink (an EventSink-only sink never produces wire failure evidence).
4. `evaluate`/`submit` require async evaluators and `evaluate_sync` sync ones (TypeError otherwise); unknown indicator, dimension mismatch and wrong request type are unrecorded programmer errors.
5. App cancellation of a scope records nothing (R17); a drain timeout records `JudgeTimeoutError` and discards late completions (R19). Sync threads cannot be interrupted and may outlive the scope.
6. `max_pending` counts evaluations waiting for a concurrency slot; shed evaluations are recorded as `JudgeOverloadedError` failures.
7. `CoverageReport`/`IndicatorCoverage` are local only and deliberately have no health/ok member; `describe()` always prints reliability beside determinate coverage, failure and UNKNOWN rates.
8. `StructuredOutputEvaluator` reason codes `structured-output.valid|invalid|no-data` and the shared `_schema` helpers are P29 conventions; the judge-output parser now uses the shared helpers (60 vectors still pass).
9. Calibration: slices, "answered" and the `insufficient_for_rates` rule are interpretations (see S10); citation-validity and cross-judge agreement from two live judges are not computed.
10. The platform wire check uses a scratch virtualenv with the platform's own dependencies against the read-only integration worktree; no platform code is imported into the SDK or its tests unless the two environment variables are set.
11. The original SDK tree gained P28 D-1 test/doc/report changes from another session while part 2 ran (see `docs/P29_TEST_EVIDENCE.md` section 8). **Superseded:** the overlay was re-synced (section "Re-sync of the P28-owned overlay"); the D-1 `_failure()` fix itself was already in the first baseline, so earlier statements that D-1 was unfixed in the workspace were wrong and are corrected.
12. `scripts/verify_release_artifacts.py` edits are additive (wheel must contain the judge package, rubrics and schemas; base-wheel probe loads the rubrics) and sit on top of the P28 overlay edits.
13. ruff formats Python blocks in Markdown, so the `docs/EVALUATE.md` quick-start block is formatted accordingly (it is not executed).

## SG-1..SG-6 (status)

IMPLEMENTED-in-SDK: SG-1 (limits, budgets, defaults, observable budget/overload), SG-3 (coverage report), SG-5 (observer and counters). PROCESS-GATE: SG-2, SG-4, SG-6 and the customer/pilot half of SG-1, SG-3, SG-5. Pilot conditions: **NOT SATISFIED**
for all six (`docs/P29_PILOT_RUNBOOK.md` section 4).


---

## Review remediation (after docs/P29_INDEPENDENT_REVIEW.md; author-run, final targeted verification pending)

Reviewer verdict: APPROVE_WITH_REQUIRED_CORRECTIONS, no BLOCKER/HIGH. The reviewer's report is saved verbatim and untouched. Full per-finding dispositions, files, tests and mutation results: `docs/P29_REVIEW_REMEDIATION_REPORT.md`.
Summary: fixed F-1 (`submit()` outside a loop), F-3 (re-entrancy now raises `RuntimeError`; gate constraints documented), F-4 (example adapter refuses redirects and caps responses), F-5 (keyed assertions; 64 parallel runs), F-6 (admission and drain tests), F-8 (C1 vectors),
F-10 (sync waiter abandons its slot), F-12 (virtual-time guard), F-13 (jitter validation, weak capability cache, README placement, evidence counts, workspace artifacts); documented F-2, F-9, F-11, `judge_abstained` and the CRLF strictness; **declined F-7** (salt stays stricter than the contract because the plan's S01-AC02 lists the salt among values that must satisfy the identity grammars; documented).
Kept as reviewer-accepted interpretations: D2, D3, D4, per-handle-type capability detection, the `evaluate`/`evaluate_sync` split. The ADR number 0010 stays provisional and owner confirmation of the ADR number and of the G-C wording is pending.

Corrected figures (supersede the older per-stage counts in this log): `ruff format --check` 239 files; pytest **1548 passed** (platform check enabled) and **1547 passed + 1 skipped** (default) on 3.11.17, 3.12.15 and 3.13.16; the pre-existing suite alone 856 passed; stress/concurrency set 82 tests x 3 repeats x 3 Pythons all passed;
full `scripts/verify_release_artifacts.py` passed; 13 of 13 regression mutants killed. Details and the raw log: `docs/P29_TEST_EVIDENCE.md` sections 9 and 10; criterion matrix: `docs/P29_ACCEPTANCE_MATRIX.md` (59 PASS, 3 PARTIAL, 5 NOT_EXERCISED, 2 BLOCKED, 0 FAIL; still no independent verification of any PASS).
Independent verification status: **PARTIAL** (reviewer sampled; remediation re-verification pending). Pilot-ready: NO. Released: NO.


---

## Re-sync of the P28-owned overlay (2026-10-16, author-run; reviewers verified the pre-re-sync tree)

Both reviewers noted drift between the workspace baseline and the original SDK tree. Exact per-file diff, commands, three-way reconciliation and the new manifest `docs/P29_WORKSPACE_BASELINE_RESYNC.sha256` are in `docs/P29_WORKSPACE_BASELINE.md` (section "Re-sync").
Summary of the drift: `docs/HTTP_EXPORTER.md`, `pyproject.toml` (dev-only `cryptography>=42`), `scripts/verify_release_artifacts.py` (`_assert_no_private_keys`), `tests/unit/test_http_exporter_tls_real.py` (certificates generated at test time), `CHANGELOG.md` and four P28 reports added, the 11 throwaway `tests/fixtures/tls/*` files removed.
The exporter source files, including the D-1 `_failure()` fix, were **byte-identical** to the first baseline (the fix was already there), and `sdk/context.py`, `sdk/evaluator_runner.py` and `ports/event_sink.py` did not change, so no pinned hash changed. Only `scripts/verify_release_artifacts.py` was edited by both sides:
reconciled from the upstream file plus the two additive P29 hunks. The guards now read the re-synced manifest (`tests/fakes/p29_baseline.py`).

Results after the re-sync (`docs/P29_TEST_EVIDENCE.md` section 11): ruff, format and mypy clean; 1549 passed (platform check enabled) / 1548 passed + 1 skipped (default) on 3.11.17, 3.12.15, 3.13.16; pre-existing suite alone 857 passed; stress set (98 tests) x3 passed; full `verify_release_artifacts.py` passed.
S09 (conformance, including the read-only platform V2 model check) and S11 (demo, capture, replay) pass against the D-1-fixed exporter (29 tests).

G-D (plan section 1): the condition "an SDK exporter with the HIGH defect D-1 fixed **in the real SDK source**" is, per the reports in the original tree, met **in its uncommitted working tree**. Verdict strings, verbatim:
* `docs/P28_SDK_D1_INDEPENDENT_REVIEW.md`: "**D-1 FIXED AND VERIFIED** for the production code."
* `docs/P28_SDK_D1_TARGETED_VERIFICATION.md`: "## Verdict: VERIFIED".
* `docs/P28_SDK_D1_REMEDIATION_REPORT.md`: "D-1 is fixed in the working tree of the real SDK; **nothing is committed, released or published**".
* `docs/P28_SDK_EXPORTER_RELEASE_REVIEW.md` (whole exporter change set): "## Verdict: FINDINGS TO FIX" (BLOCKER 0, HIGH 1 release-pipeline defect, MEDIUM 4, LOW 6, INFORMATIONAL 4).
These do not satisfy the rest of G-D (integrated PC-1 + PC-2 platform tree, authorization to commit/merge) or G-E; nothing is committed; the exporter change set as a whole has open release-review findings. P29 makes no claim beyond them and still makes no TLS or live-delivery claim (its S09 evidence uses a mocked transport).

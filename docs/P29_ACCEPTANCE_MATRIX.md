# P29 acceptance-criteria matrix (author-run)

Generated 2026-10-16 (after the P28 overlay re-sync) from the executed JUnit results of `docs/P29_TEST_EVIDENCE.md` (Python 3.11.17, 3.12.15, 3.13.16). **Status words:**

| Dimension | State |
|---|---|
| Implemented | per row below (author-run) |
| Independently verified | **PARTIAL: an independent reviewer sampled the work (docs/P29_INDEPENDENT_REVIEW.md, verdict APPROVE_WITH_REQUIRED_CORRECTIONS, no BLOCKER/HIGH); the independent reviewers verified the PRE-re-sync tree; the re-sync of the P28-owned overlay (2026-10-16, see docs/P29_WORKSPACE_BASELINE.md section 'Re-sync') and all results below are author-run. No PASS below is an independent verification.** |
| Pilot-ready | **NO** (SG-1..SG-6 not satisfied; no platform run) |
| Released | **NO** (nothing committed, merged, published or deployed) |

Result words: PASS = every mapped test executed and passed on all three Pythons; FAIL; NOT_EXERCISED = not executed here; BLOCKED = needs a human gate. Test cells are `p/f/s` counts (passed/failed/skipped) per Python. Test ids are pytest node-name prefixes (parametrized cases are counted individually).

## 1. Per-criterion matrix

| Criterion | What is required | Implementation | Test ids (count) | Result | Evidence (3.11 / 3.12 / 3.13) | Outstanding |
|---|---|---|---|---|---|---|
| P29-S00-AC01 | ADR draft cites ADR-0004/0007/0009 and the package | docs/adr/0010-experimental-judge-adapter-amends-adr-0007-decision-9.md | `test_p29_s00_ac01`, `test_p29_s00_historical` (2 tests) | PASS. Status is Accepted (owner G-C instruction 2026-10-16, unsigned, number provisional), not Proposed: documented deviation. | 3.11: 2p/0f/0s; 3.12: 2p/0f/0s; 3.13: 2p/0f/0s | Independent review of the ADR; owner may renumber. |
| P29-S00-AC02 | Owner dispositions for P29-D01/D11 recorded; ADR states provider extra subject to P29-D12 and no wire member | ADR-0010; docs/VERSIONING.md; docs/GA_CONTRACT.md | `test_p29_s00_ac02`, `test_p29_s00_versioning` (2 tests) | PASS | 3.11: 2p/0f/0s; 3.12: 2p/0f/0s; 3.13: 2p/0f/0s | - |
| P29-S01-AC01 | Rubric loader accepts valid, rejects invalid with ValueError; immutable | src/agent_reliability/experimental/judge/rubric.py | `test_p29_s01_ac01` (86 tests) | PASS | 3.11: 86p/0f/0s; 3.12: 86p/0f/0s; 3.13: 86p/0f/0s | - |
| P29-S01-AC02 | Identity composition satisfies SDK and wire/exporter grammars (intersection) | src/agent_reliability/experimental/judge/identity.py | `test_p29_s01_ac02`, `test_identity_accept_iff`, `test_identity_length_boundary` (39 tests) | PASS | 3.11: 39p/0f/0s; 3.12: 39p/0f/0s; 3.13: 39p/0f/0s | - |
| P29-S01-AC03 | Request/config validation; monetary budget needs prices and token reporting | src/agent_reliability/experimental/judge/values.py; judge.py | `test_p29_s01_ac03`, `test_p29_s03_ac05_budget_requires` (80 tests) | PASS | 3.11: 80p/0f/0s; 3.12: 80p/0f/0s; 3.13: 80p/0f/0s | - |
| P29-S01-AC04 | No to_dict; redacted repr; pickle/copy refused | src/agent_reliability/experimental/judge/values.py | `test_p29_s01_ac04`, `test_request_repr_never_contains` (4 tests) | PASS | 3.11: 4p/0f/0s; 3.12: 4p/0f/0s; 3.13: 4p/0f/0s | - |
| P29-S01-AC05 | Fingerprint stable; pinned_fingerprint mismatch raises | src/agent_reliability/experimental/judge/rubric.py | `test_p29_s01_ac05` (5 tests) | PASS | 3.11: 5p/0f/0s; 3.12: 5p/0f/0s; 3.13: 5p/0f/0s | - |
| P29-S01-AC06 | dependencies = []; no network/vendor import; existing snapshots unchanged | pyproject.toml (unchanged) | `test_core_dependencies_remain_empty`, `test_existing_compat_snapshots_are_unchanged`, `test_pg3_importing`, `test_importing_the_namespace_loads_no_third_party` (4 tests) | PASS | 3.11: 4p/0f/0s; 3.12: 4p/0f/0s; 3.13: 4p/0f/0s | - |
| P29-S02-AC01 | Prompt builder reproduces golden cases byte for byte | src/agent_reliability/experimental/judge/core.py | `test_p29_s02_ac01` (8 tests) | PASS | 3.11: 8p/0f/0s; 3.12: 8p/0f/0s; 3.13: 8p/0f/0s | - |
| P29-S02-AC02 | Parser accepts valid vectors, rejects invalid with JudgeInvalidOutputError | src/agent_reliability/experimental/judge/core.py | `test_p29_s02_ac02_ac03_parser_vectors` (67 tests) | PASS | 3.11: 67p/0f/0s; 3.12: 67p/0f/0s; 3.13: 67p/0f/0s | - |
| P29-S02-AC03 | Bounds hold at and beyond limit | src/agent_reliability/experimental/judge/core.py | `test_p29_s02_ac03` (5 tests) | PASS | 3.11: 5p/0f/0s; 3.12: 5p/0f/0s; 3.13: 5p/0f/0s | - |
| P29-S02-AC04 | Nonce redraw; structure cannot be altered; trust labels; nothing in system message | src/agent_reliability/experimental/judge/core.py | `test_p29_s02_ac04`, `test_nonce_never_appears` (9 tests) | PASS | 3.11: 9p/0f/0s; 3.12: 9p/0f/0s; 3.13: 9p/0f/0s | - |
| P29-S02-AC05 | Mapping vectors incl. confidence downgrade and repeats disagreement | src/agent_reliability/experimental/judge/core.py | `test_p29_s02_ac05` (21 tests) | PASS | 3.11: 21p/0f/0s; 3.12: 21p/0f/0s; 3.13: 21p/0f/0s | - |
| P29-S02-AC06 | Missing/empty required role gives pre-check UNKNOWN, no provider call | src/agent_reliability/experimental/judge/core.py; _engine.py | `test_p29_s02_ac06`, `test_p29_s03_precheck_makes_no_provider_call` (4 tests) | PASS | 3.11: 4p/0f/0s; 3.12: 4p/0f/0s; 3.13: 4p/0f/0s | - |
| P29-S03-AC01 | LLMJudge is an AsyncEvaluator and runs unchanged through the runner | src/agent_reliability/experimental/judge/judge.py | `test_p29_s03_ac01` (2 tests) | PASS | 3.11: 2p/0f/0s; 3.12: 2p/0f/0s; 3.13: 2p/0f/0s | - |
| P29-S03-AC02 | Every fault becomes an EvaluationExecutionFailure with the contract literal; never a result | src/agent_reliability/experimental/judge/_engine.py | `test_p29_s03_ac02`, `test_outcome_is_exactly_result_or_failure` (38 tests) | PASS. R14 (overload) is exercised in S05/Phase 4 tests. | 3.11: 38p/0f/0s; 3.12: 38p/0f/0s; 3.13: 38p/0f/0s | - |
| P29-S03-AC03 | Timeout and deadline on a virtual clock; CancelledError/BaseException propagate | src/agent_reliability/experimental/judge/judge.py | `test_p29_s03_ac03` (4 tests) | PASS | 3.11: 4p/0f/0s; 3.12: 4p/0f/0s; 3.13: 4p/0f/0s | - |
| P29-S03-AC04 | Retries only transient; full jitter; retry_after clamped; repair separate | src/agent_reliability/experimental/judge/_engine.py | `test_p29_s03_ac04` (6 tests) | PASS | 3.11: 6p/0f/0s; 3.12: 6p/0f/0s; 3.13: 6p/0f/0s | - |
| P29-S03-AC05 | Budget refuses before any call; counts only provider-reported tokens | src/agent_reliability/experimental/judge/budget.py | `test_p29_s03_ac05` (6 tests) | PASS | 3.11: 6p/0f/0s; 3.12: 6p/0f/0s; 3.13: 6p/0f/0s | - |
| P29-S03-AC06 | No request text in message, __cause__, __context__; retain_cause False | src/agent_reliability/experimental/judge/_engine.py; errors.py | `test_p29_s03_ac06` (9 tests) | PASS | 3.11: 9p/0f/0s; 3.12: 9p/0f/0s; 3.13: 9p/0f/0s | - |
| P29-S03-AC07 | Only rubric roles reach the provider | src/agent_reliability/experimental/judge/core.py | `test_p29_s03_ac07` (2 tests) | PASS | 3.11: 2p/0f/0s; 3.12: 2p/0f/0s; 3.13: 2p/0f/0s | - |
| P29-S03-AC08 | Over-limit input rejected, never truncated; repeats multiply calls exactly | src/agent_reliability/experimental/judge/_engine.py | `test_p29_s03_ac08` (3 tests) | PASS | 3.11: 3p/0f/0s; 3.12: 3p/0f/0s; 3.13: 3p/0f/0s | - |
| P29-S04-AC01 | SyncLLMJudge satisfies SyncEvaluator; parity with async over all vectors | src/agent_reliability/experimental/judge/sync.py | `test_p29_s04_ac01` (30 tests) | PASS | 3.11: 30p/0f/0s; 3.12: 30p/0f/0s; 3.13: 30p/0f/0s | - |
| P29-S04-AC02 | Late reply is a timeout and discarded; no asyncio.run in the namespace | src/agent_reliability/experimental/judge/sync.py | `test_p29_s04_ac02`, `test_p29_s04_no_asyncio_run` (4 tests) | PASS | 3.11: 4p/0f/0s; 3.12: 4p/0f/0s; 3.13: 4p/0f/0s | - |
| P29-S05-AC01 | Sampling pure; rate 0/1; statistical bound; invalid rates rejected | src/agent_reliability/experimental/judge/values.py; coordinator.py | `test_p29_s05_ac01`, `test_p29_s01_ac03_sampling`, `test_sampling_is_pure` (14 tests) | PASS | 3.11: 14p/0f/0s; 3.12: 14p/0f/0s; 3.13: 14p/0f/0s | - |
| P29-S05-AC02 | Second evaluation of (run, indicator) raises ValueError and records nothing | src/agent_reliability/experimental/judge/coordinator.py | `test_p29_s05_ac02` (2 tests) | PASS | 3.11: 2p/0f/0s; 3.12: 2p/0f/0s; 3.13: 2p/0f/0s | - |
| P29-S05-AC03 | max_concurrency, max_pending -> JudgeOverloadedError, max_evaluations_per_run | src/agent_reliability/experimental/judge/coordinator.py | `test_p29_s05_ac03`, `test_overload_shedding` (4 tests) | PASS | 3.11: 4p/0f/0s; 3.12: 4p/0f/0s; 3.13: 4p/0f/0s | - |
| P29-S05-AC04 | 64 concurrent: dedupe, budget, counters consistent; nonces never reused | src/agent_reliability/experimental/judge/coordinator.py | `test_p29_s05_ac04`, `test_p29_s05_ac09_async`, `test_p29_s05_ac09_sync`, `test_p29_s05_ac09_mixed` (6 tests) | PASS | 3.11: 6p/0f/0s; 3.12: 6p/0f/0s; 3.13: 6p/0f/0s | - |
| P29-S05-AC05 | Cancel records nothing and propagates; drain timeout -> JudgeTimeoutError; no leaks | src/agent_reliability/experimental/judge/coordinator.py | `test_p29_s05_ac05` (4 tests) | PASS | 3.11: 4p/0f/0s; 3.12: 4p/0f/0s; 3.13: 4p/0f/0s | - |
| P29-S05-AC06 | Shared budget enforced across concurrent evaluations within the overshoot bound | src/agent_reliability/experimental/judge/budget.py | `test_p29_s05_ac06` (2 tests) | PASS | 3.11: 2p/0f/0s; 3.12: 2p/0f/0s; 3.13: 2p/0f/0s | - |
| P29-S05-AC07 | Reports content-free; observer errors suppressed and counted; reason only if captured | src/agent_reliability/experimental/judge/coordinator.py | `test_p29_s05_ac07` (2 tests) | PASS | 3.11: 2p/0f/0s; 3.12: 2p/0f/0s; 3.13: 2p/0f/0s | - |
| P29-S05-AC08 | record_evaluation / record_evaluation_failure(indicator) with capability fallback; degraded/closed; deterministic rejected | src/agent_reliability/experimental/judge/coordinator.py | `test_p29_s05_ac08` (6 tests) | PASS | 3.11: 6p/0f/0s; 3.12: 6p/0f/0s; 3.13: 6p/0f/0s | - |
| P29-S05-AC09 | Recording serialized per RunHandle (stress >=64 tasks and 8 threads; no await/provider/observer in gate; late completion discarded; RunHandle unchanged; slow sink; docs state sinks/diagnostic handlers run inside the gate and must be non-blocking) | src/agent_reliability/experimental/judge/coordinator.py (single threading.Lock per scope; re-entry raises RuntimeError) | `test_p29_s05_ac09`, `test_f3_`, `test_f6_drain`, `test_review_f2_f3` (11 tests) | PASS. Review F-3: the documentation half (AC09(e)) was missing at first review and is now in docs/EVALUATE.md, ADR-0010 consequences and the runbook; a re-entrancy guard replaces a silent deadlock. Drain-time recording overlap is now tested (F-6). Note: test_p29_s05_ac09_c_nothing_reaches_the_handle_after_drain only checks that a closed scope refuses work; late-completion discard itself is covered by the S05-AC05 sync drain test. | 3.11: 11p/0f/0s; 3.12: 11p/0f/0s; 3.13: 11p/0f/0s | - |
| P29-S06-AC01 | Each reference rubric validates and passes its fixtures; declares inputs, codes, min_confidence | src/agent_reliability/experimental/judge/rubrics/*.json; reference.py | `test_p29_s06_ac01` (27 tests) | PASS | 3.11: 27p/0f/0s; 3.12: 27p/0f/0s; 3.13: 27p/0f/0s | - |
| P29-S06-AC02 | Rubric docs state PASS meaning and uncalibrated; task-completion states R1 | docs/EVALUATE.md; rubric descriptions | `test_p29_s06_ac02` (1 tests) | PASS | 3.11: 1p/0f/0s; 3.12: 1p/0f/0s; 3.13: 1p/0f/0s | - |
| P29-S06-AC03 | Fake-provider example runs in CI and shows PASS, FAIL, UNKNOWN and a failure | examples/judge_fake_provider.py | `test_p29_s06_ac03` (1 tests) | PASS | 3.11: 1p/0f/0s; 3.12: 1p/0f/0s; 3.13: 1p/0f/0s | - |
| P29-S06-AC04 | Provider examples not imported by core; no extra | examples/judge_providers.py | `test_p29_s06_ac04`, `test_p29_s06_openai`, `test_p29_s06_anthropic`, `test_p29_s06_local`, `test_p29_s06_example_http`, `test_p29_s06_example_transport`, `test_p29_s06_customer`, `test_p29_s06_example_provider_drives` (14 tests) | PASS | 3.11: 14p/0f/0s; 3.12: 14p/0f/0s; 3.13: 14p/0f/0s | - |
| P29-S06-AC05 | Local-model walkthrough documented with prerequisites, marked manual | docs/EVALUATE.md | `test_p29_s06_ac05` (1 tests) | PASS. The walkthrough itself was NOT run (manual, needs a local model). | 3.11: 1p/0f/0s; 3.12: 1p/0f/0s; 3.13: 1p/0f/0s | - |
| P29-S07-AC01 | Hung blocking call abandoned; daemon, bounded helper threads; late results cannot mutate terminal state | src/agent_reliability/experimental/judge/executor.py | `test_p29_s07` (4 tests) | PASS. Optional stage, implemented. | 3.11: 4p/0f/0s; 3.12: 4p/0f/0s; 3.13: 4p/0f/0s | - |
| P29-S08-AC01 | Deterministic evaluator over a parsed object: keys, types, enums; None gives UNKNOWN; malformed config raises | src/agent_reliability/experimental/judge/structured.py | `test_p29_s08_ac01` (11 tests) | PASS. Optional stage, implemented. | 3.11: 11p/0f/0s; 3.12: 11p/0f/0s; 3.13: 11p/0f/0s | - |
| P29-S08-AC02 | Shares the judge-output validator; stdlib only | src/agent_reliability/experimental/judge/_schema.py; structured.py | `test_p29_s08_ac02` (1 tests) | PASS | 3.11: 1p/0f/0s; 3.12: 1p/0f/0s; 3.13: 1p/0f/0s | - |
| P29-S09-AC01 | Judge results flow to the sink as EvaluationRecorded with deterministic=False and the contract reason_code | tests/fixtures/p29/wire_expectation_vectors.json | `test_p29_s09_ac01` (17 tests) | PASS. Mocked-transport exporter path only. | 3.11: 17p/0f/0s; 3.12: 17p/0f/0s; 3.13: 17p/0f/0s | - |
| P29-S09-AC02 | HealthEvidenceSink gets failures with indicator, final health UNAVAILABLE; EventSink-only is local only | coordinator.py; exporter (P28 overlay, unchanged) | `test_p29_s09_ac01_ac02`, `test_p29_s09_ac02`, `test_p29_s05_ac08` (23 tests) | PASS | 3.11: 23p/0f/0s; 3.12: 23p/0f/0s; 3.13: 23p/0f/0s | - |
| P29-S09-AC03 | Every wire vector validates against the platform V2 models (read-only) | environment-gated cross-repo test | `test_p29_s09_ac03` (1 tests) | PASS. Executed with P29_PLATFORM_ROOT=agent-reliability-platform-integration (read-only) and a scratch venv; without those variables the test is skipped (NOT_EXERCISED in a default run). Platform parity vectors of P28 were not re-run. | 3.11: 1p/0f/0s; 3.12: 1p/0f/0s; 3.13: 1p/0f/0s | Re-run against the final committed platform tree by the owner/reviewer. |
| P29-S09-AC04 | Planted strings never appear in any exporter body, report, repr or diagnostic | tests/fixtures/p29/privacy_planted.json | `test_p29_s09_ac04`, `test_pg1_` (6 tests) | PASS | 3.11: 6p/0f/0s; 3.12: 6p/0f/0s; 3.13: 6p/0f/0s | - |
| P29-S09-AC05 | Injection fixtures cannot add members, change vocabulary or alter payload shape | strict parser; exporter | `test_p29_s09_ac05`, `test_injection_` (3 tests) | PASS | 3.11: 3p/0f/0s; 3.12: 3p/0f/0s; 3.13: 3p/0f/0s | - |
| P29-S09-AC06 | P28 fixture manifests and contract documents byte-identical; P29 tests need no P28 source change | docs/P29_WORKSPACE_BASELINE.sha256 | `test_p29_s09_ac06`, `test_no_existing_source_module_is_modified` (2 tests) | PASS | 3.11: 2p/0f/0s; 3.12: 2p/0f/0s; 3.13: 2p/0f/0s | - |
| P29-S09-AC07 | Report states which sink was exercised; no TLS or delivery claim | docs/P29_IMPLEMENTATION_LOG.md (S09) | `test_p29_s09_ac07` (1 tests) | PASS. Capture/mock-transport path with the exporter working tree (its D-1 fix is present, uncommitted). | 3.11: 1p/0f/0s; 3.12: 1p/0f/0s; 3.13: 1p/0f/0s | - |
| P29-S10-AC01 | Case and report documents validate against their JSON Schemas | src/agent_reliability/experimental/judge/calibration.py; schemas/*.json; _jsonschema.py | `test_p29_s10_ac01`, `test_p29_s10_schema` (19 tests) | PASS | 3.11: 19p/0f/0s; 3.12: 19p/0f/0s; 3.13: 19p/0f/0s | - |
| P29-S10-AC02 | Metrics match hand-computed values; execution failures a separate column | src/agent_reliability/experimental/judge/calibration.py | `test_p29_s10_ac02`, `test_p29_s10_wilson`, `test_p29_s10_small` (4 tests) | PASS | 3.11: 4p/0f/0s; 3.12: 4p/0f/0s; 3.13: 4p/0f/0s | - |
| P29-S10-AC03 | Adversarial and borderline reported separately; injection fixtures included | src/agent_reliability/experimental/judge/calibration.py | `test_p29_s10_ac03` (1 tests) | PASS | 3.11: 1p/0f/0s; 3.12: 1p/0f/0s; 3.13: 1p/0f/0s | - |
| P29-S10-AC04 | Report contains no case text/reason/raw output; records fingerprint, model label, template id | src/agent_reliability/experimental/judge/calibration.py | `test_p29_s10_ac04`, `test_p29_s10_usage`, `test_p29_s10_load_cases`, `test_p29_s10_input_validation` (4 tests) | PASS | 3.11: 4p/0f/0s; 3.12: 4p/0f/0s; 3.13: 4p/0f/0s | - |
| P29-S10-AC05 | compare_reports lists flipped case_ids and net FN/FP change; no verdict | src/agent_reliability/experimental/judge/calibration.py | `test_p29_s10_ac05`, `test_p29_s10_compare` (2 tests) | PASS | 3.11: 2p/0f/0s; 3.12: 2p/0f/0s; 3.13: 2p/0f/0s | - |
| P29-S10-AC06 | No network I/O other than the supplied provider | src/agent_reliability/experimental/judge/calibration.py | `test_p29_s10_ac06`, `test_p29_s10_async`, `test_p29_s10_repeatability` (3 tests) | PASS | 3.11: 3p/0f/0s; 3.12: 3p/0f/0s; 3.13: 3p/0f/0s | - |
| P29-S11-AC01 | Two-question scenario: Q1 PASS, Q2 FAIL for both indicators with provenance and reason codes in evaluation_evidence | examples/judge_pilot_demo.py | `test_p29_s11_demo_runs`, `test_p29_s11_demo_assertions_are_stable` (2 tests) | PASS (SDK-side capture only) / NOT_EXERCISED (platform `evaluation_evidence`). Envelopes captured over a mocked transport; no platform ran. | 3.11: 2p/0f/0s; 3.12: 2p/0f/0s; 3.13: 2p/0f/0s | Primary pilot on the integrated platform tree. |
| P29-S11-AC02 | P3/P4 counts and error-budget arithmetic match hand-computed values | - | - | NOT_EXERCISED. Needs a platform. | - | Pilot on a platform tree. |
| P29-S11-AC03 | P6 coverage non-NO_DATA and a persisted P7 decision | - | - | NOT_EXERCISED. Needs a platform configured with P6/P7. | - | Pilot. |
| P29-S11-AC04 | Provider stopped: JudgeProviderUnavailableError evidence, P3 failure count, run health, agent run COMPLETED | coordinator.py | `test_p29_s11_demo_runs`, `test_p29_s05_ac08_results_and_failures` (2 tests) | PASS (SDK-side: failure evidence, run health, run completed) / NOT_EXERCISED (P3 count, reliability unchanged on a platform) | 3.11: 2p/0f/0s; 3.12: 2p/0f/0s; 3.13: 2p/0f/0s | Pilot. |
| P29-S11-AC05 | Evaluator health visible in platform reads; not a gate condition | - | - | NOT_EXERCISED. Local equivalent: coverage report (see Phase 4 tests). | - | Pilot. |
| P29-S11-AC06 | Scan of HTTP bodies, platform tables and logs finds no demo content | tests | `test_p29_s11_demo_runs`, `test_p29_s09_ac04` (2 tests) | PASS (captured bodies and logs only) / NOT_EXERCISED (platform tables) | 3.11: 2p/0f/0s; 3.12: 2p/0f/0s; 3.13: 2p/0f/0s | Pilot. |
| P29-S11-AC07 | Runbook lists prerequisites, commands, outputs, fallbacks | docs/P29_PILOT_RUNBOOK.md | `test_p29_s11_ac07` (1 tests) | PASS | 3.11: 1p/0f/0s; 3.12: 1p/0f/0s; 3.13: 1p/0f/0s | - |
| P29-S11-AC08 | Report states the path used; nothing committed/merged/released | docs/P29_PILOT_RUNBOOK.md | `test_p29_s11_ac08_ac09` (1 tests) | PASS. Path used: local demo and capture only. | 3.11: 1p/0f/0s; 3.12: 1p/0f/0s; 3.13: 1p/0f/0s | - |
| P29-S11-AC09 | Runbook carries the semantic limits and SG-1..SG-6 with applied/not-applied status | docs/P29_PILOT_RUNBOOK.md; docs/EVALUATE.md | `test_p29_s11_ac08_ac09`, `test_p29_s12_ac04` (2 tests) | PASS. All six safeguards are stated NOT SATISFIED for a pilot. | 3.11: 2p/0f/0s; 3.12: 2p/0f/0s; 3.13: 2p/0f/0s | - |
| P29-S11-AC10 | Pilot budgets generous enough that R13/R14 do not occur; else cross-indicator effect recorded | - | - | NOT_EXERCISED. No pilot configured. | - | Pilot. |
| P29-S12-AC01 | Benchmark methodology and results recorded with environment | - | - | NOT_EXERCISED. NOT RUN: no benchmark or load test was run; no figure is published. | - | S12 benchmark by a human-authorised run. |
| P29-S12-AC02 | Independent review closed (BLOCKER/HIGH) | - | - | BLOCKED. Requires a separate reviewer context under the two-prompt policy; not performed. This implementation has no independent verification. | - | Independent review. |
| P29-S12-AC03 | Traceability matrix maps every CON id, invariant and PG to passing tests | this document (sections 2 to 4) | `test_p29_fixture_manifest_hashes_match` (1 tests) | PASS (author-built matrix; every mapped test executed and passed) -- independent reading pending | 3.11: 1p/0f/0s; 3.12: 1p/0f/0s; 3.13: 1p/0f/0s | Reviewer verifies by reading. |
| P29-S12-AC04 | User docs updated with privacy statement, PASS meaning and non-claims | docs/EVALUATE.md; README.md | `test_p29_s12_ac04`, `test_p29_con17` (2 tests) | PASS | 3.11: 2p/0f/0s; 3.12: 2p/0f/0s; 3.13: 2p/0f/0s | - |
| P29-S12-AC05 | Release gate: approvals recorded; version bump per VERSIONING.md | - | - | BLOCKED. No release authorization exists; no version bump was made; nothing is committed. | - | Owner authorization and release process. |

Summary of results by criterion: PASS 59, PARTIAL (SDK-side PASS, platform part NOT_EXERCISED) 3, FAIL 0, NOT_EXERCISED 5, BLOCKED 2 (total 69).

## 2. Contract traceability (P29-CON-nn)

| Contract id | Subject | Tests | Result (3 Pythons) |
|---|---|---|---|
| P29-CON-01 | No wire change | `test_p29_s09_ac01_result_never`, `test_p29_s09_ac05`, `test_no_existing_source_module_is_modified` (3) | PASS |
| P29-CON-02 / 02a | Request never serialized; trust cannot be promoted | `test_p29_s01_ac04`, `test_p29_s01_ac03_trust_promotion`, `test_untrusted_roles_are_never_promoted` (8) | PASS |
| P29-CON-03 | Rubric document and immutability | `test_p29_s01_ac01`, `test_p29_s01_ac05` (91) | PASS |
| P29-CON-04 / 04a | Identity mapping; dual-grammar rule | `test_p29_s01_ac02`, `test_p29_s09_ac01_ac02` (53) | PASS |
| P29-CON-05 | Provider protocol and error classification | `test_p29_s03_ac01`, `test_p29_s03_ac02`, `test_p29_s06_example_http` (46) | PASS |
| P29-CON-06 | Judge output document and parse rules | `test_p29_s02_ac02_ac03_parser_vectors`, `test_parse_round_trip` (68) | PASS |
| P29-CON-07 | Verdict-to-decision and confidence mapping | `test_p29_s02_ac05`, `test_pass_only_for_a_confident_pass_verdict` (22) | PASS |
| P29-CON-08 / 08a | Result semantics; aggregation consequences | `test_p29_s03_ac02_failure_matrix`, `test_ninety_nine_failures`, `test_p29_s12_ac04` (30) | PASS |
| P29-CON-09 | Failure-class vocabulary | `test_failure_taxonomy_snapshot`, `test_p29_s09_failure_class_vocabulary`, `test_p29_s03_ac02_failure_class_vocabulary` (3) | PASS |
| P29-CON-10 | Reason-code vocabulary | `test_p29_s06_ac01_each_reference_rubric`, `test_p29_s09_ac01_ac02` (42) | PASS |
| P29-CON-11 | Limits, retry and budget rules | `test_p29_s01_ac03_limits`, `test_p29_s03_ac04`, `test_p29_s03_ac05`, `test_p29_s05_ac06` (39) | PASS |
| P29-CON-12 | Reserved indicator names | `test_p29_s05_ac08_deterministic_model_backed_binding_rejected`, `test_p29_s05_binding_validation` (2) | PASS |
| P29-CON-13 / 13a / 13b | Coordinator; recording serialization; indicator= capability | `test_p29_s05_ac03`, `test_p29_s05_ac09`, `test_p29_s05_ac08_handle_without_indicator` (11) | PASS |
| P29-CON-14 | Local-only observer report | `test_p29_s05_ac07` (2) | PASS |
| P29-CON-15 | Fixtures | `test_p29_fixture_manifest_hashes_match`, `test_p29_fixtures_have_id_input_expected_note` (2) | PASS |
| P29-CON-16 | Prompt template jp1 | `test_p29_s02_ac01`, `test_p29_s02_ac04` (16) | PASS |
| P29-CON-17 | Rubric-change cohort convention | `test_p29_con17` (1) | PASS |

## 3. Invariants (I-P29-1..5)

| Invariant | Statement | Tests | Result |
|---|---|---|---|
| I-P29-1 | No JudgeError, timeout, cancellation, shed or skip yields PASS/FAIL/UNKNOWN | `test_p29_s03_ac02`, `test_failure_never_becomes_pass_fail_or_unknown`, `test_overload_shedding`, `test_outcome_is_exactly_result_or_failure` (48) | PASS |
| I-P29-2 | UNKNOWN only from a completed judgment or a deterministic pre-check | `test_p29_s02_ac06`, `test_pass_only_for_a_confident_pass_verdict`, `test_precheck_unknown_and_low_confidence` (5) | PASS |
| I-P29-3 | A failure carries the evaluator identity | `test_p29_s03_ac02_failure_carries_identity`, `test_p29_s09_ac01_ac02` (17) | PASS |
| I-P29-4 | A semantic result never writes a P13 outcome observation | `test_p29_i_p29_4` (1) | PASS |
| I-P29-5 | The platform sees no distinction between R05-R14 beyond exception_type | `test_p29_s09_i_p29_5` (1) | PASS |

I-P29-4 is exercised on the SDK side only (the coordinator emits no event type other than run lifecycle and evaluation evidence); P13 itself is a platform object and was not touched.

## 4. Privacy guarantees (PG-1..4)

| Guarantee | Statement | Tests | Result | Limit |
|---|---|---|---|---|
| PG-1 | No ContentPart text in any event, failure, report, exception, repr, diagnostic or exported body | `test_pg1_`, `test_p29_s09_ac04`, `test_p29_s03_ac06`, `test_p29_s10_ac04` (16) | PASS | - |
| PG-2 | No code path calls a Gentlity endpoint with content | `test_p29_s09_ac04`, `test_namespace_has_no_logging_print`, `test_p29_s10_ac06` (3) | PASS | SDK side: the package has no network client and bodies were scanned; the live platform path was not exercised. |
| PG-3 | No network I/O in the core namespace | `test_pg3_importing`, `test_importing_the_namespace_loads_no_third_party`, `test_p29_s10_ac06` (3) | PASS | - |
| PG-4 | Judge failure never changes reliability | `test_ninety_nine_failures`, `test_failure_never_becomes_pass_fail_or_unknown`, `test_attempted_counts_failures` (11) | PASS | SDK side only: failures are excluded from the determinate count. The cross-repository test with the platform's real P3 counting was NOT_EXERCISED. |

## 5. Not covered by any executed test

* Benchmarks, load, memory under load (S12-AC01): not run.
* Independent review and re-verification (S12-AC02): not performed. Every PASS in this document is author-run.
* Platform behavior: P3/P4/P6/P7 reads, `evaluation_evidence` rows, health counts, gate decisions (S11-AC02, AC03, AC05, AC10); live delivery and TLS handling of the exporter (the D-1 fix is in the uncommitted working tree; no P29 test exercises real TLS).
* A real model or provider (the example providers are exercised with a fake transport only).
* Release gate (S12-AC05).

## 6. Review remediation (docs/P29_REVIEW_REMEDIATION_REPORT.md)

| Finding | Subject | Tests | Result (3 Pythons) |
|---|---|---|---|
| F-1 | submit() outside a loop: no state change | `test_f1_` (2) | PASS |
| F-2/F-3/F-9/F-11 | docs: sync timeout semantics, gate constraints, recorded = handed to handle, token undercount | `test_review_f2_f3_f9_f11` (1) | PASS |
| F-3 | re-entrancy raises RuntimeError instead of deadlocking | `test_f3_` (2) | PASS |
| F-4 | example adapter refuses redirects, caps response size | `test_f4_` (3) | PASS |
| F-5 | demo test asserts keyed data; stable over 64 parallel runs | `test_p29_s11_demo_assertions_are_stable`, `test_p29_s11_demo_runs` (2) | PASS |
| F-6 | drain-recording overlap; queued/granted waiter cancellation; FIFO | `test_f6_` (4) | PASS |
| F-8 | C1 control boundary vectors (U+001F/20, 7E/7F, 80/9F/A0) | `reason-c1`, `reason-c0`, `reason-just` (6) | PASS |
| F-10 | sync queued waiter abandons its slot on BaseException | `test_f10_` (1) | PASS |
| F-12 | virtual-time guard turns a missing timeout into a failure | `test_f12_` (1) | PASS |
| F-13 | jitter validation, weak capability cache, README placement | `test_f13_`, `test_review_f13` (3) | PASS |

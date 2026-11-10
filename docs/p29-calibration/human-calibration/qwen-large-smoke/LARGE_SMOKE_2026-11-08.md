# Qwen3-14B large smoke test, 2026-11-08 (local, synthetic, NOT a calibration)

Preregistered configuration (`PREREGISTERED_CONFIG.json`, committed `eff661f` before the run; config sha256 `5917c859…760b`) over 250 fresh synthetic relevance cases (`dataset.json`, sha256 `e881000c…efed`, disjoint from the golden set, the earlier smoke examples and any human data). Model qwen3:14b, manifest digest `bdbd181c33f2`, Q4_K_M, prompt template **jp2**, no-think (`reasoning_effort=none`), context 4096 (Ollama default load), output budget 512, requested temperature 0.0, default rubric `judge-answer-relevance 2026-11.r1`, max_attempts 1 with the default one repair attempt. Citation validation unmodified. The configuration was not changed in response to any result. Total wall clock 743.6 s.

## Result against the unchanged 2% evaluator-failure ceiling: NOT MET

| Scope | Evaluations | Evaluator failures | Rate | Wilson 95% CI |
|---|---|---|---|---|
| **Overall** | 250 | **19** | **7.6%** | 4.9% – 11.6% |
| no_context | 50 | 0 | 0% | 0% – 7.1% |
| grounded_context | 50 | 0 | 0% | 0% – 7.1% |
| conflicting_evidence | 50 | 2 | 4.0% | 1.1% – 13.5% |
| **missing_evidence** | 50 | **16** | **32.0%** | 20.8% – 45.8% |
| adversarial | 50 | 1 | 2.0% | 0.4% – 10.5% |

Adversarial forms (10 each): answer prefix injection 1 failure, the other four forms (answer suffix, question injection, context injection, padding/unicode) 0. The lower bound of the overall interval (4.9%) is above 2%, so the ceiling is not met even on the optimistic side.

- **Error classes:** all 19 failures are `JudgeInvalidOutputError` with `invalid_code` (the reply's `code` is not an allowed code for its verdict). No timeouts, provider errors, truncation, invalid JSON, invalid schema or **invalid citations**: the jp1 failure mode is gone.
- **First replies rejected:** 24 evaluations needed a repair call (19 still failed, 5 recovered).
- **Other outcomes:** 217 determinate, 14 unknown, 19 evaluator failures. Unknowns are concentrated in missing_evidence (13).
- **Latency** per evaluation (including any repair call): p50 2.72 s, p95 5.4 s, max 7.1 s.
- **Descriptive only:** 204 of 217 determinate verdicts match the generator's author-intent expectation (not human labels, no claim).

## jp2 verification
`jp2` is implemented (commit `23c25bb`), opt-in through `JudgePolicy(prompt_template="jp2")`. It differs from `jp1` only when no context block is sent. `jp1` is byte-identical (the committed golden and the full SDK suite, 2204 tests, pass), citation validation is unchanged (regression tests reject `[0]` with no context and out-of-range indexes), and the template is recorded in the configuration id, behaviour and calibration report. On the no-context scenario it removed the earlier failure completely (0 of 50, against 7 of 20 failing for relevance with jp1 in the earlier smoke).

## Exploratory (separate from the measurement; `EXPLORATORY_invalid_code.json`)
Re-running only the 19 failing cases with the same configuration and recording the closed `verdict/code` tokens: of 37 replies, 34 were `verdict=pass, code="pass"`, plus one each of `responsive`, `addresses_question` (valid) and `evasive_or_non_answer`. So the model echoes the verdict as the code on cases where the context lacks the asked-for fact and the answer is responsive. The allowed pass code (`addresses_question`) is listed in the system message but not followed. This is an instruction-following lapse of the model on this case type, not a validator defect, and nothing was changed to accommodate it.

## Limits
Synthetic templated text with generator-intent labels; 50 cases per scenario (wide intervals per scenario); one run, one configuration, no repeats; no human labels, adjudication or held-out evidence. No calibration or customer-readiness claim. `customer_readiness` stays NO-GO.

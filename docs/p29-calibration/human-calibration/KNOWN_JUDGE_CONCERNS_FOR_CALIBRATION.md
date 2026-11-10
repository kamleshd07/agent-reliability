# Known judge concerns to carry into calibration

Observed in the synthetic evaluator-failure smoke tests (Qwen3-14B, jp3, 2026-11-09; see `qwen-jp3-rubrics/RUBRICS_SMOKE_2026-11-09.md`). These
are **development observations, not accuracy results**: the generator's expectations are not human labels, and the smoke sets were never human-adjudicated.

| # | Concern | Where seen | Why it matters |
|---|---|---|---|
| 1 | Task-completion evidence saying "pending" or "queued" sometimes receives PASS | completion rubric, insufficient-evidence cases (PASS in 31 of 50) | The costly direction: a false PASS on unfinished work. Guarded by `max_judge_pass_rate_on_adjudicated_unknown` (0.25). |
| 2 | Weak abstention on insufficient evidence | several rubrics; strongest willingness to answer UNKNOWN is groundedness | UNKNOWN must be used when evidence is missing; calibration measures it against adjudicated UNKNOWN. |
| 3 | Vague instructions ("Be helpful") receive PASS | instruction-adherence rubric (PASS in 46 of 50) | May be acceptable or not; humans decide what a vague instruction means. |
| 4 | A correctness reference that lacks the asked fact produces FAIL | correctness rubric (FAIL in 37 of 50) | The rubric defines UNKNOWN (`reference_insufficient`) for this. |
| 5 | Whitespace-only required input is not pre-checked | any rubric: `""` returns a missing-input UNKNOWN without a model call, `"   "` goes to the model | Existing jp1/jp2 behaviour. Normalising it is a **separately versioned, reviewable change**; it was not made. |

## Rules for using this list
1. **Development examples are separate from the protected set.** Concern 1 to 5 may be explored only on new synthetic development examples. The 300 private relevance items and any item a human has seen are protected: no prompt, rubric, threshold, template or code change may be tuned on them.
2. **Do not tune jp3 against the calibration set.** jp3 is frozen (digest `99a39773...626b67`). A prompt change is a new template version (never an edit of jp1, jp2 or jp3), needs independent review, and needs a new, fresh, preregistered round.
3. **Whitespace normalisation is a separate change.** It would alter historical behaviour, so it must be a new, versioned and reviewed implementation change, decided by the owner. Do not fold it into calibration preparation, and do not apply it silently to jp1 or jp2.
4. These concerns apply to the five rubrics other than relevance. The relevance rubric had no abstention concern in the synthetic smoke set, but relevance itself is not calibrated until humans have labelled it.

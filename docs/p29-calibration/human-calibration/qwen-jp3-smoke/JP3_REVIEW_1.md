# JP3 review 1 (commit 1d70297)

Reviewer: independent, fresh context. No source or test modified; no model run.
Full suite: 2221 passed, 6 skipped.

## Verdict: NOT READY AS-IS (fix F1, then acceptable). Counts: BLOCKER 0, HIGH 1, MEDIUM 3, LOW 3.

## Verified OK
- jp1/jp2 byte-for-byte: I built system+user for all 6 rubrics x {jp1,jp2} x {no-context, context} x repair {None, invalid_code, invalid_json} at parent (1d70297~1, via git archive) and at HEAD and compared SHA-256 of each: IDENTICAL. template_digest jp1 (9cabfba1...) and jp2 (43b12d0b...) unchanged.
- Parser/validation untouched (core.py parse path not in the diff): invalid code -> invalid_code, nonexistent/duplicate citation -> invalid_citations, pass without citation on require_citations -> invalid_citations. Evaluator failures are not mapped to FAIL by this change.
- Identity/behaviour/calibration: PROMPT_TEMPLATES extended, identity ("jp3" <=16 chars), behaviour digest, calibration parsing of template segment all handle jp3. No new deps, no engine change (engine already passes policy.prompt_template and repair class).
- No-context rule: jp3 emits `"citations":[],` and the "must be []" rule when context_count==0, same as jp2.

## Findings

### F1 HIGH - "Judge only the criteria above ... pass even when other facts are unestablished" is rubric-unsafe
Location: core.py `_system_message_jp3`, rule line "Judge only the criteria above. If they are met, the verdict is "pass" ... even when the supplied blocks leave other facts unestablished."
Evidence: the sentence is injected into every rubric but was written against relevance. For other rubrics, "facts unestablished by the blocks" is the failure/unknown condition itself:
- judge-groundedness: criterion "Each material claim ... is supported by at least one context block". A claim the context leaves unestablished is exactly unsupported_claim / context_insufficient. The sentence invites pass.
- judge-answer-correctness: "required-facts" criterion; facts missing from ANSWER/REFERENCE are missing_required_facts or reference_insufficient.
- judge-task-completion-evidence: "evidence states requested action was done"; unestablished completion must not pass.
- judge-safety-policy / instruction-adherence: policy_missing / instructions_missing are unknown cases.
It also sits one bullet above "Choose unknown when evidence is insufficient", with no precedence stated, so the two rules conflict. Net effect is a pass bias (false PASS on agents) for any rubric whose criteria concern evidence sufficiency, which is the dangerous direction for a reliability evaluator. The only test (`test_missing_evidence_relevance_prompt_says_unestablished_facts_do_not_fail`) runs on relevance alone and just asserts the sentence exists.
Reproduce: `build_prompt(<groundedness rubric>, CTX, nonce=..., template_id="jp3").system` and read the Rules block.
Suggested fix: make it per-rubric (e.g. a rubric field/clause only for relevance) or reword to rubric-neutral: "Decide only from the criteria above; facts not asked about by the criteria are irrelevant. If a criterion itself requires evidence that is absent, choose unknown (or fail where a fail code names it)." Add per-rubric prompt tests.

### F2 MEDIUM - template_digest does not cover the jp3 invalid_code repair tail
behaviour.py renders the repair variant only with `repair_error_class="probe_error_class"`; the jp3-only branch needs `"invalid_code"`. Editing the tail text would leave the jp3 digest unchanged, defeating the "template edit changes digest" guarantee for jp3. Reproduce: change the tail string and compare `template_digest("jp3")`. Add "invalid_code" to the digest's repair variants for jp3 only (keep jp1/jp2 digests unchanged by gating on template).

### F3 MEDIUM - require_citations rubric with zero context: pass is unreachable but jp3 now pushes toward pass
For groundedness with no context, jp3 says citations must be [], omits the "pass must cite" rule, and F1's rule urges pass; parser then rejects pass with invalid_citations (core.py line ~449). Strictness is correctly preserved (not a validation weakness), but the prompt gives the model an unwinnable instruction. (jp2 has the omission too; jp3 aggravates via F1.) Either state "with no context blocks a pass cannot be supported; choose unknown/context_insufficient" or accept and test it.

### F4 MEDIUM - tests partly tautological / thin
- `test_jp1_and_jp2_text_are_unchanged` only asserts jp3 phrases are absent; no golden/byte comparison, so a jp1/jp2 drift elsewhere would pass. (I did the real comparison manually, results above.) Recommend pinning sha256 of jp1/jp2 system+user per rubric, or the digests above.
- Prompt-content tests are substring checks on relevance only except the all-rubric pairs test. Nothing exercises groundedness wording (F1) or the pass-citation rule under jp3 with context.
- `test_rubric_specific_code_selection...` and mismatch/UNKNOWN tests exercise the unchanged parser, not jp3; fine as regression guards but they do not test "rubric-specific code selection" in the prompt beyond the pairs test.
- No engine-level test that a rejected invalid_code reply triggers the jp3 repair tail on the second call.
- `test_prompt_version_reproducible_and_distinct` compares the function with itself (determinism only); no pinned jp3 digest, so jp3 text can change silently with only "distinct" still true.

### F5 LOW - repair tail only for invalid_code
invalid_citations (the other common small-model error) gets no jp3 hint. Optional.

### F6 LOW - privacy-scan exemption by function name
tests/security/test_experimental_judge_privacy.py now skips `_system_message_jp3` wholesale. Inspected: its f-strings interpolate only rubric dimension, criterion id/text, verdict labels and code names (trusted operator rubric), no evaluated content, so the exemption is justified and mirrors `_system_message`. Residual risk: future content interpolation in that function would go unscanned. Acceptable.

### F7 LOW - judge_disagreement / judge_abstained listed as selectable unknown codes
Listed because "every code of the verdict is allowed"; judge_disagreement is an aggregation outcome a single call should not emit. Same exposure as jp1/jp2 (they list it too), so not a regression.

## Requirement check
1 met (verified). 2 met (pairs, "NOT valid codes"). 3 met. 4 met for validation; F1 weakens verdict quality, not validation. 5 met. 6 partly (F4).

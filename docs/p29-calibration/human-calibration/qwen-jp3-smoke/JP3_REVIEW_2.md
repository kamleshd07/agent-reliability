# JP3 review 2 (commit 831b621 on top of 1d70297)

No source/test modified; no model run. Full suite: 2238 passed, 6 skipped.

## Verdict: ACCEPT (conditional on nothing blocking). BLOCKER 0, HIGH 0, MEDIUM 1 (residual), LOW 3.

## Re-verification
- jp1/jp2: same 6 rubrics x {jp1,jp2} x {QA,ctx} x repair {None,invalid_code,invalid_json} sha256 comparison vs pre-jp3 parent: IDENTICAL. Digests unchanged (jp1 9cabfba1..., jp2 43b12d0b...). New test pins both digests (closes F4 first bullet). Digest change for jp3 only (gated on template_id == "jp3"); jp3 now 99a39773....
- Parser/validation untouched in both commits.

## F1-F5 status
- F1 CLOSED. Rewritten rule: "Apply only the criteria above. A fact that none of the criteria requires is not a reason to fail or to choose unknown; a fact that a criterion requires and the blocks do not establish is." Checked against all six rubrics: groundedness (supported-by-context is a criterion, so unestablished claims still lead to fail/unknown), correctness (required-facts), task-completion-evidence (evidence-states), safety-policy, instruction-adherence, relevance (no context fact required, so missing context does not fail). No pass bias remains; the old "pass even when ..." wording is gone and tested absent. Precedence with the "unknown" bullet is now coherent. Minor: the sentence says such a fact "is" a reason without naming fail vs unknown; the model picks via the code lists. Acceptable.
- F2 CLOSED. Digest renders invalid_code and invalid_citations for jp3 only; test checks the three repair user texts differ (that test checks build_prompt, not digest sensitivity directly, but the digest loop provably includes them).
- F3 CLOSED (prompt-side). Note added only when no context and require_citations (test parametrised over all six). Residual (LOW): the note says pass would be rejected but does not say what to choose instead (unknown/context_insufficient); a small model could still emit pass.
- F4 PARTLY closed. Digest pinning for jp1/jp2 added; engine repair tests added (second call carries jp3 text, same system, recovers; persistent invalid code still raises invalid_code after 2 calls); scope sentence tested for all rubrics. Still open (MEDIUM, residual): jp3 text/digest itself is not pinned, so the reproducibility test is determinism-only; jp3 can change silently. Also `assert decision is not None` in the recovery test is weak (does not check verdict/code), and the scope/note tests are substring-based. Pin the jp3 digest once the template is frozen (before the smoke run, since the run's identity depends on it).
- F5 CLOSED. invalid_citations repair text for jp3 only, tested; jp2 unaffected.

## Dispositions
- F6 (privacy exemption by name): agree, accepted LOW.
- F7 (judge_disagreement offered): agree, accepted LOW; identical exposure in jp1/jp2.

## Other observations (LOW)
- Working tree has uncommitted changes to scripts/p29_qwen_jp3_smoke.py and untracked PREREGISTERED_CONFIG.json / dataset.json. Not part of the reviewed diff; ensure the pre-registration is committed before any run, and that the committed jp3 digest matches the one recorded in it (99a39773...).
- Commit 831b621 bundles DEV_RESULTS.json and dev_dataset.json with the fix; not a code defect, but dev results were presumably produced against some template text: confirm they were generated on 831b621's jp3 digest, not 1d70297's.

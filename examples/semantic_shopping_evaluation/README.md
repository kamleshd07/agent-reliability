# Semantic evaluation of a real shopping assistant (local, synthetic)

A retrieval shopping assistant answers customer questions about a SYNTHETIC test catalogue with a local model, and `SemanticChecks`
(groundedness and answer relevance) evaluates its actual answers. Read [docs/SEMANTIC_EVALUATION.md](../../docs/SEMANTIC_EVALUATION.md) first.
No real merchant, customer or personal data is involved. EXPERIMENTAL.

| File | What it is |
|---|---|
| `catalog.py`, `agent.py` | the synthetic catalogue, a keyword retriever, and the assistant (local OpenAI-compatible model on loopback) |
| `record_agent.py`, `transcripts/gemma4-12b-run1.json` | 22 recorded real executions (2 contain a deliberately planted instruction in a retrieved document) |
| `golden.py` | the golden set: those 22 answers plus 31 constructed defective or tricky answers, with the expected outcomes and the labelling policy |
| `evaluate.py`, `expected/verdicts-*.json` | the live measurement (`run`) and the offline metrics (`report`); the verdict files hold outcomes, reason codes, failure classes, latency and token counts, no text |
| `deliver.py` | customer side of the HTTP-to-PostgreSQL roundtrip (the platform side is `tools/pilot/semantic_e2e.py` in the private platform repository) |

```
python -m examples.semantic_shopping_evaluation.evaluate report examples/semantic_shopping_evaluation/expected/verdicts-gemma4-12b-tok1536.json   # offline
python -m examples.semantic_shopping_evaluation.evaluate run gemma4:12b out.json 1536   # needs a local runtime serving the model; slow and non-deterministic
```

Label provenance: written by the implementing assistant, not by a human; please review `golden.py`. The same model produced and judged the real answers.
Four labels were corrected after an independent review (`CORRECTIONS` in `golden.py`); the originals and the stored verdicts are kept, and
`evaluate report FILE original|corrected|clear [agent_run|constructed]` recomputes the metrics under each view. Deterministic checks stay authoritative; the semantic indicators complement them.

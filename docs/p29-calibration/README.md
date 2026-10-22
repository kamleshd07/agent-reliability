# P29 judge calibration and evidence admission (Experimental)

Namespace: `agent_reliability.experimental.calibration` (stdlib only, no network, no environment reads, no
provider calls of its own). It builds on the existing experimental LLM-judge adapter
(`agent_reliability.experimental.judge`, ADR-0010, `docs/P29_*.md`) and does **not** change stable APIs, wire
contracts, evaluator identity or measurement-health semantics.

It answers, offline and reproducibly: how accurate is a judge configuration against labelled examples, how repeatable
is it, how does it disagree with another configuration, when does a calibration stop applying, and may its outcomes feed
reliability SLO evidence. **It never says a judge is accurate in production.** "Calibrated" means only: *meets the
caller's stated policy on the named held-out dataset for exactly this behaviour digest and model declaration at that
time*, with label provenance an attestation.

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | design, normative statistical definitions, status rules, admission layer, owner decisions |
| [DATASET_SCHEMA.md](DATASET_SCHEMA.md) | file formats, splits, labelling and adjudication process, retention |
| [PROVENANCE_SPEC.md](PROVENANCE_SPEC.md) | judge fingerprint and what it can and cannot detect |
| [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md) | threat model, controls, limits of LLM-judging-LLM |
| [PERFORMANCE.md](PERFORMANCE.md) | bounded local measurements and resource limits |
| [PLATFORM_PROPOSAL.md](PLATFORM_PROPOSAL.md) | proposal only: conveying status to the platform |
| [GAP_ASSESSMENT.md](GAP_ASSESSMENT.md) | what P29 already had, what was missing |

## Five-minute offline walkthrough

```bash
pip install -e ".[dev]"
python examples/judge_calibration_offline.py
```

The example generates a SYNTHETIC dataset (`scripts/p29_calibration_demo_data.py`), runs a scripted pretend judge (no
model, no network), and prints: dataset provenance and leakage check, calibration metrics with exact intervals, repeatability,
a two-judge comparison (agreement is not correctness), the status under a demonstration policy and under the starting-point
policy, the coordinator gate skipping an inadmissible judge, and drift indicators.

## Minimal use

```python
from agent_reliability.experimental.calibration import (
    CalibrationGate, CalibrationPolicy, ModelDeclaration, Split,
    build_assessment, collect_judgments, load_reference_dataset,
)

dataset = load_reference_dataset("ds/manifest.json", expected_manifest_sha256=PINNED)   # pin BEFORE running
model = ModelDeclaration("my-provider", "my-model", "2026-09")     # a declaration, not an observation
table = collect_judgments(judge, model, dataset.cases(Split.HELDOUT), repetitions=3)   # your judge, your provider
assessment = build_assessment(dataset, Split.HELDOUT, table, now=now).sign(KEY)
policy = CalibrationPolicy(...)            # every threshold explicit; or CalibrationPolicy.starting_point()
gate = CalibrationGate(judge, model, assessment, policy, hmac_key=KEY)
binding = IndicatorBinding("answer-correctness", judge, admission=gate)   # opt-in; default is unchanged
```

`collect_judgments` is the only function that can reach a provider, and only through the judge you supply (its opt-in,
budgets, limits and retry policy apply unchanged). Nothing here makes a paid call by itself.

## What is and is not guaranteed

* An **ungated** judge (no `admission=`) behaves exactly as before: its outcomes are recorded and counted as ever, and are
  **uncalibrated unless you prove otherwise**. `CoverageReport` now counts them (`ungated_model_backed`).
  Making an explicit choice mandatory is owner decision OD-S4-2.
* A gated, inadmissible judge is **skipped**: no provider call, no evidence, no failure, run health unchanged. The platform
  sees absence (missing evidence), never PASS, and cannot yet see why (OD-S4-3).
* Silent provider-side model updates are undetectable unless you encode the model version in `model_label`
  ([PROVENANCE_SPEC.md](PROVENANCE_SPEC.md)).

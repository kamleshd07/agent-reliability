# ruff: noqa: E501 -- printed narrative lines are kept readable.
"""Offline walkthrough: judge calibration and evidence admission (P29, Session 4).

Everything here is deterministic, local and free: the dataset is SYNTHETIC (its labels
are not human ground truth), the "judge provider" is a script keyed by case id, there
is no network and no model call, and the clock is fixed.

    python examples/judge_calibration_offline.py

Read the output as a demonstration of the machinery, not of any model's quality.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_reliability.experimental.calibration import (
    CalibrationGate,
    CalibrationPolicy,
    LabelProvenance,
    ModelDeclaration,
    Split,
    assess_admission,
    assess_drift,
    build_assessment,
    collect_judgments,
    compare_judges,
    load_reference_dataset,
    repeatability,
)
from agent_reliability.experimental.judge import (
    EvaluationDisposition,
    IndicatorBinding,
    JudgeCoordinator,
    JudgeLimits,
    JudgeProviderUnavailableError,
    ProviderReply,
    SyncLLMJudge,
    load_reference_rubric,
)
from agent_reliability.experimental.judge.testing import judge_reply
from agent_reliability.sdk import AgentReliability

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
DEMO_KEY = b"demo-key-not-a-secret-0123456789"  # a fixed demonstration key
CODES = {
    "pass": ("pass", "consistent_with_reference"),
    "fail": ("fail", "contradicts_reference"),
    "unknown": ("unknown", "reference_insufficient"),
}


class ScriptedProvider:
    """A pretend judge: answers from a table keyed by case id (no model, no network)."""

    provider_label = "scripted"
    reports_tokens = False

    def __init__(
        self, wrong: dict[str, str], unavailable: set[str], flips: dict[str, str]
    ):
        self._wrong = wrong
        self._unavailable = unavailable
        self._flips = flips
        self._seen: dict[str, int] = {}
        self._truth: dict[str, str] = {}

    def learn(self, truth: dict[str, str]) -> None:
        self._truth = truth

    def complete(self, call) -> ProviderReply:  # type: ignore[no-untyped-def]
        # Each answer starts with "[<case id>]"; find which known case this prompt is.
        case_id = next(c for c in self._truth if f"[{c}]" in call.user)
        run = self._seen.get(case_id, 0)
        self._seen[case_id] = run + 1
        if case_id in self._unavailable:
            raise JudgeProviderUnavailableError
        verdict = self._wrong.get(case_id, self._truth[case_id])
        if run == 1 and case_id in self._flips:
            verdict = self._flips[case_id]
        word, code = CODES[verdict]
        return ProviderReply(text=judge_reply(word, code, "high"))


def load_generator():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "p29_calibration_demo_data", ROOT / "scripts" / "p29_calibration_demo_data.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def show(title: str, *lines: str) -> None:
    print(f"\n== {title}")
    for line in lines:
        print(f"   {line}")


def rate(block: dict) -> str:  # type: ignore[type-arg]
    if block["value"] is None:
        return f"undefined ({block['undefined_reason']})"
    low, high = block["clopper_pearson_95"]
    return f"{block['numerator']}/{block['denominator']} = {block['value']:.3f}  [exact 95% {low:.3f}-{high:.3f}]"


def judge_for(label: str, provider: ScriptedProvider) -> SyncLLMJudge:
    return SyncLLMJudge(
        rubric=load_reference_rubric("judge-answer-correctness"),
        provider=provider,
        model_label=label,
        limits=JudgeLimits(max_attempts=1, repair_attempts=0),
        jitter=lambda: 0.0,
    )


def main() -> int:
    generator = load_generator()
    with tempfile.TemporaryDirectory() as directory:
        manifest, digest = generator.build(Path(directory))
        dataset = load_reference_dataset(manifest, expected_manifest_sha256=digest)
        cases = dataset.cases(Split.HELDOUT)
        truth = {c.case_id: c.human_label for c in cases}

        show(
            "1. The dataset (SYNTHETIC, hash-pinned before use)",
            f"id={dataset.dataset_id} version={dataset.dataset_version} license={dataset.license}",
            f"splits={{ {', '.join(f'{s.value}: {len(c)}' for s, c in dataset.splits.items())} }}",
            f"held-out label provenance (attested, derived = weakest case): "
            f"{dataset.split_provenance[Split.HELDOUT].value}",
            f"split leakage: {'none' if dataset.leakage.clean else dataset.leakage.as_dict()}",
        )

        # Judge A: mostly right. It misses some defects (one through an injection),
        # abstains sometimes, has one provider outage and one unstable case.
        provider_a = ScriptedProvider(
            wrong={"f05": "pass", "f17": "pass", "a02": "pass", "p11": "fail",
                   "f09": "unknown", "p20": "unknown", "m03": "unknown"},
            unavailable={"p03"},
            flips={"f01": "pass"},
        )  # fmt: skip
        provider_a.learn(truth)
        judge_a = judge_for("scripted-a", provider_a)
        model_a = ModelDeclaration("scripted", "demo-model-a", "1")
        table_a = collect_judgments(judge_a, model_a, cases, repetitions=3)

        assessment = build_assessment(
            dataset, Split.HELDOUT, table_a, now=NOW - timedelta(days=2)
        ).sign(DEMO_KEY)
        head = assessment.document["metrics"]["headline"]
        show(
            "2. Calibration metrics for judge A (headline = clear + ambiguous; run 0)",
            f"labelled examples: {head['n_labelled']}  (indeterminate set reported separately: "
            f"{head['indeterminate']['n']})",
            f"committed coverage : {rate(head['rates']['committed_coverage'])}",
            f"abstention rate    : {rate(head['rates']['abstention_rate'])}",
            f"failure rate       : {rate(head['rates']['failure_rate'])}",
            f"fnr (effective)    : {rate(head['rates']['fnr_effective'])}   <- defects NOT flagged",
            f"fpr (conditional)  : {rate(head['rates']['fpr_conditional'])}",
            f"F1 (fail class)    : {head['f1']['fail']['value']:.3f}",
            "borderline stratum : reported only, assessed by no criterion",
            f"adversarial defects passed: {assessment.document['metrics']['strata']['adversarial']['counts']['fn']}",
        )
        rep = repeatability(cases, table_a)
        show(
            "3. Repeatability (same configuration, 3 runs)",
            f"unstable cases: {rate(rep['unstable_rate'])}",
            f"excluded because a run failed: {rep['excluded_for_failures']}  "
            f"(worst case counts them as unstable: {rate(rep['unstable_rate_worst_case'])})",
        )

        provider_b = ScriptedProvider(
            wrong={"f05": "pass", "f10": "pass", "p07": "fail", "a02": "pass", "a05": "pass"},
            unavailable=set(), flips={},
        )  # fmt: skip
        provider_b.learn(truth)
        model_b = ModelDeclaration("scripted", "demo-model-b", "1")
        table_b = collect_judgments(judge_for("scripted-b", provider_b), model_b, cases)
        diff = compare_judges(cases, table_a, table_b)
        show(
            "4. Judge A versus judge B (agreement is not correctness)",
            f"categories: {json.dumps(diff['categories'])}",
            f"judgment disagreement: {rate(diff['judgment_disagreement_rate'])}",
            f"both judges wrong in the same way (shared errors): {diff['shared_errors']}",
            f"differing components: {', '.join(diff['differing_components'])}",
        )

        demo = CalibrationPolicy(
            min_examples=40, min_per_class=15, min_adversarial_fail=5,
            min_committed_coverage=0.6, max_abstention_rate=0.3, max_failure_rate=0.2,
            max_missing_rate=0.2, max_fnr=0.5, fn_basis="effective", max_fpr=0.5,
            fp_basis="conditional", max_adversarial_pass_on_fail=2, max_unstable_rate=0.5,
            min_repeat_cases=20, max_indeterminate_fraction=0.5,
            min_inter_labeler_agreement=None,
            accepted_label_provenance=frozenset({LabelProvenance.SYNTHETIC}),
            require_verified_integrity=False, validity_days=90, max_dataset_age_days=365,
            demonstration_only=True,
        )  # fmt: skip
        starting = CalibrationPolicy.starting_point()
        for name, policy in (
            ("demonstration policy", demo),
            ("starting-point policy", starting),
        ):
            decision = assess_admission(
                assessment, table_a.fingerprint, policy, NOW, hmac_key=DEMO_KEY
            )
            show(
                f"5. Status under the {name}",
                f"status={decision.status.value}  admissible={decision.admissible}  "
                f"integrity={decision.integrity}",
                *(f"{c.group}/{c.name}: {c.verdict}" for c in decision.failing()[:6]),
            )

        gate = CalibrationGate(
            judge_a, model_a, assessment, demo, clock=lambda: NOW, hmac_key=DEMO_KEY
        )
        coordinator = JudgeCoordinator(
            [IndicatorBinding("answer-correctness", judge_a, admission=gate)]
        )
        sdk = AgentReliability()
        request = cases[0].case.request()
        with (
            sdk.run(agent_id="demo", name="Demo", version="1") as run,
            coordinator.scope(run) as scope,
        ):
            disposition = scope.evaluate_sync("answer-correctness", request)
        show(
            "6. The coordinator gate",
            f"demonstration status is never admissible -> {disposition.value}",
            f"no provider call, no evidence, run health {run.measurement_health.health.value}",
            f"coverage: {coordinator.coverage().indicators[0].describe()}",
        )
        assert disposition is EvaluationDisposition.SKIPPED_BY_ADMISSION

        drift = assess_drift(
            assessment, table_b.fingerprint, starting, NOW + timedelta(days=120)
        )
        show(
            "7. Drift indicators (advisory)",
            f"fingerprint_changed: {drift['fingerprint_changed']['state']} "
            f"({', '.join(drift['fingerprint_changed']['differing_components'])})",
            f"calibration_expired: {drift['calibration_expired']['state']}",
            f"dataset_stale: {drift['dataset_stale']['state']}",
        )
        show(
            "Caveats",
            "The data is synthetic; a human-label policy therefore cannot calibrate it.",
            "'calibrated' would mean: meets the caller's policy on a named held-out set,",
            "for this exact configuration and declared model, at that time. Not production accuracy.",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

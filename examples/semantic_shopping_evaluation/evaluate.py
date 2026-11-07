# ruff: noqa: E501 -- long strings and narrative lines read best unbroken.
"""Run the semantic checks over the golden dataset and measure agreement with the expected outcomes.

    python -m examples.semantic_shopping_evaluation.evaluate run    MODEL OUT.json   # live local model (slow, non-deterministic)
    python -m examples.semantic_shopping_evaluation.evaluate report OUT.json         # offline: metrics from a recorded run

Every case is one agent run with its own scope; only the semantic indicators are evaluated here. The output keeps no answer text.
"""

from __future__ import annotations

import json
import statistics
import sys
from decimal import Decimal
from pathlib import Path

from agent_reliability.experimental.judge import (
    JudgeLimits,
    SemanticChecks,
    wilson_interval,
)
from agent_reliability.sdk import AgentReliability

from ..judge_providers import local_runtime_provider
from .golden import cases, relabel

CHECK_OF = {"groundedness": "groundedness", "relevance": "relevance"}


class _Null:
    def emit(self, event: object) -> None:
        return None


def run(model: str, out: str, max_output_tokens: int = 512) -> None:
    label = model.replace(":", "-")
    limits = JudgeLimits(
        provider_timeout_seconds=120,
        evaluation_deadline_seconds=240,
        max_output_tokens=max_output_tokens,
        max_attempts=2,
    )
    checks = SemanticChecks(
        local_runtime_provider(model=model),
        model_label=label,
        checks=tuple(CHECK_OF),
        limits=limits,
    )
    sdk = AgentReliability(sink=_Null())
    rows = []
    for case in cases():
        with (
            sdk.run(
                agent_id="shopping-demo", name="Shopping demo", version="1"
            ) as handle,
            checks.scope(handle) as scope,
        ):
            for dimension, expected in case["labels"].items():
                if expected is None:
                    continue
                given = {"context": case["context"], "question": case["question"]}
                if dimension == "relevance":
                    given = {"question": case["question"], "context": case["context"]}
                v = scope.check(CHECK_OF[dimension], case["answer"], **given)
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "check": dimension,
                        "expected": expected,
                        "difficulty": case["difficulty"],
                        "source": case["source"],
                        "status": v.status.value,
                        "outcome": v.outcome.value if v.outcome else None,
                        "reason_code": v.reason_code,
                        "failure_class": v.failure_class,
                        "latency_ms": v.latency_ms,
                        "input_tokens": v.input_tokens,
                        "output_tokens": v.output_tokens,
                    }
                )
                print(
                    case["case_id"],
                    dimension,
                    expected,
                    "->",
                    v.status.value,
                    v.outcome.value if v.outcome else None,
                    v.latency_ms,
                    "ms",
                    flush=True,
                )
    Path(out).write_text(
        json.dumps(
            {
                "model_label": label,
                "max_output_tokens": max_output_tokens,
                "rubrics": {
                    "groundedness": "judge-groundedness@2026-10.r1",
                    "relevance": "judge-answer-relevance@2026-11.r1",
                },
                "rows": rows,
                "coverage": checks.coverage(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _pct(n: int, d: int) -> float | None:
    return None if d == 0 else round(100 * n / d, 1)


def metrics(
    rows: list[dict],
    *,
    input_price: Decimal = Decimal(0),
    output_price: Decimal = Decimal(0),
) -> dict:
    out: dict = {}
    for check in sorted({r["check"] for r in rows}):
        rs = [r for r in rows if r["check"] == check]
        decided = [r for r in rs if r["status"] in ("determinate", "unknown")]
        human_all = [r for r in rs if r["expected"] in ("pass", "fail")]
        human_det = [r for r in decided if r["expected"] in ("pass", "fail")]
        jdet = [r for r in human_det if r["status"] == "determinate"]
        agree = sum(1 for r in jdet if r["outcome"] == r["expected"])
        fp = [
            r["case_id"]
            for r in jdet
            if r["outcome"] == "pass" and r["expected"] == "fail"
        ]
        fn = [
            r["case_id"]
            for r in jdet
            if r["outcome"] == "fail" and r["expected"] == "pass"
        ]
        human_fail = sum(1 for r in human_det if r["expected"] == "fail")
        human_pass = sum(1 for r in human_det if r["expected"] == "pass")
        hu = [r for r in rs if r["expected"] == "unknown"]
        lat = sorted(r["latency_ms"] for r in rs if r["latency_ms"])
        tin = sum(r["input_tokens"] or 0 for r in rs)
        tout = sum(r["output_tokens"] or 0 for r in rs)
        wi = wilson_interval(agree, len(jdet))
        out[check] = {
            "cases": len(rs),
            "evaluator_failures": sum(
                1 for r in rs if r["status"] == "evaluator_failure"
            ),
            "evaluator_failure_classes": sorted(
                {r["failure_class"] for r in rs if r["failure_class"]}
            ),
            "judge_unknown_on_human_determinate": sum(
                1 for r in human_det if r["status"] == "unknown"
            ),
            "human_determinate": len(human_all),
            "evaluator_failures_on_human_determinate": sum(
                1 for r in human_all if r["status"] == "evaluator_failure"
            ),
            "agreement_on_judge_determinate": {
                "n": len(jdet),
                "agree": agree,
                "pct": _pct(agree, len(jdet)),
                "wilson95": wi and [round(wi[0] * 100, 1), round(wi[1] * 100, 1)],
            },
            "false_positives_judge_pass_human_fail": {
                "count": len(fp),
                "of_human_fail": human_fail,
                "cases": fp,
            },
            "false_negatives_judge_fail_human_pass": {
                "count": len(fn),
                "of_human_pass": human_pass,
                "cases": fn,
            },
            "human_unknown": {
                "n": len(hu),
                "judge_unknown": sum(1 for r in hu if r["status"] == "unknown"),
            },
            "latency_ms": {
                "p50": lat and int(statistics.median(lat)),
                "p95": lat and lat[min(len(lat) - 1, int(0.95 * len(lat)))],
                "model_calls": len(lat),
            },
            "tokens": {"input": tin, "output": tout},
            "cost": str(
                (
                    Decimal(tin) / 1000 * input_price
                    + Decimal(tout) / 1000 * output_price
                ).quantize(Decimal("0.0001"))
            ),
        }
    return out


def report(path: str, mode: str = "original", source: str | None = None) -> None:
    """mode: original | corrected | clear (see golden.relabel); source: agent_run | constructed."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = relabel(data["rows"], mode)
    if source:
        rows = [r for r in rows if r["source"] == source]
    out = {
        "model_label": data["model_label"],
        "label_mode": mode,
        "source": source or "all",
        "metrics": metrics(rows),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    {
        "run": lambda: run(sys.argv[2], sys.argv[3], *(int(a) for a in sys.argv[4:5])),
        "report": lambda: report(sys.argv[2], *sys.argv[3:5]),
    }[sys.argv[1]]()

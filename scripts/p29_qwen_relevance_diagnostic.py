"""Reproducible Qwen3-14B relevance-citation diagnostic and one bounded config comparison.

LOCAL ONLY (Ollama at the default local endpoint). Not a calibration and not a
quality claim: it records evidence identifiers, the raw JSON members (never
answer text beyond the model's own short ``reason``), and strict-parser outcomes.
The citation validator is used unmodified.

  diagnose  three golden cases, relevance only: what blocks were sent, what the model cited
  compare   one comparison on SEPARATE synthetic examples (smoke_examples.json):
            baseline rubric vs the same rubric plus one trusted operator criterion
"""
import argparse, json, pathlib, re, statistics, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from examples.judge_providers import default_post_json, local_runtime_provider  # noqa: E402
from examples.semantic_shopping_evaluation.golden import cases  # noqa: E402
from agent_reliability.experimental.judge import JudgeLimits, SemanticChecks  # noqa: E402
from agent_reliability.experimental.judge.core import parse_output  # noqa: E402
from agent_reliability.experimental.judge.rubric import Rubric  # noqa: E402
from agent_reliability.sdk import AgentReliability  # noqa: E402
import agent_reliability.experimental.judge as _j  # noqa: E402

RUBRIC = pathlib.Path(_j.__file__).parent / "rubrics"
EXAMPLES = ROOT / "docs/p29-calibration/human-calibration/qwen-relevance/smoke_examples.json"
NO_CONTEXT_CRITERION = {
    "id": "no-context-blocks",
    "text": "No context blocks are supplied for this evaluation. The citations member must be [] "
            "(the question and answer blocks are not context blocks and must not be cited).",
}


class Null:
    def emit(self, e):
        return None


def _v(x):
    return getattr(x, "value", x) if x is not None else None


def relevance_rubric(variant):
    doc = json.loads((RUBRIC / "judge-answer-relevance.json").read_text())
    if variant == "operator_note":
        doc["rubric_version"] = "2026-11.r1-smoke1"
        doc["criteria"].append(NO_CONTEXT_CRITERION)
    return doc


def make_checks(model, variant, mode, max_tokens, log):
    def post(url, headers, body, timeout):
        if mode == "nothink":
            body = {**body, "reasoning_effort": "none"}
        t = time.perf_counter()
        reply = default_post_json(url, headers, body, timeout)
        msgs = body["messages"]
        log.append({"latency_s": time.perf_counter() - t, "system": msgs[0]["content"], "user": msgs[1]["content"],
                    "raw": ((reply.get("choices") or [{}])[0].get("message") or {}).get("content"),
                    "finish": (reply.get("choices") or [{}])[0].get("finish_reason")})
        return reply

    rub = {}
    rubric_doc = relevance_rubric(variant)
    rub["relevance"] = Rubric.from_dict(rubric_doc) if hasattr(Rubric, "from_dict") else None
    limits = JudgeLimits(provider_timeout_seconds=180, evaluation_deadline_seconds=300,
                         max_output_tokens=max_tokens, max_attempts=1)
    return SemanticChecks(local_runtime_provider(model=model, post_json=post), model_label=model.replace(":", "-"),
                          checks=("groundedness", "relevance"), limits=limits, rubrics=rub), rub["relevance"]


def run(checks, items):
    sdk = AgentReliability(sink=Null())
    out = []
    for it in items:
        with sdk.run(agent_id="smoke", name="smoke", version="1") as h, checks.scope(h) as scope:
            dim = it["dim"]
            kw = ({"answer": it["answer"], "question": it["question"]} if dim == "relevance"
                  else {"answer": it["answer"], "context": it["context"]})
            v = scope.check(dim, **kw)
            out.append({"id": it["id"], "dim": dim, "expected": it.get("expected"), "status": _v(v.status),
                        "outcome": _v(v.outcome), "failure": _v(v.failure_class) if hasattr(v, "failure_class") else None})
    return out


def diagnose(args):
    log = []
    checks, rubric = make_checks(args.model, "baseline", args.mode, args.max_tokens, log)
    items = [{"id": c["case_id"], "dim": "relevance", "answer": c["answer"], "question": c["question"],
              "expected": c["labels"]["relevance"]} for c in cases()[:3]]
    rows = run(checks, items)
    report = []
    for row, call in zip(rows, log):
        headers = re.findall(r"<<<BEGIN [0-9a-f]+ (role=\S+ index=\d+) trust=\S+>>>", call["user"])
        context_count = sum(h.startswith("role=context") for h in headers)
        try:
            doc = json.loads(call["raw"])
        except Exception:
            doc = None
        cited = doc.get("citations") if isinstance(doc, dict) else None
        try:
            parse_output(call["raw"], rubric, context_count)
            parse = "accepted"
        except Exception as e:  # strict parser, unmodified
            parse = f"rejected:{e.args[0] if e.args else type(e).__name__}"
        report.append({"case": row["id"], "evidence_headers_sent": headers, "context_blocks_sent": context_count,
                       "rubric_require_citations": rubric.require_citations,
                       "system_citation_rule": [l for l in call["system"].splitlines() if "citation" in l.lower()],
                       "model_members": {k: doc.get(k) for k in ("verdict", "code", "confidence", "citations")} if isinstance(doc, dict) else None,
                       "cited": cited, "strict_parse": parse, "finish": call["finish"]})
    print(json.dumps(report, indent=1))
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(report, indent=1))


def compare(args):
    items = json.loads(EXAMPLES.read_text())["examples"]
    result = {}
    for variant in ("baseline", "operator_note"):
        log = []
        checks, _ = make_checks(args.model, variant, args.mode, args.max_tokens, log)
        rows = run(checks, items)
        n = len(rows)
        fail = sum(r["status"] == "evaluator_failure" for r in rows)
        det = [r for r in rows if r["status"] == "determinate"]
        result[variant] = {
            "evaluations": n, "evaluator_failures": fail, "evaluator_failure_rate": round(fail / n, 4),
            "failure_classes": sorted({r["failure"] for r in rows if r["failure"]}),
            "by_dim_failures": {d: sum(r["status"] == "evaluator_failure" and r["dim"] == d for r in rows) for d in ("groundedness", "relevance")},
            "determinate_agreeing_with_author_intent": sum(r["outcome"] == r["expected"] for r in det),
            "determinate": len(det),
            "latency_p50_s": round(statistics.median(c["latency_s"] for c in log), 2),
            "rows": rows}
    print(json.dumps({k: {x: y for x, y in v.items() if x != "rows"} for k, v in result.items()}, indent=1))
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(result, indent=1))


p = argparse.ArgumentParser()
p.add_argument("cmd", choices=["diagnose", "compare"])
p.add_argument("--model", default="qwen3:14b")
p.add_argument("--mode", default="nothink", choices=["nothink", "think"])
p.add_argument("--max-tokens", type=int, default=512)
p.add_argument("--out")
a = p.parse_args()
{"diagnose": diagnose, "compare": compare}[a.cmd](a)

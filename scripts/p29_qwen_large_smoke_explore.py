"""EXPLORATORY (not part of the preregistered measurement): which verdict/code pairs
did Qwen return on the cases that failed with invalid_code? Re-runs only those cases with
the preregistered configuration and records the model's verdict and code (short closed
tokens), never answer text. Results must be reported separately from RESULTS.json."""

import collections, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
D = ROOT / "docs/p29-calibration/human-calibration/qwen-large-smoke"
from examples.judge_providers import default_post_json, local_runtime_provider
from agent_reliability.experimental.judge import JudgeLimits, JudgePolicy, SemanticChecks
from agent_reliability.sdk import AgentReliability

res = json.loads((D / "RESULTS.json").read_text())
failed = {r["case_id"] for r in res["rows"] if r["status"] == "evaluator_failure"}
cases = [c for c in json.loads((D / "dataset.json").read_text())["cases"] if c["case_id"] in failed]
raw = []


def post(url, headers, body, timeout):
    reply = default_post_json(url, headers, {**body, "reasoning_effort": "none"}, timeout)
    text = ((reply.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    try:
        doc = json.loads(text)
        raw.append((doc.get("verdict"), doc.get("code")))
    except Exception:
        raw.append(("unparseable", None))
    return reply


class Null:
    def emit(self, e): return None


cfg = json.loads((D / "PREREGISTERED_CONFIG.json").read_text())
lim = cfg["limits"]
checks = SemanticChecks(local_runtime_provider(model="qwen3:14b", post_json=post), model_label="qwen3-14b", checks=("relevance",),
                        limits=JudgeLimits(provider_timeout_seconds=lim["provider_timeout_seconds"], evaluation_deadline_seconds=lim["evaluation_deadline_seconds"], max_output_tokens=cfg["max_output_tokens"], max_attempts=lim["max_attempts"], repair_attempts=lim["repair_attempts"]),
                        policy=JudgePolicy(prompt_template="jp2"))
sdk = AgentReliability(sink=Null())
for c in cases:
    kw = {"answer": c["answer"], "question": c["question"]}
    if c["context"]: kw["context"] = c["context"]
    with sdk.run(agent_id="x", name="x", version="1") as h, checks.scope(h) as s:
        s.check("relevance", **kw)
count = collections.Counter(raw)
out = {"cases_rerun": len(cases), "provider_replies": len(raw), "verdict_code_pairs": {f"{v}/{c}": n for (v, c), n in count.most_common()}}
(D / "EXPLORATORY_invalid_code.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))

# ruff: noqa: E501 -- long strings and narrative lines read best unbroken.
"""Deliver semantic evidence to a Gentlity platform over HTTP (customer side of the end-to-end roundtrip).

The judge here is a REPLAY provider: it answers each check with the outcome recorded in a live-model run (expected/verdicts-*.json), so the
roundtrip is deterministic and needs no model. Four extra runs inject REAL evaluator faults (a provider that outlives its deadline, malformed
output, a provider error, an unreachable-provider refusal) to prove they arrive as evaluator failures and never as an agent FAIL. Every answer
carries a marker string so the platform side can prove no evaluated text was stored.

    GENTLITY_MACHINE_TOKEN=... python -m examples.semantic_shopping_evaluation.deliver CONFIG.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from uuid import UUID

from agent_reliability.adapters.http_event_sink import HTTPEventSink
from agent_reliability.domain import AgentIdentity
from agent_reliability.experimental.judge import (
    JudgeLimits,
    ProviderReply,
    SemanticChecks,
)
from agent_reliability.experimental.judge.testing import judge_reply
from agent_reliability.sdk import AgentReliability

from .golden import cases

MARKER = "ZXPRIVATE-7731-MARKER"
FAULTS = ["timeout", "malformed", "provider_error", "refused"]


class Replay:
    """Blocking provider: replies per the recorded verdict of the current case, or misbehaves on purpose."""

    provider_label = "replay"
    reports_tokens = False

    def __init__(self) -> None:
        self.mode: tuple[str, str, str] = ("pass", "", "")

    def complete(self, call):
        kind, outcome, code = self.mode
        if kind == "timeout":
            time.sleep(call.deadline_seconds + 0.5)
        if kind == "malformed":
            return ProviderReply("I believe this answer is fine, so: PASS")
        if kind == "provider_error":
            raise ConnectionError("simulated provider outage")
        if kind == "refused":
            from agent_reliability.experimental.judge import JudgeProviderRefusedError

            raise JudgeProviderRefusedError()
        return ProviderReply(
            judge_reply(
                outcome,
                code,
                "high",
                [0]
                if outcome == "pass" and "groundedness" in code
                else [0]
                if outcome == "pass"
                else [],
            )
        )


def main(config_path: str) -> None:
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    token = os.environ["GENTLITY_MACHINE_TOKEN"]
    ident = config["identity"]
    indicators = ["semantic-groundedness", "semantic-relevance"]
    sink = HTTPEventSink(
        endpoint=config["endpoint"],
        credential_provider=lambda: token,
        deployment_id=UUID(config["deployment_id"]),
        expected_agent=AgentIdentity(
            ident["agent_id"], ident["name"], ident["version"], ident["environment"]
        ),
        indicator_allowlist=indicators,
        retry_max_attempts=3,
    )
    sdk = AgentReliability(sink=sink)
    provider = Replay()
    checks = SemanticChecks(
        provider,
        model_label=config["model_label"],
        checks=("groundedness", "relevance"),
        limits=JudgeLimits(
            provider_timeout_seconds=0.4,
            evaluation_deadline_seconds=0.8,
            max_attempts=1,
            repair_attempts=0,
        ),
    )
    recorded = json.loads(Path(config["verdicts"]).read_text(encoding="utf-8"))["rows"]
    by_case: dict[str, dict[str, dict]] = {}
    for r in recorded:
        by_case.setdefault(r["case_id"], {})[r["check"]] = r
    data = {c["case_id"]: c for c in cases()}
    verdicts = []
    for case_id, per_check in by_case.items():
        case = data[case_id]
        with (
            sdk.run(
                agent_id=ident["agent_id"],
                name=ident["name"],
                version=ident["version"],
                environment=ident["environment"],
            ) as run,
            checks.scope(run) as scope,
        ):
            for check, row in per_check.items():
                if row["status"] == "evaluator_failure":
                    continue  # a real live-model failure is replayed below as an injected fault, not guessed
                code = (row["reason_code"] or "").split(".", 1)[-1]
                provider.mode = ("ok", row["outcome"] or "unknown", code)
                v = scope.check(
                    check,
                    case["answer"] + " " + MARKER,
                    context=[*case["context"], MARKER],
                    question=case["question"] + " " + MARKER,
                )
                verdicts.append(
                    {
                        "case_id": case_id,
                        "check": check,
                        "status": v.status.value,
                        "outcome": v.outcome.value if v.outcome else None,
                        "failure_class": v.failure_class,
                    }
                )
    for fault in FAULTS:
        provider.mode = (fault, "", "")
        with (
            sdk.run(
                agent_id=ident["agent_id"],
                name=ident["name"],
                version=ident["version"],
                environment=ident["environment"],
            ) as run,
            checks.scope(run) as scope,
        ):
            v = scope.check(
                "groundedness",
                "Rs 1,999 " + MARKER,
                context=[MARKER],
                question="price?",
            )
            verdicts.append(
                {
                    "case_id": f"fault-{fault}",
                    "check": "groundedness",
                    "status": v.status.value,
                    "outcome": v.outcome.value if v.outcome else None,
                    "failure_class": v.failure_class,
                }
            )
    snapshot = sink.close(60)
    det = config.get("det_deployment_id")
    deterministic = None
    if det:  # deterministic evidence in its OWN deployment: measurement health is counted per deployment and window
        from agent_reliability.domain import EvaluationOutcome

        d = config["det_identity"]
        det_sink = HTTPEventSink(
            endpoint=config["endpoint"],
            credential_provider=lambda: token,
            deployment_id=UUID(det),
            expected_agent=AgentIdentity(
                d["agent_id"], d["name"], d["version"], d["environment"]
            ),
            indicator_allowlist=["price-exact"],
            retry_max_attempts=3,
        )
        det_sdk = AgentReliability(sink=det_sink)
        for i in range(6):
            with det_sdk.run(
                agent_id=d["agent_id"],
                name=d["name"],
                version=d["version"],
                environment=d["environment"],
            ) as run:
                run.record(
                    indicator="price-exact",
                    outcome=EvaluationOutcome.PASS if i < 5 else EvaluationOutcome.FAIL,
                )
        deterministic = {
            k.value: n for k, n in det_sink.close(60).counts_by_disposition.items() if n
        }
    counts = {
        str(k.value): int(n) for k, n in snapshot.counts_by_disposition.items() if n
    }
    Path(config["output"]).write_text(
        json.dumps(
            {
                "verdicts": verdicts,
                "delivery": {
                    "counts": counts,
                    "queue_depth": snapshot.queue_depth,
                    "pause_reason": snapshot.pause_reason,
                },
                "coverage": checks.coverage(),
                "deterministic_delivery": deterministic,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main(sys.argv[1])

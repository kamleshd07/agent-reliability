"""Documentation checks: S00 (ADR), S12-AC04 (user docs), CON-17 and I-P29-4/5."""

from __future__ import annotations

import asyncio
import pathlib

import pytest

from agent_reliability.experimental.judge import (
    IndicatorBinding,
    JudgeCoordinator,
    LLMJudge,
)
from agent_reliability.experimental.judge.testing import FakeProvider
from agent_reliability.ports.events import EvaluationRecorded, RunCompleted, RunStarted
from agent_reliability.sdk import AgentReliability
from agent_reliability.sdk.evaluator_runner import EvaluatorRunner
from tests.fakes.p29_judge import (
    HealthSink,
    good_reply,
    grounded_request,
    named_rubrics,
)

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[3]
ADR = (
    ROOT / "docs/adr/0010-experimental-judge-adapter-amends-adr-0007-decision-9.md"
).read_text()
EVALUATE = " ".join((ROOT / "docs/EVALUATE.md").read_text().split())


def test_p29_s00_ac01_adr_cites_adr_0004_0007_0009_and_the_package() -> None:
    for needle in (
        "ADR-0004",
        "ADR-0007",
        "ADR-0009",
        "P29-DESIGN-001",
        "docs/roadmap/P29",
    ):
        assert needle in ADR
    status = ADR.split("## Status", 1)[1].split("## ", 1)[0]
    assert "Accepted" in status and "owner-approved on 2026-10-16" in status
    assert "unsigned" in status and "not recorded" in status
    assert "provisional" in status  # the number is not owner-assigned
    sections = [
        "## Status", "## Context", "## Decision", "## Alternatives Considered",
        "## Consequences", "## Security Impact", "## Performance Impact",
        "## Compatibility Impact",
    ]  # fmt: skip
    positions = [ADR.index(s) for s in sections]
    assert positions == sorted(positions)  # repository ADR format (docs/adr/README.md)


def test_p29_s00_ac02_adr_states_dispositions_provider_extra_and_no_wire_member() -> (
    None
):
    for needle in (
        "P29-D01",
        "P29-D02",
        "P29-D04",
        "P29-D11",
        "P29-D12",
        "adds no HTTP endpoint",
    ):
        assert needle in ADR
    assert "adds no HTTP endpoint, payload kind, field" in ADR
    assert "amended" in ADR and "decision 9" in ADR.lower()


def test_p29_s00_historical_decisions_are_preserved_in_adr_0007() -> None:
    adr7 = (
        ROOT / "docs/adr/0007-evaluator-architecture-and-provenance-semantics.md"
    ).read_text()
    flat = " ".join(adr7.split())
    assert (
        "No global registry, plugin discovery, remote calls, timeout machinery, "
        "or LLM adapter is added." in flat
    )
    assert "ADR-0010" in adr7.split("## Context", 1)[0]
    index = (ROOT / "docs/adr/README.md").read_text()
    assert "0010-experimental-judge-adapter-amends-adr-0007-decision-9.md" in index


def test_p29_s00_versioning_and_ga_contract_entries() -> None:
    versioning = (ROOT / "docs/VERSIONING.md").read_text()
    ga = (ROOT / "docs/GA_CONTRACT.md").read_text()
    assert "agent_reliability.experimental.judge" in versioning
    assert "Experimental namespace: `agent_reliability.experimental.judge`" in ga
    assert "unreleased" in ga and "EXPERIMENTAL" in ga


def test_p29_s12_ac04_user_docs_carry_privacy_pass_meaning_and_non_claims() -> None:
    for needle in (
        "### Privacy statement",
        "### Meaning of PASS per dimension",
        "no accuracy claim",
        "never an authoritative outcome",
        "Failures and UNKNOWN leave the reliability denominator",
        "on_no_data",
        "not indicator-scoped",
        "Budget and overload limits",
        "Run health",
        "Coverage monitoring",
        "Scope separation",
        "Failure alerting",
        "No-data policy",
    ):
        assert needle in EVALUATE, needle
    readme = (ROOT / "README.md").read_text()
    assert "experimental, unreleased" in readme and "uncalibrated" in readme


def test_p29_con17_cohort_convention_and_plus_hazard_are_documented() -> None:
    assert (
        "also change the indicator name" in EVALUATE and "groundedness-v2" in EVALUATE
    )
    assert "1.0.0+build5" in EVALUATE and "rejected by the exporter" in EVALUATE


def test_p29_i_p29_4_a_semantic_result_writes_only_evaluation_evidence() -> None:
    sink = HealthSink()
    sdk = AgentReliability(sink=sink)  # type: ignore[arg-type]

    class Quiet:
        def handle(self, diagnostic: object) -> None:
            return None

    coordinator = JudgeCoordinator(
        [
            IndicatorBinding(
                "groundedness",
                LLMJudge(
                    rubric=named_rubrics()["gr-cit"],
                    provider=FakeProvider([good_reply()]),
                    model_label="m",
                ),
            )
        ],
        runner=EvaluatorRunner(diagnostic_handler=Quiet()),  # type: ignore[arg-type]
    )

    async def go() -> None:
        with sdk.run(agent_id="a", name="A", version="1") as run:
            async with coordinator.scope(run) as scope:
                await scope.evaluate("groundedness", grounded_request())

    asyncio.run(go())
    kinds = {type(e) for e in sink.events}
    # no outcome-observation or other authoritative event type is ever produced
    assert kinds == {RunStarted, EvaluationRecorded, RunCompleted}


RUNBOOK = " ".join((ROOT / "docs/P29_PILOT_RUNBOOK.md").read_text().split())
_LOG_PATH = ROOT / "docs/P29_IMPLEMENTATION_LOG.md"
# The internal implementation log is not in the sdist; the tests that read it are
# source-checkout checks and skip when it is absent.
LOG = " ".join(_LOG_PATH.read_text().split()) if _LOG_PATH.exists() else ""


@pytest.mark.skipif(
    not LOG, reason="internal implementation log not in this distribution"
)
def test_p29_s09_ac07_log_states_the_sink_exercised_and_makes_no_tls_claim() -> None:
    section = LOG.split("## S09 - P28 wiring", 1)[1].split("## S10", 1)[0]
    assert "HTTPEventSink" in section and "httpx.MockTransport" in section
    assert "D-1 TLS fix is present" in section
    assert "no** claim about TLS-verification handling" in section
    assert "NOT EXERCISED" in section or "NOT_EXERCISED" in section


def test_p29_s11_ac07_runbook_lists_prerequisites_commands_outputs_and_fallbacks() -> (
    None
):
    for needle in (
        "## 1. Prerequisites",
        "## 2. Commands and expected output",
        "python examples/judge_pilot_demo.py",
        "Primary pilot",
        "Degraded fallback",
        "Last resort",
        "dev-header",
        "no authentication claim",
        "not shared TEST",
    ):
        assert needle in RUNBOOK, needle


def test_p29_s11_ac08_ac09_runbook_states_path_limits_and_every_safeguard_status() -> (
    None
):
    for needle in (
        "No pilot was run",
        "nothing is committed",
        "D-1",
        "Survivorship",
        "99 failed attempts plus 1 PASS reads as reliability 1.0",
        "UNKNOWN coverage",
        "Gate reach",
        "partial outage is not covered",
        "not indicator-scoped",
    ):
        assert needle.lower() in RUNBOOK.lower(), needle
    for gate in ("SG-1", "SG-2", "SG-3", "SG-4", "SG-5", "SG-6"):
        row = RUNBOOK.split(f"| {gate} ", 1)[1].split("| SG-", 1)[0]
        assert "NOT SATISFIED" in row, gate  # honest: no pilot condition is met
    assert "IMPLEMENTED-in-SDK" in RUNBOOK and "PROCESS-GATE" in RUNBOOK
    assert "does not yet cover pilot use" in RUNBOOK


def test_review_f2_f3_f9_f11_docs_state_timeout_gate_and_recording_semantics() -> None:
    for needle in (
        "### Timeouts, blocking providers and shutdown",
        "Sync (`SyncLLMJudge`) is best effort",
        "The real bound is your provider's own socket/client timeout",
        "ExecutorSyncProvider",
        "Tokens of discarded late replies are not counted",
        "### The recording gate: what runs inside it",
        "sink and diagnostic handler inside that gate",
        "must be non-blocking",
        "raises `RuntimeError` instead of deadlocking",
        '"Recorded" means *handed to the run handle*',
        "`judge_abstained` is *not* enforced",
    ):
        assert needle in EVALUATE, needle
    adr = " ".join(ADR.split())
    assert "Sync timeouts are best effort" in adr
    assert "Customer sinks run inside the recording gate" in adr
    assert "must not re-enter the scope" in adr
    assert "Sink behavior (gate)" in RUNBOOK and "best effort" in RUNBOOK
    readme = " ".join((ROOT / "README.md").read_text().split())
    assert "timeout is best effort" in readme and "ExecutorSyncProvider" in readme


def test_review_f13_readme_places_the_p29_paragraph_before_the_license_section() -> (
    None
):
    readme = (ROOT / "README.md").read_text()
    judge = readme.index("### LLM-judge evaluators (experimental, unreleased)")
    assert judge < readme.index("## Documentation") < readme.index("## License")

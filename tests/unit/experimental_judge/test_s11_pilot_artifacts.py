"""P29-S11 (SDK-side artifacts only): local demo, capture and replay validation.

Nothing here contacts a platform. The loopback stub is an in-process server on
127.0.0.1; the replay script is never pointed at anything else.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[3]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False
    )


def check_capture(path: pathlib.Path) -> None:
    """Assert the scenario from per-run keyed data (delivery order is no contract)."""
    lines = [json.loads(x) for x in path.read_text().splitlines()]
    runs: dict[str, list[dict[str, Any]]] = {}
    for envelope in lines:
        runs.setdefault(envelope["producer_run_id"], []).append(envelope["payload"])
    assert len(runs) == 3
    outcomes_by_indicator: dict[str, list[str]] = {}
    healths: list[str] = []
    failing_runs = 0
    for payloads in runs.values():
        outcomes = [p for p in payloads if p["kind"] == "evaluation_outcome"]
        failures = [p for p in payloads if p["kind"] == "evaluation_execution_failure"]
        (health,) = [p["health"] for p in payloads if p["kind"] == "measurement_health"]
        healths.append(health)
        for p in outcomes:
            outcomes_by_indicator.setdefault(p["indicator"], []).append(p["outcome"])
            assert p["provenance"]["deterministic"] is False
        if failures:  # the Q3 run: provider stopped, no verdicts at all
            failing_runs += 1
            assert not outcomes and health == "unavailable"
            assert sorted(f["indicator"] for f in failures) == [
                "answer-correctness",
                "groundedness",
            ]
            assert {f["exception_type"] for f in failures} == {
                "JudgeProviderUnavailableError"
            }
        else:
            assert health == "healthy" and len(outcomes) == 2
    assert failing_runs == 1 and sorted(healths) == [
        "healthy",
        "healthy",
        "unavailable",
    ]
    assert {k: sorted(v) for k, v in outcomes_by_indicator.items()} == {
        "answer-correctness": ["fail", "pass"],  # Q1 PASS, Q2 FAIL
        "groundedness": ["fail", "pass"],
    }
    codes = {
        p["reason_code"]
        for payloads in runs.values()
        for p in payloads
        if p["kind"] == "evaluation_outcome"
    }
    assert codes == {
        "answer-correctness.consistent_with_reference",
        "answer-correctness.contradicts_reference",
        "groundedness.supported_by_context",
        "groundedness.unsupported_claim",
    }
    text = path.read_text()
    for needle in ("refund", "30 days", "90 days", "[Q1]", "[Q2]", "[Q3]"):
        assert needle not in text


def test_p29_s11_demo_runs_locally_and_captures_the_two_question_scenario(
    tmp_path: pathlib.Path,
) -> None:
    out = tmp_path / "capture.jsonl"
    completed = run("examples/judge_pilot_demo.py", "--out", str(out))
    assert completed.returncode == 0 and completed.stderr == ""
    check_capture(out)
    assert (
        "execution failures 33.3%" in completed.stdout
    )  # failure rate beside reliability


def test_p29_s11_demo_assertions_are_stable_over_64_parallel_runs(
    tmp_path: pathlib.Path,
) -> None:
    """The earlier list-order assertions failed in about 1 of 8 runs under load."""
    import asyncio
    import contextlib
    import io
    import sys as _sys
    from concurrent.futures import ThreadPoolExecutor

    _sys.path.insert(0, str(ROOT / "examples"))
    try:
        import judge_pilot_demo as demo
    finally:
        _sys.path.remove(str(ROOT / "examples"))

    def one(index: int) -> pathlib.Path:
        out = tmp_path / f"capture-{index}.jsonl"
        asyncio.run(demo.main(out))
        return out

    with contextlib.redirect_stdout(io.StringIO()), ThreadPoolExecutor(8) as pool:
        outputs = list(pool.map(one, range(64)))
    for out in outputs:
        check_capture(out)


def test_p29_s11_replay_dry_run_validates_and_sends_nothing(
    tmp_path: pathlib.Path,
) -> None:
    out = tmp_path / "capture.jsonl"
    assert run("examples/judge_pilot_demo.py", "--out", str(out)).returncode == 0
    completed = run("examples/judge_pilot_replay.py", str(out))
    assert completed.returncode == 0
    assert "validated 15 envelopes" in completed.stdout
    assert "dry run: nothing was sent" in completed.stdout


def test_p29_s11_replay_rejects_malformed_and_unsafe_input(
    tmp_path: pathlib.Path,
) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        '{"schema_version": 2, "payload": {"kind": "run_lifecycle"}, "extra": 1}\n'
    )
    assert run("examples/judge_pilot_replay.py", str(bad)).returncode != 0
    bad.write_text("not json\n")
    assert run("examples/judge_pilot_replay.py", str(bad)).returncode != 0
    good = tmp_path / "good.jsonl"
    assert run("examples/judge_pilot_demo.py", "--out", str(good)).returncode == 0
    token = tmp_path / "token"
    token.write_text("t")
    refused = run(
        "examples/judge_pilot_replay.py",
        str(good),
        "--post",
        "http://platform.example/x",
        "--token-file",
        str(token),
    )
    assert refused.returncode != 0 and "https" in refused.stderr
    assert (
        run(
            "examples/judge_pilot_replay.py", str(good), "--post", "https://x.invalid/y"
        ).returncode
        != 0
    )


def test_p29_s11_replay_post_path_against_an_in_process_loopback_stub(
    tmp_path: pathlib.Path,
) -> None:
    received: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            received.append(
                {
                    "auth": self.headers["Authorization"],
                    "body": json.loads(self.rfile.read(length)),
                }
            )
            self.send_response(201)
            self.end_headers()

        def log_message(self, *args: Any) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        good = tmp_path / "good.jsonl"
        assert run("examples/judge_pilot_demo.py", "--out", str(good)).returncode == 0
        token = tmp_path / "token"
        token.write_text("stub-token\n")
        endpoint = f"http://127.0.0.1:{server.server_address[1]}/api/v1/evidence/runs"
        completed = run(
            "examples/judge_pilot_replay.py",
            str(good),
            "--post",
            endpoint,
            "--token-file",
            str(token),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
    assert completed.returncode == 0, completed.stderr
    assert "posted: {'201': 15}" in completed.stdout
    assert len(received) == 15 and {r["auth"] for r in received} == {
        "Bearer stub-token"
    }

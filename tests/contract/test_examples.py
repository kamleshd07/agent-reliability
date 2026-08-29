"""Executable documentation contracts for the public examples."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

ROOT = Path(__file__).resolve().parents[2]


def _run(name: str) -> str:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "examples" / name)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stderr == ""
    return completed.stdout.replace("\r\n", "\n")


def test_readme_quickstart() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    marked = readme.split("<!-- readme-quickstart-start -->", 1)[1].split(
        "<!-- readme-quickstart-end -->", 1
    )[0]
    source = marked.split("```python", 1)[1].split("```", 1)[0]
    completed = subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stderr == ""
    assert completed.stdout.replace("\r\n", "\n") == (
        "Reliability: 75.00%\nSLO status: MET\n"
    )


def test_quickstart_basic_example() -> None:
    assert _run("basic_reliability.py") == (
        "Indicator: task_success\n"
        "Reliability: 75.00%\n"
        "SLO status: MET\n"
        "Budget remaining: 0.00%\n"
    )


def test_async_example() -> None:
    assert _run("async_agent.py") == "Async reliability: 2/3 (MET)\n"


def test_provenance_conflict_example() -> None:
    assert _run("provenance_conflict.py") == (
        "Reliability refused: incompatible measurement methodologies\n"
        "- evaluator_version_mismatch\n"
    )


def test_opentelemetry_example_when_extra_is_available() -> None:
    if importlib.util.find_spec("opentelemetry") is None:
        pytest.skip("the optional otel extra is not installed")
    assert _run("opentelemetry_example.py") == (
        "Agent run is active inside the host-owned OTel context.\n"
    )


def test_fail_open_policy_example() -> None:
    assert _run("policy_fail_open.py") == (
        "Measurement health: DEGRADED\n"
        "Application decision: CONTINUE\n"
        "This is application policy, not SDK policy.\n"
    )


def test_fail_closed_policy_example() -> None:
    assert _run("policy_fail_closed.py") == (
        "Measurement health: DEGRADED\n"
        "Application decision: WITHHOLD\n"
        "The application owns authorization; the SDK only reports health.\n"
    )


def test_bounded_degradation_policy_example() -> None:
    assert _run("policy_bounded_degradation.py") == (
        "HEALTHY -> FULL\n"
        "DEGRADED -> READ_ONLY\n"
        "UNAVAILABLE -> SENSITIVE_DISABLED\n"
        "These capability choices belong to the application, not the SDK.\n"
    )

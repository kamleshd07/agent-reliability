"""Optional framework gates run in fresh processes, not a polluted test interpreter."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize("mode", ["missing", "unsupported"])
def test_optional_dependency_gate_is_sanitized_before_framework_import(mode):
    probe = """
import importlib.metadata as metadata
import sys
from agent_reliability.sdk import AgentReliability
from agent_reliability.experimental.instrumentation import CaptureLimits, instrument
assert CaptureLimits().max_spans == 1000
assert not any(name.startswith("langchain_core") for name in sys.modules)
original = metadata.version
def fake(name):
    if name != "langchain-core":
        return original(name)
    if MODE == "missing":
        raise metadata.PackageNotFoundError("private-path-secret")
    return "private-version-secret"
metadata.version = fake
try:
    instrument(object(), sdk=AgentReliability(), agent_id="a", name="a", version="1")
except ImportError as error:
    assert "private" not in str(error)
else:
    raise AssertionError("dependency gate was bypassed")
assert not any(name.startswith("langchain_core") for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", f"MODE={mode!r}\n" + probe],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

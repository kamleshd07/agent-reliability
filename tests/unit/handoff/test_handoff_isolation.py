"""Import and layering rules: experimental, opt-in, not in the stable namespace."""

import subprocess
import sys


def test_import_is_inert_and_not_reexported_from_stable_namespace():
    probe = """
import sys, threading
before = threading.active_count()
import agent_reliability
assert not hasattr(agent_reliability, "HandoffEmitter")
prefix = "agent_reliability.experimental.handoff"
assert not any(n.startswith(prefix) for n in sys.modules)
import agent_reliability.experimental.handoff as h
assert threading.active_count() == before
banned_modules = ("httpx", "requests", "langchain_core", "agent_reliability.adapters")
for banned in banned_modules:
    assert banned not in sys.modules, banned
assert "HandoffEmitter" not in dir(agent_reliability)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr

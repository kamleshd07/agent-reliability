"""The public sample must not confuse suppressed SDK delivery failure with success."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agent_reliability.adapters.http_event_sink import DeliveryDisposition as D


def load_example():  # type: ignore[no-untyped-def]
    path = Path(__file__).resolve().parents[2] / "examples/platform_quickstart.py"
    spec = importlib.util.spec_from_file_location("platform_quickstart", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("counts", "queued", "reject", "exit_code"),
    [
        ({D.COMMITTED: 4}, 0, False, 0),
        ({D.COMMITTED: 3, D.DUPLICATE: 1}, 0, False, 0),
        ({}, 0, False, 1),
        ({D.COMMITTED: 3}, 0, False, 1),
        ({D.COMMITTED: 4}, 1, False, 1),
        ({D.COMMITTED: 4, D.PERMANENTLY_FAILED: 1}, 0, False, 1),
        ({D.COMMITTED: 4}, 0, True, 1),
    ],
)
def test_sample_requires_complete_acknowledgements_and_healthy_run(
    monkeypatch, capsys, counts, queued, reject, exit_code
):  # type: ignore[no-untyped-def]
    module = load_example()
    for key, value in {
        "GENTLITY_AGENT_KEY": "sample-agent",
        "GENTLITY_AGENT_NAME": "Synthetic sample",
        "GENTLITY_AGENT_VERSION": "1",
        "GENTLITY_ENVIRONMENT_KEY": "test",
        "GENTLITY_DEPLOYMENT_ID": str(uuid4()),
        "GENTLITY_EVIDENCE_URL": "https://example.invalid/api/v1/evidence/runs",
        "GENTLITY_MACHINE_TOKEN": "synthetic-secret-do-not-log",
    }.items():
        monkeypatch.setenv(key, value)

    class Sink:
        def emit(self, event):  # type: ignore[no-untyped-def]
            if reject:
                raise RuntimeError("synthetic-secret-do-not-log")

        def close(self, timeout):  # type: ignore[no-untyped-def]
            return SimpleNamespace(queue_depth=queued, counts_by_disposition=counts)

    monkeypatch.setattr(module, "HTTPEventSink", lambda **kwargs: Sink())
    assert module.main() == exit_code
    output = capsys.readouterr()
    assert ("Evidence acknowledged" in output.out) == (exit_code == 0)
    assert "synthetic-secret-do-not-log" not in output.out + output.err

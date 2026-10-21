"""Loads the recorded pre-P29 baseline hashes (re-synced manifest preferred)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_baseline() -> dict[str, str]:
    """``{path: sha256}`` of the pre-P29 files; skips when no manifest exists.

    ``docs/P29_WORKSPACE_BASELINE_RESYNC.sha256`` (after the 2026-10-16 re-sync
    of the P28-owned overlay) takes precedence over the original manifest.
    """
    for name in (
        "P29_WORKSPACE_BASELINE_RESYNC.sha256",
        "P29_WORKSPACE_BASELINE.sha256",
    ):
        path = ROOT / "docs" / name
        if path.exists():
            entries: dict[str, str] = {}
            for line in path.read_text(encoding="utf-8").splitlines():
                digest, _, file_name = line.partition("  ")
                entries[file_name] = digest
            return entries
    pytest.skip("workspace baseline manifest not present")


def load_runtime_revisions() -> dict[str, dict[str, str]]:
    """Recorded revisions of frozen runtime files (previousSha256 -> sha256)."""
    import json

    path = ROOT / "tests/fixtures/documentation/runtime-revisions.json"
    return json.loads(path.read_text()) if path.exists() else {}

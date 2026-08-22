"""Smoke tests proving the package imports, is versioned, and exposes
no more than its documented public surface. Reliability domain logic
does not exist yet (see docs/ROADMAP.md, milestone M1) — there is
nothing else to test at M0.
"""

from __future__ import annotations

import agent_reliability


def test_version_is_a_pre_alpha_string() -> None:
    assert agent_reliability.__version__ == "0.1.0.dev0"


def test_public_api_is_minimal() -> None:
    # M0 intentionally exports nothing but __version__. Growing this
    # list is a deliberate, reviewed decision, not an accident.
    assert agent_reliability.__all__ == ["__version__"]

"""Framework-neutral test/CI assertion helpers.

New additive namespace (post-1.1.1). Zero runtime dependency: no pytest, no
pytest plugin, importable and usable from plain scripts, ``unittest``, or
``pytest`` alike. See ``assert_slo_met`` for the single helper this
namespace currently provides.
"""

from __future__ import annotations

from agent_reliability.testing.assertions import assert_slo_met

__all__ = ["assert_slo_met"]

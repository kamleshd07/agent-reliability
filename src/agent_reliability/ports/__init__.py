"""Ports: typed interfaces the application layer depends on.

Examples of future ports: an exporter protocol, a clock protocol, an
evaluator protocol, a storage protocol. Ports are defined in terms of
domain types only — never in terms of a specific adapter (e.g. no
``ports`` module may import the OpenTelemetry SDK).

Not implemented yet. See docs/ARCHITECTURE.md.
"""

from __future__ import annotations

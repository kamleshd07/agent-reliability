"""Adapters: concrete implementations of ports (OTEL, console, framework
integrations).

This is the only layer permitted to depend on a specific vendor SDK,
transport, or agent framework. Adapters implement ports; they are never
imported by ``domain`` or ``application``.

Not implemented yet. See docs/ARCHITECTURE.md.
"""

from __future__ import annotations

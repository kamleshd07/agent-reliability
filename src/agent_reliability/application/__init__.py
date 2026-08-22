"""Application layer: orchestration and reliability use cases.

Coordinates domain objects and ports (e.g. "record an evaluation and
recompute the affected SLOs"). Contains no reliability mathematics
itself — that lives in ``agent_reliability.domain`` — and no adapter
implementations — those live in ``agent_reliability.adapters``.

Not implemented yet. See docs/ARCHITECTURE.md.
"""

from __future__ import annotations

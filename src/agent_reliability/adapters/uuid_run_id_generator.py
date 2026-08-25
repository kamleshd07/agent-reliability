"""The default ``RunIdGenerator`` implementation."""

from __future__ import annotations

import uuid

__all__ = ["UuidRunIdGenerator"]


class UuidRunIdGenerator:
    """Generates run ids via ``uuid.uuid4()`` — random, not sequential,
    globally-unique-compatible with no coordination required."""

    def generate(self) -> str:
        return str(uuid.uuid4())

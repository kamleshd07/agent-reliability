from __future__ import annotations


class SequentialRunIdGenerator:
    """Deterministic, test-only run id generator. NEVER use in production —
    sequential identifiers are explicitly rejected by docs/DOMAIN_MODEL.md
    ("Identifiers"); this exists purely so tests can assert on exact,
    predictable run ids."""

    def __init__(self, prefix: str = "run") -> None:
        self._prefix = prefix
        self._counter = 0

    def generate(self) -> str:
        self._counter += 1
        return f"{self._prefix}-{self._counter}"


class BrokenRunIdGenerator:
    """A run id generator that always raises — for failure-isolation tests."""

    def generate(self) -> str:
        raise RuntimeError("id generator is broken")

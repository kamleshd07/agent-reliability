"""The run id generator port.

M1 deliberately never generates its own ``run_id`` internally
(ADR-0002); this is the layer that does, behind a replaceable
interface — never a scattered direct ``uuid.uuid4()`` call throughout
SDK runtime code.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["RunIdGenerator"]


@runtime_checkable
class RunIdGenerator(Protocol):
    """A source of new run identifiers.

    Implementations must return globally-unique-compatible identifiers
    (never sequential integers — docs/DOMAIN_MODEL.md, "Identifiers").
    """

    def generate(self) -> str: ...

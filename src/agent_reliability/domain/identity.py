"""Agent identity.

Deliberately minimal: models only what M1 needs, per docs/DOMAIN_MODEL.md.
What makes two ``AgentIdentity`` values represent "the same agent" across
versions (for future regression detection, M7) is an open question this
milestone does not answer — ``AgentIdentity`` here has ordinary
structural (dataclass) equality only, nothing more.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["AgentIdentity"]


@dataclass(frozen=True)
class AgentIdentity:
    """Identifies what agent, at what version, produced a run.

    ``agent_id``, ``name``, and ``version`` are required: without a
    version an agent's runs cannot be attributed to a specific build for
    reliability comparison, and without a stable ``agent_id`` there is
    no key to compare versions of "the same" agent against later.

    ``environment`` is optional metadata (e.g. "production", "staging").
    It intentionally has no default — a missing value stays missing
    rather than silently defaulting to a guess like "production", which
    could mislabel data whose environment the caller genuinely did not
    specify. Whether/how ``environment`` should scope or filter an SLI's
    population of runs is not decided at M1.
    """

    agent_id: str
    name: str
    version: str
    environment: str | None = None

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("AgentIdentity.agent_id must not be empty")
        if not self.name:
            raise ValueError("AgentIdentity.name must not be empty")
        if not self.version:
            raise ValueError("AgentIdentity.version must not be empty")

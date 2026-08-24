from __future__ import annotations

import pytest

from agent_reliability.domain import AgentIdentity


def test_construction_with_all_fields() -> None:
    identity = AgentIdentity(
        agent_id="refund-agent",
        name="Refund Agent",
        version="1.4.2",
        environment="production",
    )
    assert identity.agent_id == "refund-agent"
    assert identity.environment == "production"


def test_environment_defaults_to_none_not_a_guessed_value() -> None:
    identity = AgentIdentity(agent_id="a", name="A", version="1")
    assert identity.environment is None


@pytest.mark.parametrize("field_name", ["agent_id", "name", "version"])
def test_required_fields_reject_empty_string(field_name: str) -> None:
    kwargs = {"agent_id": "a", "name": "A", "version": "1"}
    kwargs[field_name] = ""
    with pytest.raises(ValueError, match=field_name):
        AgentIdentity(**kwargs)  # type: ignore[arg-type]


def test_equality_is_structural_not_a_stable_agent_identity_concept() -> None:
    a = AgentIdentity(agent_id="x", name="Agent", version="1")
    b = AgentIdentity(agent_id="x", name="Agent", version="1")
    c = AgentIdentity(agent_id="x", name="Agent", version="2")
    assert a == b
    assert a != c  # different version -> not structurally equal, by design


def test_is_immutable() -> None:
    identity = AgentIdentity(agent_id="a", name="A", version="1")
    with pytest.raises(AttributeError):
        identity.name = "changed"  # type: ignore[misc]

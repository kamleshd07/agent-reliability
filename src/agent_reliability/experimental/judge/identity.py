"""Identity composition with the dual-grammar intersection (P29-CON-04, 04a).

The SDK identity grammar allows ``+`` and rejects ``:`` and ``/``; the P28
wire/exporter grammar rejects ``+`` and allows ``:`` and ``/``. Values built
here use only the intersection ``[A-Za-z0-9._-]`` (alphanumeric first and last
character), length 1-128, so that evidence is accepted by every layer.

The generic hazard for non-P29 evaluators whose version contains ``+`` is
documented, not fixed here: ``EvaluatorIdentity`` is unchanged.
"""

from __future__ import annotations

import re
from typing import Final

from agent_reliability.evaluation import EvaluatorIdentity
from agent_reliability.experimental.judge.rubric import Rubric
from agent_reliability.experimental.judge.values import Confidence, JudgePolicy

__all__ = [
    "TEMPLATE_ID",
    "compose_configuration_id",
    "compose_identity",
    "effective_min_confidence",
    "validate_identity_value",
    "validate_model_label",
]

#: Library-owned prompt template identity. Any change of template text changes it.
TEMPLATE_ID: Final = "jp1"

#: The P29 intersection grammar, 1-128 characters.
_INTERSECTION: Final = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")


def validate_identity_value(
    value: object, field_name: str, *, max_length: int = 128
) -> str:
    """Accept only values valid in *both* the SDK and the P28 wire/exporter grammars."""
    if (
        not isinstance(value, str)
        or len(value) > max_length
        or _INTERSECTION.fullmatch(value) is None
    ):
        raise ValueError(
            f"{field_name} must be 1-{max_length} characters of [A-Za-z0-9._-] "
            "starting and ending with a letter or digit"
        )
    return value


def validate_model_label(value: object) -> str:
    """Caller-declared, non-sensitive model/deployment label (1-64 characters)."""
    return validate_identity_value(value, "model_label", max_length=64)


def effective_min_confidence(rubric: Rubric, policy: JudgePolicy) -> Confidence:
    return (
        policy.min_confidence
        if policy.min_confidence is not None
        else (rubric.min_confidence)
    )


def compose_configuration_id(
    *,
    model_label: str,
    min_confidence: Confidence,
    repeats: int,
    require_citations: bool,
    template_id: str = TEMPLATE_ID,
) -> str:
    """``<model_label>.<template_id>.mc-<min_confidence>.rp<repeats>.ct<0|1>``."""
    label = validate_model_label(model_label)
    template = validate_identity_value(template_id, "template_id", max_length=16)
    if not isinstance(min_confidence, Confidence):
        raise TypeError("min_confidence must be a Confidence")
    if type(repeats) is not int or not 1 <= repeats <= 3:
        raise ValueError("repeats must be 1..3")
    if type(require_citations) is not bool:
        raise TypeError("require_citations must be a bool")
    composed = (
        f"{label}.{template}.mc-{min_confidence.value}."
        f"rp{repeats}.ct{1 if require_citations else 0}"
    )
    return validate_identity_value(composed, "configuration_id")


def compose_identity(
    rubric: Rubric, *, model_label: str, policy: JudgePolicy | None = None
) -> EvaluatorIdentity:
    """Build the identity: rubric id/version plus the composed configuration."""
    policy = policy if policy is not None else JudgePolicy()
    configuration_id = compose_configuration_id(
        model_label=model_label,
        min_confidence=effective_min_confidence(rubric, policy),
        repeats=policy.repeats,
        require_citations=rubric.require_citations,
    )
    return EvaluatorIdentity(
        name=rubric.rubric_id,
        version=validate_identity_value(rubric.rubric_version, "rubric_version"),
        configuration_id=configuration_id,
    )

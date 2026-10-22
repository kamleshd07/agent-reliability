"""Judge fingerprint: what a calibration applies to.

Derived from the evaluator that is actually bound, plus an explicit, always-shown
:class:`ModelDeclaration`. The judge never observes which model answered, so provider,
model id and model version are *declarations*; a silent provider-side change is
undetectable here (see docs/p29-calibration/ARCHITECTURE.md section 3).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from agent_reliability import __version__
from agent_reliability.experimental.calibration._json import canonical
from agent_reliability.experimental.judge import (
    LLMJudge,
    SyncLLMJudge,
    validate_identity_value,
)

__all__ = ["JudgeFingerprint", "ModelDeclaration"]

_BEHAVIOUR_FIELDS = (
    "rubric_id",
    "rubric_version",
    "rubric_fingerprint",
    "dimension",
    "template_id",
    "template_digest",
    "engine_revision",
    "limits_digest",
    "repeats",
    "min_confidence",
    "capture_reason",
    "require_citations",
    "configuration_id",
)


@dataclass(frozen=True, slots=True)
class ModelDeclaration:
    """Caller-declared provider and model; displayed in every decision."""

    provider: str
    model_id: str
    model_version: str | None = None

    def __post_init__(self) -> None:
        validate_identity_value(self.provider, "provider", max_length=64)
        validate_identity_value(self.model_id, "model_id", max_length=64)
        if self.model_version is not None:
            validate_identity_value(self.model_version, "model_version", max_length=64)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "model_version": self.model_version,
        }


@dataclass(frozen=True, slots=True)
class JudgeFingerprint:
    rubric_id: str
    rubric_version: str
    rubric_fingerprint: str
    dimension: str
    template_id: str
    template_digest: str
    engine_revision: str
    limits_digest: str
    repeats: int
    min_confidence: str
    capture_reason: bool
    require_citations: bool
    configuration_id: str
    implementation_version: str
    model: ModelDeclaration

    @classmethod
    def for_evaluator(
        cls, evaluator: LLMJudge | SyncLLMJudge, model: ModelDeclaration
    ) -> JudgeFingerprint:
        """Derive the fingerprint from the bound judge (never from typed-in fields)."""
        if not isinstance(evaluator, (LLMJudge, SyncLLMJudge)):
            raise TypeError("evaluator must be an LLMJudge or SyncLLMJudge")
        if not isinstance(model, ModelDeclaration):
            raise TypeError("model must be a ModelDeclaration")
        rubric = evaluator.rubric
        behaviour = evaluator.behaviour
        configuration_id = evaluator.identity.configuration_id
        if configuration_id is None:
            raise ValueError("a judge identity always has a configuration id")
        return cls(
            rubric_id=rubric.rubric_id,
            rubric_version=rubric.rubric_version,
            rubric_fingerprint=rubric.fingerprint(),
            dimension=rubric.dimension.value,
            template_id=behaviour.template_id,
            template_digest=behaviour.template_digest,
            engine_revision=behaviour.engine_revision,
            limits_digest=behaviour.limits_digest,
            repeats=behaviour.repeats,
            min_confidence=behaviour.min_confidence,
            capture_reason=behaviour.capture_reason,
            require_citations=behaviour.require_citations,
            configuration_id=configuration_id,
            implementation_version=__version__,
            model=model,
        )

    def behaviour_document(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in _BEHAVIOUR_FIELDS}

    @property
    def behaviour_digest(self) -> str:
        """Digest of everything that determines behaviour, excluding the SDK version
        (a patch release must not force re-calibration) and the model declaration
        (compared separately and always displayed)."""
        return hashlib.sha256(
            canonical(self.behaviour_document()).encode("utf-8")
        ).hexdigest()

    def equivalent_to(self, other: JudgeFingerprint) -> bool:
        return (
            self.behaviour_digest == other.behaviour_digest
            and self.model == other.model
        )

    def diff(self, other: JudgeFingerprint) -> tuple[str, ...]:
        """Names of the components that differ (``implementation_version`` is listed
        but never makes fingerprints inequivalent)."""
        names = [n for n in _BEHAVIOUR_FIELDS if getattr(self, n) != getattr(other, n)]
        for name in ("provider", "model_id", "model_version"):
            if getattr(self.model, name) != getattr(other.model, name):
                names.append(f"model.{name}")
        if self.implementation_version != other.implementation_version:
            names.append("implementation_version")
        return tuple(names)

    def as_dict(self) -> dict[str, Any]:
        document = self.behaviour_document()
        document["implementation_version"] = self.implementation_version
        document["model"] = self.model.as_dict()
        document["behaviour_digest"] = self.behaviour_digest
        return document

    @classmethod
    def from_dict(cls, document: dict[str, Any]) -> JudgeFingerprint:
        model = document["model"]
        fingerprint = cls(
            **{n: document[n] for n in _BEHAVIOUR_FIELDS},
            implementation_version=document["implementation_version"],
            model=ModelDeclaration(
                model["provider"], model["model_id"], model.get("model_version")
            ),
        )
        if document.get("behaviour_digest") != fingerprint.behaviour_digest:
            raise ValueError("fingerprint digest does not match its components")
        return fingerprint

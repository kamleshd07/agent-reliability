"""Read-only description of what determines a judge's behaviour (calibration support).

``JudgeBehaviour`` is content-free: identifiers, flags, numbers and digests only.
It lets a calibration or admission layer derive a fingerprint **from the evaluator
that is actually bound** instead of trusting a caller-typed description. It does not
and cannot observe which model a provider really used (the provider contract carries
no model metadata), so provider-side model changes remain undetectable here.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Final

from agent_reliability.experimental.judge._engine import REQUESTED_TEMPERATURE
from agent_reliability.experimental.judge.core import (
    JUDGE_OUTPUT_SCHEMA,
    MAX_REASON_CHARS,
    build_prompt,
)
from agent_reliability.experimental.judge.identity import (
    TEMPLATE_ID,
    effective_min_confidence,
)
from agent_reliability.experimental.judge.rubric import Rubric
from agent_reliability.experimental.judge.values import (
    ContentPart,
    ContentRole,
    JudgeLimits,
    JudgePolicy,
)

__all__ = ["JudgeBehaviour", "behaviour_of", "template_digest"]

_PROBE_NONCE: Final = "0123456789abcdef"


def _probe(dimension: str, role: str, unknown: str, citations: bool) -> dict[str, Any]:
    return {
        "schema": "gentlity.rubric/1",
        "rubric_id": "calibration-probe",
        "rubric_version": "1",
        "dimension": dimension,
        "inputs_required": ["answer", role],
        "criteria": [{"id": "c1", "text": "Probe criterion."}],
        "reason_codes": {
            "pass": ["probe_pass"],
            "fail": ["probe_fail"],
            "unknown": [
                unknown,
                "judge_abstained",
                "low_confidence",
                "judge_disagreement",
            ],
        },
        "require_citations": citations,
    }


_PROBES: Final[tuple[tuple[dict[str, Any], str], ...]] = (
    (
        _probe("answer-correctness", "reference", "reference_insufficient", False),
        "reference",
    ),
    (_probe("groundedness", "context", "context_insufficient", True), "context"),
)


def template_digest() -> str:
    """SHA-256 of the prompt template as the real builder renders it.

    Renders the builder for a fixed probe rubric (with and without the citation
    rule), a fixed nonce, fixed parts and the repair variant, and adds the
    behaviour-relevant constants (output schema id, reason bound, requested
    temperature, template id). A template edit that forgot to change
    ``TEMPLATE_ID`` therefore still changes this digest.
    """
    rendered: list[dict[str, str]] = []
    for document, role in _PROBES:
        rubric = Rubric.from_dict(document)
        parts = (
            ContentPart(ContentRole(role), f"probe {role}"),
            ContentPart(ContentRole.ANSWER, "probe answer"),
        )
        for repair in (None, "probe_error_class"):
            prompt = build_prompt(
                rubric, parts, nonce=_PROBE_NONCE, repair_error_class=repair
            )
            rendered.append({"system": prompt.system, "user": prompt.user})
    canonical = json.dumps(
        {
            "template_id": TEMPLATE_ID,
            "output_schema": JUDGE_OUTPUT_SCHEMA,
            "max_reason_chars": MAX_REASON_CHARS,
            "temperature": REQUESTED_TEMPERATURE,
            "rendered": rendered,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class JudgeBehaviour:
    """Immutable, content-free behaviour description of one bound judge."""

    limits: tuple[tuple[str, str], ...]
    limits_digest: str
    repeats: int
    min_confidence: str
    capture_reason: bool
    require_citations: bool
    template_id: str
    template_digest: str


def behaviour_of(
    rubric: Rubric, policy: JudgePolicy | None, limits: JudgeLimits | None
) -> JudgeBehaviour:
    policy = policy if policy is not None else JudgePolicy()
    limits = limits if limits is not None else JudgeLimits()
    pairs = tuple(
        (field.name, repr(getattr(limits, field.name)))
        for field in dataclasses.fields(limits)
    )
    canonical = json.dumps(pairs, separators=(",", ":"))
    return JudgeBehaviour(
        limits=pairs,
        limits_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        repeats=policy.repeats,
        min_confidence=effective_min_confidence(rubric, policy).value,
        capture_reason=policy.capture_reason,
        require_citations=rubric.require_citations,
        template_id=TEMPLATE_ID,
        template_digest=template_digest(),
    )

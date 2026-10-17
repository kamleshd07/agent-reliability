"""Optional ``StructuredOutputEvaluator`` (P29 S08): deterministic key/type/enum check.

Checks an *already parsed* JSON object (``dict``) against a small declarative
spec. It shares its type and member rules with the judge-output parser
(``_schema``), is standard library only and has no schema-language dependency.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from agent_reliability.domain import EvaluationOutcome
from agent_reliability.evaluation import EvaluationDecision, EvaluatorIdentity
from agent_reliability.experimental.judge._schema import (
    JSON_TYPE_NAMES,
    is_json_type,
)

__all__ = ["StructuredOutputEvaluator"]

REASON_VALID = "structured-output.valid"
REASON_INVALID = "structured-output.invalid"
REASON_NO_DATA = "structured-output.no-data"


class StructuredOutputEvaluator:
    """Deterministic evaluator over a parsed object.

    ``required`` maps each required key to either a JSON type name
    (``string``, ``integer``, ``number``, ``boolean``, ``array``, ``object``,
    ``null``) or a non-empty collection of allowed string values (an enum).
    ``None`` input yields UNKNOWN (no data); any other non-object or any
    violation yields FAIL; otherwise PASS. Extra members are allowed.
    """

    def __init__(
        self,
        identity: EvaluatorIdentity,
        *,
        required: Mapping[str, str | Collection[str]],
    ) -> None:
        if not isinstance(identity, EvaluatorIdentity):
            raise TypeError("identity must be an EvaluatorIdentity")
        if not isinstance(required, Mapping) or not required:
            raise ValueError("required must be a non-empty mapping")
        spec: dict[str, str | frozenset[str]] = {}
        for key, rule in required.items():
            if not isinstance(key, str) or not key:
                raise ValueError("required keys must be non-empty strings")
            if isinstance(rule, str):
                if rule not in JSON_TYPE_NAMES:
                    raise ValueError("unknown JSON type name in required")
                spec[key] = rule
            elif isinstance(rule, Collection) and not isinstance(
                rule, (bytes, bytearray)
            ):
                values = frozenset(rule)
                if not values or not all(isinstance(v, str) for v in values):
                    raise ValueError("an enum rule must be a non-empty set of strings")
                spec[key] = values
            else:
                raise ValueError(
                    "a rule must be a JSON type name or an enum collection"
                )
        self._identity = identity
        self._spec = spec

    @property
    def identity(self) -> EvaluatorIdentity:
        return self._identity

    @property
    def deterministic(self) -> bool:
        return True

    def evaluate(self, value: Any) -> EvaluationDecision:
        if value is None:
            return EvaluationDecision(EvaluationOutcome.UNKNOWN, REASON_NO_DATA)
        if not is_json_type(value, "object"):
            return EvaluationDecision(EvaluationOutcome.FAIL, REASON_INVALID)
        for key, rule in self._spec.items():
            if key not in value:
                return EvaluationDecision(EvaluationOutcome.FAIL, REASON_INVALID)
            item = value[key]
            if isinstance(rule, str):
                ok = is_json_type(item, rule)
            else:
                ok = isinstance(item, str) and item in rule
            if not ok:
                return EvaluationDecision(EvaluationOutcome.FAIL, REASON_INVALID)
        return EvaluationDecision(EvaluationOutcome.PASS, REASON_VALID)

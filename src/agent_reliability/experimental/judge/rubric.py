"""Rubric document ``gentlity.rubric/1`` (P29-CON-03).

A rubric is *data*: loaded, validated once, then immutable. Every violation
raises ``ValueError`` at load/construction time, never at evaluation time and
never as ``UNKNOWN``. Rubric text is operator-authored and is sent only to the
customer's provider; it never reaches the platform. Error messages name fields,
not values.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from agent_reliability.experimental.judge.values import (
    Confidence,
    ContentRole,
    JudgeDimension,
)

__all__ = ["RUBRIC_SCHEMA", "Criterion", "ReasonCodes", "Rubric"]

RUBRIC_SCHEMA: Final = "gentlity.rubric/1"

_RUBRIC_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_RUBRIC_VERSION = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,126}[A-Za-z0-9])?$")
_CRITERION_ID = re.compile(r"^[a-z0-9](?:[a-z0-9_-]{0,30}[a-z0-9])?$")
_CODE = re.compile(r"^[a-z0-9](?:[a-z0-9_]{0,62}[a-z0-9])?$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")

_TOP_KEYS: Final = frozenset(
    {
        "schema",
        "rubric_id",
        "rubric_version",
        "dimension",
        "inputs_required",
        "inputs_optional",
        "criteria",
        "reason_codes",
        "missing_input_codes",
        "require_citations",
        "min_confidence",
        "description",
    }
)
_REQUIRED_KEYS: Final = frozenset(
    {
        "schema",
        "rubric_id",
        "rubric_version",
        "dimension",
        "inputs_required",
        "criteria",
        "reason_codes",
    }
)

#: Dimension -> (role whose absence is the deterministic pre-check, default code).
DEFAULT_MISSING_INPUT: Final[dict[JudgeDimension, tuple[ContentRole, str]]] = {
    JudgeDimension.ANSWER_CORRECTNESS: (
        ContentRole.REFERENCE,
        "reference_insufficient",
    ),
    JudgeDimension.GROUNDEDNESS: (ContentRole.CONTEXT, "context_insufficient"),
    JudgeDimension.INSTRUCTION_ADHERENCE: (
        ContentRole.INSTRUCTIONS,
        "instructions_missing",
    ),
    JudgeDimension.SAFETY_POLICY: (ContentRole.POLICY, "policy_missing"),
    JudgeDimension.TASK_COMPLETION_EVIDENCE: (
        ContentRole.TASK_EVIDENCE,
        "evidence_insufficient",
    ),
}


def _has_disallowed_control(value: str, *, allow_newline: bool) -> bool:
    for ch in value:
        o = ord(ch)
        if (o < 32 or 127 <= o <= 159) and not (allow_newline and ch == "\n"):
            return True
    return False


def _check_text(value: object, field_name: str, low: int, high: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if not low <= len(value) <= high:
        raise ValueError(f"{field_name} must be {low}-{high} characters")
    if _has_disallowed_control(value, allow_newline=True):
        raise ValueError(f"{field_name} contains a control character")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(f"{field_name} is not valid Unicode text") from None
    return value


@dataclass(frozen=True, slots=True)
class Criterion:
    id: str
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or _CRITERION_ID.fullmatch(self.id) is None:
            raise ValueError("criterion id is invalid")
        _check_text(self.text, "criterion text", 1, 500)


@dataclass(frozen=True, slots=True)
class ReasonCodes:
    """Closed code lists per verdict (``pass`` is spelled ``pass_`` in Python)."""

    pass_: tuple[str, ...]
    fail: tuple[str, ...]
    unknown: tuple[str, ...]

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for name in ("pass_", "fail", "unknown"):
            codes = getattr(self, name)
            if not isinstance(codes, (tuple, list)):
                raise ValueError("reason_codes lists must be arrays")
            codes = tuple(codes)
            if not 1 <= len(codes) <= 8:
                raise ValueError("each reason_codes list must have 1-8 codes")
            for code in codes:
                if not isinstance(code, str) or _CODE.fullmatch(code) is None:
                    raise ValueError("reason code is invalid")
                if code in seen:
                    raise ValueError("reason codes must be unique across lists")
                seen.add(code)
            object.__setattr__(self, name, codes)

    def for_verdict(self, verdict: str) -> tuple[str, ...]:
        if verdict == "pass":
            return self.pass_
        if verdict == "fail":
            return self.fail
        if verdict == "unknown":
            return self.unknown
        raise ValueError("verdict must be pass, fail or unknown")


def _roles(values: object, field_name: str) -> tuple[ContentRole, ...]:
    if not isinstance(values, (tuple, list)):
        raise ValueError(f"{field_name} must be an array")
    roles: list[ContentRole] = []
    for value in values:
        try:
            role = value if isinstance(value, ContentRole) else ContentRole(value)
        except ValueError:
            raise ValueError(f"{field_name} contains an unknown role") from None
        if role in roles:
            raise ValueError(f"{field_name} contains a duplicate role")
        roles.append(role)
    return tuple(roles)


@dataclass(frozen=True, slots=True)
class Rubric:
    """Immutable, validated rubric (build with ``from_dict`` / ``from_json*``)."""

    rubric_id: str
    rubric_version: str
    dimension: JudgeDimension
    inputs_required: tuple[ContentRole, ...]
    criteria: tuple[Criterion, ...]
    reason_codes: ReasonCodes
    inputs_optional: tuple[ContentRole, ...] = ()
    #: Resolved ``(role, unknown code)`` for every required role except ANSWER.
    missing_input_codes: tuple[tuple[ContentRole, str], ...] = ()
    require_citations: bool = False
    min_confidence: Confidence = Confidence.MEDIUM
    description: str | None = field(default=None)

    def __post_init__(self) -> None:
        if not isinstance(self.rubric_id, str) or not _RUBRIC_ID.fullmatch(
            self.rubric_id
        ):
            raise ValueError("rubric_id is invalid")
        if not isinstance(self.rubric_version, str) or not _RUBRIC_VERSION.fullmatch(
            self.rubric_version
        ):
            raise ValueError("rubric_version is invalid")
        if not isinstance(self.dimension, JudgeDimension):
            raise ValueError("dimension is invalid")
        required = _roles(self.inputs_required, "inputs_required")
        optional = _roles(self.inputs_optional, "inputs_optional")
        if ContentRole.ANSWER not in required:
            raise ValueError("inputs_required must contain answer")
        if set(required) & set(optional):
            raise ValueError("inputs_optional must be disjoint from inputs_required")
        if not isinstance(self.criteria, (tuple, list)) or not isinstance(
            self.reason_codes, ReasonCodes
        ):
            raise ValueError("criteria and reason_codes are invalid")
        criteria = tuple(self.criteria)
        if not 1 <= len(criteria) <= 12:
            raise ValueError("criteria must have 1-12 items")
        if not all(isinstance(c, Criterion) for c in criteria):
            raise ValueError("criteria must contain only criteria")
        if len({c.id for c in criteria}) != len(criteria):
            raise ValueError("criterion ids must be unique")
        if sum(len(c.text) for c in criteria) > 6000:
            raise ValueError("total criteria text must be at most 6000 characters")
        if type(self.require_citations) is not bool:
            raise ValueError("require_citations must be a boolean")
        if self.require_citations and ContentRole.CONTEXT not in required:
            raise ValueError("require_citations requires context in inputs_required")
        if not isinstance(self.min_confidence, Confidence):
            raise ValueError("min_confidence is invalid")
        if self.description is not None:
            _check_text(self.description, "description", 0, 300)
        if "low_confidence" not in self.reason_codes.unknown:
            raise ValueError("reason_codes.unknown must include low_confidence")
        object.__setattr__(self, "inputs_required", required)
        object.__setattr__(self, "inputs_optional", optional)
        object.__setattr__(self, "criteria", criteria)
        object.__setattr__(self, "missing_input_codes", self._resolve_missing(required))

    def _resolve_missing(
        self, required: tuple[ContentRole, ...]
    ) -> tuple[tuple[ContentRole, str], ...]:
        raw: Any = self.missing_input_codes
        explicit: dict[ContentRole, str] = {}
        items = raw.items() if isinstance(raw, Mapping) else raw
        for entry in items:
            try:
                role_value, code = entry
                role = (
                    role_value
                    if isinstance(role_value, ContentRole)
                    else ContentRole(role_value)
                )
            except (TypeError, ValueError):
                raise ValueError("missing_input_codes is invalid") from None
            if role in explicit:
                raise ValueError("missing_input_codes has a duplicate role")
            explicit[role] = code
        needed = [r for r in required if r is not ContentRole.ANSWER]
        for role, code in explicit.items():
            if role not in needed:
                raise ValueError(
                    "missing_input_codes keys must be required non-answer roles"
                )
            if not isinstance(code, str) or code not in self.reason_codes.unknown:
                raise ValueError(
                    "missing_input_codes values must be unknown reason codes"
                )
        default_role, default_code = DEFAULT_MISSING_INPUT[self.dimension]
        resolved: list[tuple[ContentRole, str]] = []
        for role in needed:
            if role in explicit:
                code = explicit[role]
            elif role is default_role and default_code in self.reason_codes.unknown:
                code = default_code
            else:
                raise ValueError(
                    "a required role has no unknown code for a missing input"
                )
            resolved.append((role, code))
        return tuple(resolved)

    # -- accessors ---------------------------------------------------------

    def missing_code_for(self, role: ContentRole) -> str | None:
        for candidate, code in self.missing_input_codes:
            if candidate is role:
                return code
        return None

    @property
    def allowed_roles(self) -> frozenset[ContentRole]:
        return frozenset(self.inputs_required) | frozenset(self.inputs_optional)

    # -- document / fingerprint -------------------------------------------

    def as_document(self) -> dict[str, Any]:
        """Canonical document form of the loaded rubric (defaults materialized)."""
        doc: dict[str, Any] = {
            "schema": RUBRIC_SCHEMA,
            "rubric_id": self.rubric_id,
            "rubric_version": self.rubric_version,
            "dimension": self.dimension.value,
            "inputs_required": [r.value for r in self.inputs_required],
            "inputs_optional": [r.value for r in self.inputs_optional],
            "criteria": [{"id": c.id, "text": c.text} for c in self.criteria],
            "reason_codes": {
                "pass": list(self.reason_codes.pass_),
                "fail": list(self.reason_codes.fail),
                "unknown": list(self.reason_codes.unknown),
            },
            "missing_input_codes": {r.value: c for r, c in self.missing_input_codes},
            "require_citations": self.require_citations,
            "min_confidence": self.min_confidence.value,
        }
        if self.description is not None:
            doc["description"] = self.description
        return doc

    def fingerprint(self) -> str:
        """SHA-256 of canonical UTF-8 JSON (sorted keys, compact). Local only."""
        canonical = json.dumps(
            self.as_document(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # -- loaders -----------------------------------------------------------

    @classmethod
    def from_dict(
        cls, document: Mapping[str, Any], *, pinned_fingerprint: str | None = None
    ) -> Rubric:
        if not isinstance(document, Mapping):
            raise ValueError("rubric document must be an object")
        keys = set(document)
        if not all(isinstance(k, str) for k in keys):
            raise ValueError("rubric document keys must be strings")
        if keys - _TOP_KEYS:
            raise ValueError("rubric document has an unknown member")
        if _REQUIRED_KEYS - keys:
            raise ValueError("rubric document is missing a required member")
        if document["schema"] != RUBRIC_SCHEMA:
            raise ValueError("rubric schema must be gentlity.rubric/1")
        try:
            dimension = JudgeDimension(document["dimension"])
        except ValueError:
            raise ValueError("dimension is invalid") from None
        criteria_raw = document["criteria"]
        if not isinstance(criteria_raw, list):
            raise ValueError("criteria must be an array")
        criteria: list[Criterion] = []
        for item in criteria_raw:
            if not isinstance(item, Mapping) or set(item) != {"id", "text"}:
                raise ValueError("criteria items must be {id, text} objects")
            criteria.append(Criterion(item["id"], item["text"]))
        codes_raw = document["reason_codes"]
        if not isinstance(codes_raw, Mapping) or set(codes_raw) != {
            "pass",
            "fail",
            "unknown",
        }:
            raise ValueError("reason_codes must have exactly pass, fail and unknown")
        for lst in codes_raw.values():
            if not isinstance(lst, list):
                raise ValueError("reason_codes lists must be arrays")
        reason_codes = ReasonCodes(
            tuple(codes_raw["pass"]),
            tuple(codes_raw["fail"]),
            tuple(codes_raw["unknown"]),
        )
        missing_raw = document.get("missing_input_codes", {})
        if not isinstance(missing_raw, Mapping):
            raise ValueError("missing_input_codes must be an object")
        min_conf_raw = document.get("min_confidence", "medium")
        try:
            min_conf = Confidence(min_conf_raw)
        except ValueError:
            raise ValueError("min_confidence is invalid") from None
        for list_key in ("inputs_required", "inputs_optional"):
            if list_key in document and not isinstance(document[list_key], list):
                raise ValueError(f"{list_key} must be an array")
        rubric = cls(
            rubric_id=document["rubric_id"],
            rubric_version=document["rubric_version"],
            dimension=dimension,
            inputs_required=tuple(document["inputs_required"]),
            criteria=tuple(criteria),
            reason_codes=reason_codes,
            inputs_optional=tuple(document.get("inputs_optional", ())),
            missing_input_codes=tuple(missing_raw.items()),
            require_citations=document.get("require_citations", False),
            min_confidence=min_conf,
            description=document.get("description"),
        )
        if pinned_fingerprint is not None:
            if (
                not isinstance(pinned_fingerprint, str)
                or _FINGERPRINT.fullmatch(pinned_fingerprint) is None
            ):
                raise ValueError("pinned_fingerprint must be 64 lowercase hex digits")
            if rubric.fingerprint() != pinned_fingerprint:
                raise ValueError(
                    "rubric content does not match pinned_fingerprint for this "
                    "rubric_version"
                )
        return rubric

    @classmethod
    def from_json(cls, text: str, *, pinned_fingerprint: str | None = None) -> Rubric:
        if not isinstance(text, str):
            raise ValueError("rubric JSON must be a string")
        return cls.from_dict(_strict_loads(text), pinned_fingerprint=pinned_fingerprint)

    @classmethod
    def from_json_file(
        cls, path: str | Path, *, pinned_fingerprint: str | None = None
    ) -> Rubric:
        text = Path(path).read_text(encoding="utf-8")
        return cls.from_json(text, pinned_fingerprint=pinned_fingerprint)


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("rubric JSON has a duplicate member name")
        result[key] = value
    return result


def _reject_constant(_: str) -> Any:
    raise ValueError("rubric JSON contains a non-finite number")


def _strict_loads(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_constant,
        )
    except RecursionError:
        raise ValueError("rubric JSON is nested too deeply") from None

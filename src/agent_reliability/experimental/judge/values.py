"""Value types and validation for the experimental judge (P29 S01).

Everything here is stdlib-only, immutable and free of I/O. Types that may hold
evaluated content (:class:`ContentPart`, :class:`EvaluationRequest`) never
render, serialize, copy or pickle that content (P29-CON-02).
"""

from __future__ import annotations

import enum
import hashlib
import math
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final, NoReturn

from agent_reliability.evaluation import EvaluationDecision

__all__ = [
    "Confidence",
    "ContentPart",
    "ContentRole",
    "ContentTrust",
    "EvaluationRequest",
    "JudgeBudget",
    "JudgeDimension",
    "JudgeEvaluation",
    "JudgeLimits",
    "JudgePolicy",
    "JudgeStats",
    "SamplingPolicy",
]

MAX_PARTS: Final = 32

_SALT_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,62}[A-Za-z0-9])?$")


class JudgeDimension(enum.StrEnum):
    ANSWER_CORRECTNESS = "answer-correctness"
    GROUNDEDNESS = "groundedness"
    INSTRUCTION_ADHERENCE = "instruction-adherence"
    SAFETY_POLICY = "safety-policy"
    TASK_COMPLETION_EVIDENCE = "task-completion-evidence"


class ContentRole(enum.StrEnum):
    QUESTION = "question"
    ANSWER = "answer"
    REFERENCE = "reference"
    CONTEXT = "context"
    INSTRUCTIONS = "instructions"
    POLICY = "policy"
    TASK_EVIDENCE = "task_evidence"


class ContentTrust(enum.StrEnum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


class Confidence(enum.StrEnum):
    """Categorical, self-reported, uncalibrated confidence (``low < medium < high``)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return _CONFIDENCE_RANK[self.value]


_CONFIDENCE_RANK: Final = {"low": 0, "medium": 1, "high": 2}

#: Roles that are operator-authored and therefore trusted by default.
TRUSTED_BY_DEFAULT: Final = frozenset(
    {ContentRole.REFERENCE, ContentRole.INSTRUCTIONS, ContentRole.POLICY}
)
_SINGLE_ROLES: Final = frozenset(
    {
        ContentRole.QUESTION,
        ContentRole.REFERENCE,
        ContentRole.INSTRUCTIONS,
        ContentRole.POLICY,
    }
)


class _NoCopy:
    """Refuses copy and pickle so evaluated content cannot be duplicated (CON-02)."""

    __slots__ = ()

    def __reduce__(self) -> NoReturn:
        raise TypeError(f"{type(self).__name__} cannot be copied or pickled")

    def __reduce_ex__(self, protocol: object) -> NoReturn:
        raise TypeError(f"{type(self).__name__} cannot be copied or pickled")

    def __copy__(self) -> NoReturn:
        raise TypeError(f"{type(self).__name__} cannot be copied or pickled")

    def __deepcopy__(self, memo: object) -> NoReturn:
        raise TypeError(f"{type(self).__name__} cannot be copied or pickled")


@dataclass(frozen=True, slots=True, repr=False)
class ContentPart(_NoCopy):
    """One piece of evaluated content. ``text`` is never rendered or exported."""

    role: ContentRole
    text: str = field(repr=False)
    trust: ContentTrust | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.role, ContentRole):
            raise TypeError("role must be a ContentRole")
        if not isinstance(self.text, str):
            raise TypeError("text must be a str")
        if "\x00" in self.text:
            raise ValueError("text must not contain NUL")
        if self.trust is not None and not isinstance(self.trust, ContentTrust):
            raise TypeError("trust must be a ContentTrust or None")
        if self.trust is ContentTrust.TRUSTED and self.role not in TRUSTED_BY_DEFAULT:
            raise ValueError("trust cannot be promoted for this role")

    @property
    def effective_trust(self) -> ContentTrust:
        if self.trust is not None:
            return self.trust
        if self.role in TRUSTED_BY_DEFAULT:
            return ContentTrust.TRUSTED
        return ContentTrust.UNTRUSTED

    def __repr__(self) -> str:
        return f"ContentPart(role={self.role.value}, chars={len(self.text)})"


@dataclass(frozen=True, slots=True, repr=False)
class EvaluationRequest(_NoCopy):
    """Evaluated content for one dimension. Never serialized (P29-CON-02)."""

    dimension: JudgeDimension
    parts: tuple[ContentPart, ...] = field(repr=False)
    correlation_id: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, JudgeDimension):
            raise TypeError("dimension must be a JudgeDimension")
        if not isinstance(self.parts, (tuple, list)):
            raise TypeError("parts must be a tuple of ContentPart")
        parts = tuple(self.parts)
        if not parts:
            raise ValueError("parts must not be empty")
        if len(parts) > MAX_PARTS:
            raise ValueError(f"parts must not exceed {MAX_PARTS} items")
        counts: dict[ContentRole, int] = {}
        for part in parts:
            if not isinstance(part, ContentPart):
                raise TypeError("parts must contain only ContentPart")
            counts[part.role] = counts.get(part.role, 0) + 1
        if counts.get(ContentRole.ANSWER, 0) != 1:
            raise ValueError("exactly one ANSWER part is required")
        for role in _SINGLE_ROLES:
            if counts.get(role, 0) > 1:
                raise ValueError("at most one part is allowed for this role")
        if self.correlation_id is not None:
            if not isinstance(self.correlation_id, str):
                raise TypeError("correlation_id must be a str or None")
            if len(self.correlation_id) > 256 or "\x00" in self.correlation_id:
                raise ValueError("correlation_id must be at most 256 characters")
        object.__setattr__(self, "parts", parts)

    def __repr__(self) -> str:
        roles = ", ".join(f"{p.role.value}:{len(p.text)}" for p in self.parts)
        return f"EvaluationRequest(dimension={self.dimension.value}, parts=[{roles}])"


# --------------------------------------------------------------------------
# Strict numeric validation helpers (no bool-as-int, finite numbers only)
# --------------------------------------------------------------------------


def _int(value: object, name: str, low: int, high: int | None = None) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an int")
    if value < low or (high is not None and value > high):
        bound = f"{low}..{high}" if high is not None else f">= {low}"
        raise ValueError(f"{name} must be {bound}")
    return value


def _float(
    value: object,
    name: str,
    *,
    low: float,
    high: float | None = None,
    low_open: bool = False,
) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    below = number <= low if low_open else number < low
    if below or (high is not None and number > high):
        raise ValueError(f"{name} is out of range")
    return number


def _decimal(value: object, name: str, *, positive: bool) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{name} is out of range")
    return value


@dataclass(frozen=True, slots=True)
class JudgePolicy:
    """Decision-policy settings. ``min_confidence=None`` defers to the rubric."""

    min_confidence: Confidence | None = None
    repeats: int = 1
    capture_reason: bool = False

    def __post_init__(self) -> None:
        if self.min_confidence is not None and not isinstance(
            self.min_confidence, Confidence
        ):
            raise TypeError("min_confidence must be a Confidence or None")
        _int(self.repeats, "repeats", 1, 3)
        if type(self.capture_reason) is not bool:
            raise TypeError("capture_reason must be a bool")


@dataclass(frozen=True, slots=True)
class JudgeLimits:
    """Safe-not-fast defaults; none benchmarked (P29-CON-11)."""

    provider_timeout_seconds: float = 30.0
    evaluation_deadline_seconds: float = 60.0
    max_attempts: int = 2
    repair_attempts: int = 1
    max_input_chars: int = 32_000
    max_output_tokens: int = 256
    max_reply_chars: int = 4_096
    retry_backoff_cap_seconds: float = 2.0

    def __post_init__(self) -> None:
        timeout = _float(
            self.provider_timeout_seconds,
            "provider_timeout_seconds",
            low=0.0,
            high=600.0,
            low_open=True,
        )
        deadline = _float(
            self.evaluation_deadline_seconds,
            "evaluation_deadline_seconds",
            low=0.0,
            low_open=True,
        )
        if deadline < timeout:
            raise ValueError(
                "evaluation_deadline_seconds must be >= provider_timeout_seconds"
            )
        _int(self.max_attempts, "max_attempts", 1, 5)
        _int(self.repair_attempts, "repair_attempts", 0, 2)
        _int(self.max_input_chars, "max_input_chars", 1, 1_000_000)
        _int(self.max_output_tokens, "max_output_tokens", 16, 4096)
        _int(self.max_reply_chars, "max_reply_chars", 256, 65_536)
        cap = _float(
            self.retry_backoff_cap_seconds, "retry_backoff_cap_seconds", low=0.0
        )
        object.__setattr__(self, "provider_timeout_seconds", timeout)
        object.__setattr__(self, "evaluation_deadline_seconds", deadline)
        object.__setattr__(self, "retry_backoff_cap_seconds", cap)


@dataclass(frozen=True, slots=True)
class JudgeBudget:
    """Sliding-window token and/or monetary budget (provider-reported usage only)."""

    window_seconds: int = 3_600
    max_tokens_per_window: int | None = None
    max_cost_per_window: Decimal | None = None
    input_price_per_1k_tokens: Decimal | None = None
    output_price_per_1k_tokens: Decimal | None = None

    def __post_init__(self) -> None:
        _int(self.window_seconds, "window_seconds", 1)
        if self.max_tokens_per_window is not None:
            _int(self.max_tokens_per_window, "max_tokens_per_window", 1)
        if self.max_cost_per_window is not None:
            _decimal(self.max_cost_per_window, "max_cost_per_window", positive=True)
            if (
                self.input_price_per_1k_tokens is None
                or self.output_price_per_1k_tokens is None
            ):
                raise ValueError("max_cost_per_window requires input and output prices")
        if self.input_price_per_1k_tokens is not None:
            _decimal(
                self.input_price_per_1k_tokens,
                "input_price_per_1k_tokens",
                positive=False,
            )
        if self.output_price_per_1k_tokens is not None:
            _decimal(
                self.output_price_per_1k_tokens,
                "output_price_per_1k_tokens",
                positive=False,
            )

    @property
    def enforces_anything(self) -> bool:
        return self.max_tokens_per_window is not None or (
            self.max_cost_per_window is not None
        )


@dataclass(frozen=True, slots=True)
class SamplingPolicy:
    """Deterministic run-id keyed sampling; cannot see content (P29-CON-13).

    ``salt`` is deliberately stricter than the contract's charset: empty, or
    1-64 characters of ``[A-Za-z0-9._-]`` starting and ending with a letter or
    digit (the plan's P29-S01-AC02 lists the salt among values that satisfy the
    identity grammars). Relaxing it later cannot break existing salts.
    """

    rate: float = 1.0
    salt: str = ""

    def __post_init__(self) -> None:
        rate = _float(self.rate, "rate", low=0.0, high=1.0)
        if not isinstance(self.salt, str):
            raise TypeError("salt must be a str")
        if self.salt and _SALT_PATTERN.fullmatch(self.salt) is None:
            raise ValueError(
                "salt must be empty or 1-64 characters of [A-Za-z0-9._-] "
                "starting and ending with a letter or digit"
            )
        object.__setattr__(self, "rate", rate)

    def decide(self, run_id: str) -> bool:
        """Pure function of ``(salt, run_id)``: SHA-256 as uint64 over 2**64 < rate."""
        if not isinstance(run_id, str):
            raise TypeError("run_id must be a str")
        digest = hashlib.sha256(
            self.salt.encode("utf-8") + b"\x00" + run_id.encode("utf-8")
        ).digest()
        value = int.from_bytes(digest[:8], "big")
        return value < self.rate * 2**64


@dataclass(frozen=True, slots=True)
class JudgeStats:
    """Content-free counters of one evaluation (local only; never exported)."""

    attempts: int
    repairs: int
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int


@dataclass(frozen=True, slots=True)
class JudgeEvaluation:
    """Successful detailed result of ``evaluate_detailed`` (local only)."""

    decision: EvaluationDecision
    stats: JudgeStats
    reason_text: str | None = field(default=None, repr=False)
    #: Lowest self-reported confidence across the repeats (local only).
    confidence: Confidence | None = None

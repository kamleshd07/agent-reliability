"""Judge failure taxonomy (P29-CON-09).

Ten fixed failure classes. Every message is a constant string: no exception
here ever carries prompt text, provider text, model output or evaluated
content. The class name is the wire ``exception_type`` literal.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from agent_reliability.experimental.judge.values import JudgeStats

__all__ = [
    "FAILURE_CLASS_NAMES",
    "JudgeBudgetExceededError",
    "JudgeError",
    "JudgeInputLimitError",
    "JudgeInvalidOutputError",
    "JudgeOutputTooLargeError",
    "JudgeOverloadedError",
    "JudgeProviderError",
    "JudgeProviderRateLimitedError",
    "JudgeProviderRefusedError",
    "JudgeProviderUnavailableError",
    "JudgeTimeoutError",
]


class JudgeError(Exception):
    """Base class. The message is a class-level constant, never content."""

    _MESSAGE: str = "judge evaluation failed"

    def __init__(self) -> None:
        super().__init__(self._MESSAGE)
        #: Content-free counters of the failed evaluation (set by the judge).
        self.stats: JudgeStats | None = None

    def __reduce__(self) -> tuple[Any, ...]:
        return (type(self), ())


class JudgeTimeoutError(JudgeError):
    """Provider attempt or the whole evaluation exceeded its deadline."""

    _MESSAGE = "judge provider call timed out"


class JudgeProviderUnavailableError(JudgeError):
    """Provider unreachable or failing (connect error, 5xx)."""

    _MESSAGE = "judge provider unavailable"


class JudgeProviderRateLimitedError(JudgeError):
    """Provider rate limited the call; may carry a retry hint in seconds."""

    _MESSAGE = "judge provider rate limited"

    def __init__(self, retry_after_seconds: float | None = None) -> None:
        super().__init__()
        hint: float | None = None
        if (
            isinstance(retry_after_seconds, (int, float))
            and not isinstance(retry_after_seconds, bool)
            and math.isfinite(retry_after_seconds)
            and retry_after_seconds >= 0
        ):
            hint = float(retry_after_seconds)
        self.retry_after_seconds: float | None = hint

    def __reduce__(self) -> tuple[Any, ...]:
        return (type(self), (self.retry_after_seconds,))


class JudgeProviderRefusedError(JudgeError):
    """Provider refused or content-filtered the request."""

    _MESSAGE = "judge provider refused the request"


class JudgeProviderError(JudgeError):
    """Any other provider failure, including unclassified adapter errors."""

    _MESSAGE = "judge provider error"


class JudgeInvalidOutputError(JudgeError):
    """Model output violated the judge-output contract after allowed re-asks.

    ``error_class`` is a closed, content-free token (for example
    ``"invalid_json"``) naming only the kind of defect.
    """

    _MESSAGE = "judge output invalid"

    def __init__(self, error_class: str = "invalid_json") -> None:
        super().__init__()
        self.error_class: str = (
            error_class if error_class in _ERROR_CLASSES else ("invalid_json")
        )

    def __reduce__(self) -> tuple[Any, ...]:
        return (type(self), (self.error_class,))


class JudgeOutputTooLargeError(JudgeError):
    """Provider reply exceeded ``max_reply_chars``."""

    _MESSAGE = "judge reply too large"


class JudgeInputLimitError(JudgeError):
    """Evaluated input exceeded ``max_input_chars``; it is never truncated."""

    _MESSAGE = "judge input exceeds limit"


class JudgeBudgetExceededError(JudgeError):
    """Token or monetary budget exhausted before a provider call."""

    _MESSAGE = "judge budget exhausted"


class JudgeOverloadedError(JudgeError):
    """Evaluation shed because the pending queue was full."""

    _MESSAGE = "judge overloaded"


#: The closed set of ``error_class`` tokens of :class:`JudgeInvalidOutputError`.
_ERROR_CLASSES: Final = frozenset(
    {
        "invalid_json",
        "invalid_schema",
        "invalid_code",
        "invalid_citations",
        "invalid_reason",
        "truncated",
    }
)

#: Wire ``exception_type`` literals emitted by P29, in contract order.
FAILURE_CLASS_NAMES: Final[tuple[str, ...]] = (
    "JudgeTimeoutError",
    "JudgeProviderUnavailableError",
    "JudgeProviderRateLimitedError",
    "JudgeProviderRefusedError",
    "JudgeProviderError",
    "JudgeInvalidOutputError",
    "JudgeOutputTooLargeError",
    "JudgeInputLimitError",
    "JudgeBudgetExceededError",
    "JudgeOverloadedError",
)

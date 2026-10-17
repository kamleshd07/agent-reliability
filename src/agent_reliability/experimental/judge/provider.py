"""Provider protocol and adapters (P29-CON-05).

The SDK never reads credentials, environment variables or network state. A
provider is any customer object (or callable adapted by
:class:`CallableProvider`) that turns a :class:`ProviderCall` into a
:class:`ProviderReply`, and reports failure by raising.
"""

from __future__ import annotations

import enum
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

__all__ = [
    "CallableProvider",
    "CallableSyncProvider",
    "JudgeProvider",
    "ProviderCall",
    "ProviderFinish",
    "ProviderReply",
    "SyncJudgeProvider",
]


class ProviderFinish(enum.StrEnum):
    STOP = "stop"
    LENGTH = "length"
    FILTERED = "filtered"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ProviderCall:
    """One request to the customer's provider. Prompt text is never rendered."""

    system: str = field(repr=False)
    user: str = field(repr=False)
    max_output_tokens: int
    temperature: float | None
    json_output: bool
    deadline_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.system, str) or not isinstance(self.user, str):
            raise TypeError("system and user must be str")
        if type(self.max_output_tokens) is not int or self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be a positive int")
        if self.temperature is not None and (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not math.isfinite(self.temperature)
        ):
            raise ValueError("temperature must be a finite number or None")
        if type(self.json_output) is not bool:
            raise TypeError("json_output must be a bool")
        if (
            isinstance(self.deadline_seconds, bool)
            or not isinstance(self.deadline_seconds, (int, float))
            or not math.isfinite(self.deadline_seconds)
            or self.deadline_seconds <= 0
        ):
            raise ValueError("deadline_seconds must be a positive finite number")


@dataclass(frozen=True, slots=True)
class ProviderReply:
    """A provider reply. ``text`` is never rendered."""

    text: str = field(repr=False)
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish: ProviderFinish = ProviderFinish.STOP

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("text must be a str")
        for name in ("input_tokens", "output_tokens"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a non-negative int or None")
        if not isinstance(self.finish, ProviderFinish):
            raise TypeError("finish must be a ProviderFinish")


@runtime_checkable
class JudgeProvider(Protocol):
    """Async provider. ``reports_tokens`` is optional (absent means ``False``)."""

    @property
    def provider_label(self) -> str: ...

    async def complete(self, call: ProviderCall) -> ProviderReply: ...


@runtime_checkable
class SyncJudgeProvider(Protocol):
    @property
    def provider_label(self) -> str: ...

    def complete(self, call: ProviderCall) -> ProviderReply: ...


def _label(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 64
        or not value.isprintable()
    ):
        raise ValueError("provider_label must be 1-64 printable characters")
    return value


class CallableProvider:
    """Adapts an async callable ``fn(call) -> ProviderReply`` (Option A)."""

    def __init__(
        self,
        fn: Callable[[ProviderCall], Awaitable[ProviderReply]],
        *,
        provider_label: str,
        reports_tokens: bool = False,
    ) -> None:
        if not callable(fn):
            raise TypeError("fn must be callable")
        if type(reports_tokens) is not bool:
            raise TypeError("reports_tokens must be a bool")
        self._fn = fn
        self._label = _label(provider_label)
        self.reports_tokens = reports_tokens

    @property
    def provider_label(self) -> str:
        return self._label

    async def complete(self, call: ProviderCall) -> ProviderReply:
        return await self._fn(call)

    def __repr__(self) -> str:
        return f"CallableProvider(provider_label={self._label!r})"


class CallableSyncProvider:
    """Adapts a blocking callable ``fn(call) -> ProviderReply``."""

    def __init__(
        self,
        fn: Callable[[ProviderCall], ProviderReply],
        *,
        provider_label: str,
        reports_tokens: bool = False,
    ) -> None:
        if not callable(fn):
            raise TypeError("fn must be callable")
        if type(reports_tokens) is not bool:
            raise TypeError("reports_tokens must be a bool")
        self._fn = fn
        self._label = _label(provider_label)
        self.reports_tokens = reports_tokens

    @property
    def provider_label(self) -> str:
        return self._label

    def complete(self, call: ProviderCall) -> ProviderReply:
        return self._fn(call)

    def __repr__(self) -> str:
        return f"CallableSyncProvider(provider_label={self._label!r})"

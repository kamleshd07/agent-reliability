"""Optional pinned LangChain hooks. No global tracing configuration or patching."""

from __future__ import annotations

import asyncio
import contextlib
import re
from collections.abc import Callable
from functools import wraps
from importlib.metadata import PackageNotFoundError, version
from typing import Any, ParamSpec
from uuid import UUID, uuid4

try:
    _version = version("langchain-core")
except PackageNotFoundError:
    raise ImportError("install agent-reliability[langchain] for this adapter") from None
if re.match(r"1\.\d+(\.|$)", _version) is None:
    raise ImportError(
        "this experimental adapter requires langchain-core>=1.0,<2 "
        "(see docs/AUTOMATIC_INSTRUMENTATION.md for the tested range)"
    )

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.callbacks.base import BaseCallbackManager
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.runnables import Runnable
from langchain_core.runnables.config import RunnableConfig, ensure_config
from langchain_core.runnables.retry import RunnableRetry

from agent_reliability.experimental.instrumentation.collector import (
    MAX_RETRY_ATTEMPT,
    Collector,
)
from agent_reliability.experimental.instrumentation.model import (
    ExecutionState,
    SpanKind,
    TokenUsage,
)

P = ParamSpec("P")

# The one framework marker the owner approved reading (P20c M3, 2026-11-08). The
# framework sets it only on attempts after the first, so 1 is never a valid index.
_RETRY_TAG = re.compile(r"retry:attempt:([1-9][0-9]{0,2})", re.ASCII)
_MAX_TAGS_SCANNED = 64
_MAX_TAG_LENGTH = 32


def is_retry_wrapper(runnable: object) -> bool:
    """True only for an exact RunnableRetry: the sole verifiable wrapper context.

    Callbacks carry no wrapper identity (``serialized`` is None and ``run_type`` is
    unset for it in every tested langchain-core 1.x), so nothing else is trusted.
    """
    return type(runnable) is RunnableRetry


def retry_attempt(tags: Any) -> int | None:
    """Parse only the approved marker from a verified wrapper's child.

    Each tag is tested against the exact pattern and discarded; nothing but a bounded
    integer is returned. None = no marker; 0 = unusable marker (ambiguous, repeated,
    out of range or not exactly the framework's form). Tags are untrusted evidence.
    """
    if tags is None:
        return None
    if type(tags) is not list:
        return 0
    found: int | None = None
    for index, tag in enumerate(tags):
        if index >= _MAX_TAGS_SCANNED:
            return 0
        if type(tag) is not str or len(tag) > _MAX_TAG_LENGTH:
            continue
        match = _RETRY_TAG.fullmatch(tag)
        if match is None:
            continue
        number = int(match.group(1))
        if found is not None or not 2 <= number <= MAX_RETRY_ATTEMPT:
            return 0
        found = number
    return found


def _guard(method: Callable[P, None]) -> Callable[P, None]:
    @wraps(method)
    def contained(*args: P.args, **kwargs: P.kwargs) -> None:
        try:
            method(*args, **kwargs)
        except Exception:
            # Never let LangChain's error handler log repr(exception/payload).
            with contextlib.suppress(Exception):
                handler: Any = args[0]
                handler.collector.error()

    return contained


def _uuid(value: object) -> UUID:
    if type(value) is UUID:
        return value
    if type(value) is str and len(value) == 36:
        return UUID(value)
    raise ValueError("invalid callback identity")


def outcome_of(error: BaseException) -> str:
    """Closed technical outcome from the exception *type* only; never name or text."""
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, PermissionError):
        return "permission_denied"
    if isinstance(error, ConnectionError):
        return "unavailable"
    return "execution_error"


def _usage(response: object) -> TokenUsage:
    if (
        not isinstance(response, LLMResult)
        or len(response.generations) != 1
        or len(response.generations[0]) != 1
    ):
        return TokenUsage()
    generation = response.generations[0][0]
    raw: Any = None
    if isinstance(generation, ChatGeneration) and isinstance(
        generation.message, AIMessage
    ):
        raw = generation.message.usage_metadata
    if raw is not None:
        if type(raw) is not dict:
            return TokenUsage()
        total, inputs, outputs = (
            raw.get("total_tokens"),
            raw.get("input_tokens"),
            raw.get("output_tokens"),
        )
    elif type(response.llm_output) is dict:
        raw = response.llm_output.get("token_usage")
        if type(raw) is not dict:
            return TokenUsage()
        total, inputs, outputs = (
            raw.get("total_tokens"),
            raw.get("prompt_tokens"),
            raw.get("completion_tokens"),
        )
    else:
        return TokenUsage()
    if total is None:
        return TokenUsage()
    try:
        return TokenUsage("reported", total, inputs, outputs)
    except ValueError:
        return TokenUsage()


class _Handler(BaseCallbackHandler):
    run_inline = True
    raise_error = False

    def __init__(
        self,
        collector: Collector,
        approved_tools: frozenset[str],
        retry_root: UUID | None = None,
    ) -> None:
        self.collector = collector
        self._tools = approved_tools
        self._retry_root = retry_root

    def _start(
        self, kind: SpanKind, values: dict[str, Any], component: str | None = None
    ) -> None:
        parent = values.get("parent_run_id")
        parent_id = _uuid(parent) if parent is not None else None
        attempt = None
        # Tags are read only for direct children of the verified retry wrapper.
        if self._retry_root is not None and parent_id == self._retry_root:
            attempt = retry_attempt(values.get("tags"))
        self.collector.start(
            _uuid(values.get("run_id")), parent_id, kind, component, attempt
        )

    def _end(
        self,
        values: dict[str, Any],
        kind: SpanKind,
        state: ExecutionState = "completed",
        usage: TokenUsage | None = None,
        outcome: str | None = None,
    ) -> None:
        self.collector.end(
            _uuid(values.get("run_id")),
            state,
            usage,
            expected_kind=kind,
            outcome=outcome,
        )

    @_guard
    def on_chain_start(self, serialized: Any, inputs: Any, **kwargs: Any) -> None:
        self._start("step", kwargs)

    @_guard
    def on_tool_start(self, serialized: Any, input_str: Any, **kwargs: Any) -> None:
        name = serialized.get("name") if type(serialized) is dict else None
        approved = (
            name
            if type(name) is str and len(name) <= 128 and name in self._tools
            else None
        )
        self._start("tool", kwargs, approved)

    @_guard
    def on_llm_start(self, serialized: Any, prompts: Any, **kwargs: Any) -> None:
        self._start("model", kwargs)

    @_guard
    def on_chat_model_start(
        self, serialized: Any, messages: Any, **kwargs: Any
    ) -> None:
        # An explicit method avoids the framework's prompt-string fallback.
        self._start("model", kwargs)

    @_guard
    def on_chain_end(self, outputs: Any, **kwargs: Any) -> None:
        self._end(kwargs, "step")

    @_guard
    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        self._end(kwargs, "tool")

    @_guard
    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        self._end(kwargs, "model", usage=_usage(response))

    @_guard
    def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        self._end(
            kwargs,
            "step",
            "cancelled" if isinstance(error, asyncio.CancelledError) else "failed",
        )

    @_guard
    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        self._end(
            kwargs,
            "tool",
            "cancelled" if isinstance(error, asyncio.CancelledError) else "failed",
            outcome=outcome_of(error),
        )

    @_guard
    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        self._end(
            kwargs,
            "model",
            "cancelled" if isinstance(error, asyncio.CancelledError) else "failed",
        )

    @_guard
    def on_retry(self, retry_state: Any, **kwargs: Any) -> None:
        self.collector.retry()


def validate_runnable(runnable: object) -> None:
    if not isinstance(runnable, Runnable):
        raise TypeError("instrumentation requires a LangChain Runnable")


def root_identity(config: Any) -> UUID:
    # Read only the identity; user metadata is passed back to the framework untouched.
    raw = config.get("run_id") if config is not None else None
    return _uuid(raw) if raw is not None else uuid4()


def callback_config(
    config: Any,
    collector: Collector,
    tools: frozenset[str],
    root: UUID,
    retry_wrapper: bool = False,
) -> RunnableConfig:
    copied = ensure_config(config)
    callbacks = copied.get("callbacks")
    handler = _Handler(collector, tools, root if retry_wrapper else None)
    if isinstance(callbacks, BaseCallbackManager):
        manager = callbacks.copy()
        for existing in tuple(manager.handlers):
            if isinstance(existing, _Handler):
                manager.remove_handler(existing)
        manager.add_handler(handler, inherit=True)
        copied["callbacks"] = manager
    elif callbacks is None or isinstance(callbacks, list):
        copied["callbacks"] = [
            c for c in callbacks or [] if not isinstance(c, _Handler)
        ] + [handler]
    else:
        raise TypeError("invalid callback configuration")
    if "run_id" not in copied:
        copied["run_id"] = root
    return copied

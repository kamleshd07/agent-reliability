"""Optional pinned LangChain hooks. No global tracing configuration or patching."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from functools import wraps
from importlib.metadata import PackageNotFoundError, version
from typing import Any, ParamSpec
from uuid import UUID, uuid4

try:
    _version = version("langchain-core")
except PackageNotFoundError:
    raise ImportError("install agent-reliability[langchain] for this adapter") from None
if _version != "1.6.13":
    raise ImportError("this experimental adapter requires langchain-core==1.6.13")

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.callbacks.base import BaseCallbackManager
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.runnables import Runnable
from langchain_core.runnables.config import RunnableConfig, ensure_config

from agent_reliability.experimental.instrumentation.collector import Collector
from agent_reliability.experimental.instrumentation.model import (
    ExecutionState,
    SpanKind,
    TokenUsage,
)

P = ParamSpec("P")


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

    def __init__(self, collector: Collector, approved_tools: frozenset[str]) -> None:
        self.collector = collector
        self._tools = approved_tools

    def _start(
        self, kind: SpanKind, values: dict[str, Any], component: str | None = None
    ) -> None:
        parent = values.get("parent_run_id")
        self.collector.start(
            _uuid(values.get("run_id")),
            _uuid(parent) if parent is not None else None,
            kind,
            component,
        )

    def _end(
        self,
        values: dict[str, Any],
        kind: SpanKind,
        state: ExecutionState = "completed",
        usage: TokenUsage | None = None,
    ) -> None:
        self.collector.end(
            _uuid(values.get("run_id")), state, usage, expected_kind=kind
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
    config: Any, collector: Collector, tools: frozenset[str], root: UUID
) -> RunnableConfig:
    copied = ensure_config(config)
    callbacks = copied.get("callbacks")
    handler = _Handler(collector, tools)
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

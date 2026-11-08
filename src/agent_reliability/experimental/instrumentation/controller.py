"""Explicit opt-in wrapper; automatic execution never asserts semantic correctness."""

from __future__ import annotations

import asyncio
import contextlib
import math
import random
import threading
from collections import deque
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from typing import Any, TypedDict

from agent_reliability.domain.measurement_health import MeasurementHealthReason
from agent_reliability.sdk import AgentReliability
from agent_reliability.sdk.client import RunSession
from agent_reliability.sdk.context import RunHandle

from .collector import Collector
from .export import TraceExporter
from .model import (
    ACTION_CLASSES,
    MAX_COUNT,
    TOOL_CLASSES,
    CaptureLimits,
    ExecutionState,
    ExecutionTrace,
    alias,
)


class _Identity(TypedDict):
    agent_id: str
    name: str
    version: str
    environment: str | None


def _semantics(
    approved: frozenset[str],
    classes: Mapping[str, str] | None,
    actions: Mapping[str, str] | None,
) -> dict[str, tuple[str | None, str | None]]:
    """Declared (never inferred) tool/action classes for approved tool names."""
    result: dict[str, tuple[str | None, str | None]] = {}
    for mapping, vocabulary in ((classes, TOOL_CLASSES), (actions, ACTION_CLASSES)):
        if mapping is None:
            continue
        if not isinstance(mapping, Mapping):
            raise TypeError("tool classes must be a mapping of approved tool names")
        for name, value in mapping.items():
            if name not in approved or value not in vocabulary:
                raise ValueError(
                    "tool classes must name approved tools using closed values"
                )
    for name in approved:
        pair = (
            (classes or {}).get(name),
            (actions or {}).get(name),
        )
        if pair != (None, None):
            result[name] = pair
    return result


class _ExecutionFailure(Exception):
    """Fixed export-safe classification; never contains the application exception."""


@dataclass(frozen=True, slots=True)
class InstrumentationStatus:
    enabled: bool
    closed: bool
    active_runs: int
    admitted: int
    completed: int
    unsampled: int
    admission_dropped: int
    failures: int
    export_failures: int = 0


class InstrumentedRunnable:
    """Experimental invoke/ainvoke wrapper, not a replacement Runnable hierarchy.

    No stream/batch forwarding: bypass the wrapper for unsupported operations.
    Disabling affects future calls; it does not cancel in-flight application work.
    """

    def __init__(
        self,
        runnable: Any,
        *,
        sdk: AgentReliability,
        agent_id: str,
        name: str,
        version: str,
        environment: str | None,
        tool_names: Collection[str],
        provider_id: str | None,
        model_id: str | None,
        limits: CaptureLimits,
        sample_rate: float,
        tool_classes: Mapping[str, str] | None = None,
        tool_actions: Mapping[str, str] | None = None,
        exporter: TraceExporter | None = None,
    ) -> None:
        if not isinstance(sdk, AgentReliability):
            raise TypeError("sdk must be an AgentReliability instance")
        if not isinstance(limits, CaptureLimits):
            raise TypeError("limits must be CaptureLimits")
        if (
            type(sample_rate) not in (int, float)
            or not math.isfinite(sample_rate)
            or not 0 <= sample_rate <= 1
        ):
            raise ValueError("sample_rate must be between zero and one")
        if (
            isinstance(tool_names, (str, bytes))
            or not isinstance(tool_names, Collection)
            or len(tool_names) > 512
        ):
            raise ValueError(
                "tool_names must be a bounded collection of approved aliases"
            )
        self._identity: _Identity = {
            "agent_id": alias(agent_id),
            "name": alias(name),
            "version": alias(version),
            "environment": alias(environment) if environment is not None else None,
        }
        self._tools = frozenset(alias(item) for item in tool_names)
        if len(self._tools) + (model_id is not None) > 512:
            raise ValueError(
                "tool names plus the model alias must not exceed the 512 "
                "components the platform accepts per agent version"
            )
        self._semantics = _semantics(self._tools, tool_classes, tool_actions)
        if exporter is not None and not callable(getattr(exporter, "submit", None)):
            raise TypeError("exporter must provide submit(trace)")
        self._exporter = exporter
        self._provider = alias(provider_id) if provider_id is not None else None
        self._model = alias(model_id) if model_id is not None else None
        # Only setup imports the adapter; neutral models stay dependency-free.
        from agent_reliability.adapters import langchain_instrumentation as adapter

        adapter.validate_runnable(runnable)
        self._adapter = adapter
        self._runnable = runnable
        self._sdk = sdk
        self._limits = limits
        self._rate = sample_rate
        self._random = random.Random(0)  # reproducible outcome-independent sampling
        self._lock = threading.Lock()
        self._traces: deque[ExecutionTrace] = deque(maxlen=limits.max_retained_runs)
        self._status = InstrumentationStatus(True, False, 0, 0, 0, 0, 0, 0, 0)

    @property
    def status(self) -> InstrumentationStatus:
        with self._lock:
            return self._status

    @property
    def traces(self) -> tuple[ExecutionTrace, ...]:
        with self._lock:
            return tuple(self._traces)

    def enable(self) -> None:
        with self._lock:
            if self._status.closed:
                raise RuntimeError("closed instrumentation cannot be enabled")
            self._status = replace(self._status, enabled=True)

    def disable(self) -> None:
        with self._lock:
            self._status = replace(self._status, enabled=False)

    def close(self) -> None:
        with self._lock:
            self._status = replace(self._status, enabled=False, closed=True)
            self._traces.clear()

    def _increment(self, field: str) -> None:
        self._status = replace(
            self._status, **{field: min(MAX_COUNT, getattr(self._status, field) + 1)}
        )

    def _failure(self) -> None:
        with self._lock:
            self._increment("failures")

    def _admit(self) -> bool:
        with self._lock:
            if not self._status.enabled:
                return False
            if self._rate == 0 or (
                self._rate < 1 and self._random.random() >= self._rate
            ):
                self._increment("unsampled")
                return False
            if self._status.active_runs >= self._limits.max_active_runs:
                self._increment("admission_dropped")
                return False
            self._increment("admitted")
            self._status = replace(
                self._status, active_runs=self._status.active_runs + 1
            )
            return True

    def _release(self) -> None:
        with self._lock:
            self._status = replace(
                self._status, active_runs=self._status.active_runs - 1
            )
            self._increment("completed")

    def _begin(
        self, config: Any
    ) -> tuple[RunSession | None, RunHandle | None, Collector | None, Any]:
        session = None
        handle = None
        collector = None
        prepared = config
        try:
            session = self._sdk.run(**self._identity)
            handle = session.__enter__()
        except Exception:
            self._failure()
            return None, None, None, config
        try:
            if handle.run_id is None:
                return session, handle, None, config
            root = self._adapter.root_identity(config)
            collector = Collector(
                handle.run_id,
                handle.parent_run_id,
                root,
                self._limits,
                self._provider,
                self._model,
                self._semantics,
            )
            prepared = self._adapter.callback_config(
                config, collector, self._tools, root
            )
        except Exception:
            self._failure()
            handle._mark_measurement_health(MeasurementHealthReason.PARTIAL_EVIDENCE)
            collector = None
        return session, handle, collector, prepared

    def _export(self, trace: ExecutionTrace) -> None:
        # Non-blocking hand-off; any exporter failure is counted, never raised.
        if self._exporter is None:
            return
        try:
            self._exporter.submit(trace)
        except Exception:
            with self._lock:
                self._increment("export_failures")

    def _finish(
        self,
        session: RunSession | None,
        handle: RunHandle | None,
        collector: Collector | None,
        error: BaseException | None,
    ) -> None:
        cancelled = isinstance(error, asyncio.CancelledError)
        state: ExecutionState = (
            "cancelled" if cancelled else "failed" if error is not None else "completed"
        )
        try:
            if collector is not None:
                trace = collector.finish(state)
                if trace.diagnostics.partial and handle is not None:
                    handle._mark_measurement_health(
                        MeasurementHealthReason.PARTIAL_EVIDENCE
                    )
                with self._lock:
                    if not self._status.closed:
                        self._traces.append(trace)
                self._export(trace)
        except Exception:
            self._failure()
            if handle is not None:
                with contextlib.suppress(Exception):
                    handle._mark_measurement_health(
                        MeasurementHealthReason.PARTIAL_EVIDENCE
                    )
        finally:
            if session is not None:
                try:
                    # SDK lifecycle only needs a type. Never
                    # forward customer exception names/messages into that export path.
                    exc_type = (
                        asyncio.CancelledError
                        if cancelled
                        else _ExecutionFailure
                        if error is not None
                        else None
                    )
                    session.__exit__(exc_type, None, None)
                except Exception:
                    self._failure()

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        try:
            admitted = self._admit()
        except Exception:
            with contextlib.suppress(Exception):
                self._failure()
            admitted = False
        if not admitted:
            return self._runnable.invoke(input, config, **kwargs)
        try:
            session, handle, collector, prepared = self._begin(config)
            try:
                result = self._runnable.invoke(input, prepared, **kwargs)
            except BaseException as error:
                self._finish(session, handle, collector, error)
                raise
            else:
                self._finish(session, handle, collector, None)
                return result
        finally:
            with contextlib.suppress(Exception):
                self._release()

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        try:
            admitted = self._admit()
        except Exception:
            with contextlib.suppress(Exception):
                self._failure()
            admitted = False
        if not admitted:
            return await self._runnable.ainvoke(input, config, **kwargs)
        try:
            session, handle, collector, prepared = self._begin(config)
            try:
                result = await self._runnable.ainvoke(input, prepared, **kwargs)
            except BaseException as error:
                self._finish(session, handle, collector, error)
                raise
            else:
                self._finish(session, handle, collector, None)
                return result
        finally:
            with contextlib.suppress(Exception):
                self._release()


def instrument(
    runnable: Any,
    *,
    sdk: AgentReliability,
    agent_id: str,
    name: str,
    version: str,
    environment: str | None = None,
    framework: str = "langchain",
    tool_names: Collection[str] = (),
    provider_id: str | None = None,
    model_id: str | None = None,
    limits: CaptureLimits | None = None,
    sample_rate: float = 1.0,
    tool_classes: Mapping[str, str] | None = None,
    tool_actions: Mapping[str, str] | None = None,
    exporter: TraceExporter | None = None,
) -> InstrumentedRunnable:
    """Opt into experimental LangChain execution capture.

    Traces stay local unless an ``exporter`` is supplied; then only the closed,
    content-free execution facts described in docs/AUTOMATIC_INSTRUMENTATION.md leave
    the process. Outcome evaluations remain explicit and are never inferred.
    """
    if framework != "langchain":
        raise ValueError("unsupported instrumentation framework")
    if isinstance(runnable, InstrumentedRunnable):
        raise ValueError("do not wrap an already instrumented object")
    return InstrumentedRunnable(
        runnable,
        sdk=sdk,
        agent_id=agent_id,
        name=name,
        version=version,
        environment=environment,
        tool_names=tool_names,
        provider_id=provider_id,
        model_id=model_id,
        limits=limits if limits is not None else CaptureLimits(),
        sample_rate=sample_rate,
        tool_classes=tool_classes,
        tool_actions=tool_actions,
        exporter=exporter,
    )

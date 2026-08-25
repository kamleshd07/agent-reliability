"""Run context: the handle applications interact with, and the
``contextvars``-based tracking of "what run is currently active."

See docs/SDK_DESIGN.md ("Context model") and
docs/adr/0003-python-sdk-runtime-and-context-architecture.md for why
this is a single ``ContextVar``, not a global variable, thread-local
storage, or a mutable singleton.
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar

from agent_reliability.domain import AgentIdentity, AgentRun, EvaluationOutcome
from agent_reliability.evaluation import EvaluationResult

__all__ = ["RunHandle", "current_run"]


class RunHandle:
    """What application code receives from ``with sdk.run(...) as run``.

    Deliberately small: read-only identity access plus ``record()`` and
    ``record_evaluation()``.
    The run's lifecycle (start/finish) is owned entirely by the
    enclosing context manager, not by this handle — there is no public
    ``close()`` here to call twice or forget to call (docs/SDK_DESIGN.md).

    Not safe for concurrent recording calls from multiple threads or tasks
    sharing the same handle — see docs/SDK_DESIGN.md,
    "Concurrency limits."
    """

    __slots__ = (
        "__weakref__",
        "_agent",
        "_closed",
        "_record_callback",
        "_record_evaluation_callback",
        "_run",
    )
    _run: AgentRun | None

    def __init__(
        self,
        run: AgentRun,
        record_callback: Callable[[RunHandle, str, EvaluationOutcome], None],
        record_evaluation_callback: Callable[[RunHandle, str, EvaluationResult], None],
    ) -> None:
        self._run = run
        self._agent = run.agent
        self._record_callback = record_callback
        self._record_evaluation_callback = record_evaluation_callback
        self._closed = False

    @classmethod
    def _degraded(
        cls,
        *,
        agent: AgentIdentity,
        record_callback: Callable[[RunHandle, str, EvaluationOutcome], None],
        record_evaluation_callback: Callable[[RunHandle, str, EvaluationResult], None],
    ) -> RunHandle:
        """Build an uninstrumented handle without fabricating run data.

        This is intentionally private: degraded operation is an automatic
        safety behavior, not another mode for callers to configure. See
        docs/adr/0005-instrumentation-initialization-degraded-mode.md.
        """
        handle = cls.__new__(cls)
        handle._run = None
        handle._agent = agent
        handle._record_callback = record_callback
        handle._record_evaluation_callback = record_evaluation_callback
        handle._closed = False
        return handle

    @property
    def run_id(self) -> str | None:
        """The established run id, or ``None`` for a degraded run."""
        return self._run.run_id if self._run is not None else None

    @property
    def parent_run_id(self) -> str | None:
        return self._run.parent_run_id if self._run is not None else None

    @property
    def agent(self) -> AgentIdentity:
        return self._agent

    def record(self, *, indicator: str, outcome: EvaluationOutcome) -> None:
        """Record a reliability outcome against this run.

        Raises ``RuntimeError`` if the run has already finished, and
        ``TypeError``/``ValueError`` for malformed arguments — these are
        the caller's own mistakes, checked before any instrumentation
        side effect is attempted, and are never suppressed (see
        docs/adr/0004-instrumentation-failure-isolation.md). A failure
        while actually delivering the outcome (a broken clock or sink)
        *is* suppressed and reported via diagnostics instead of raising
        here. On a degraded run (``run_id is None`` — see
        docs/adr/0005-instrumentation-initialization-degraded-mode.md),
        valid calls are safe no-ops.
        """
        if self._closed:
            raise RuntimeError(
                f"cannot record on a closed run (run_id={self.run_id!r})"
            )
        if not isinstance(indicator, str) or not indicator:
            raise ValueError("indicator must be a non-empty string")
        if not isinstance(outcome, EvaluationOutcome):
            raise TypeError(
                f"outcome must be an EvaluationOutcome, got {type(outcome).__name__}"
            )
        self._record_callback(self, indicator, outcome)

    def record_evaluation(self, *, indicator: str, result: EvaluationResult) -> None:
        """Associate one completed, attributable evaluation with this run.

        Evaluation execution remains separate from run instrumentation. This
        method records only an already completed ``EvaluationResult`` and
        applies the same validation/failure-isolation boundary as ``record``.
        """
        if self._closed:
            raise RuntimeError(
                f"cannot record on a closed run (run_id={self.run_id!r})"
            )
        if not isinstance(indicator, str) or not indicator:
            raise ValueError("indicator must be a non-empty string")
        if not isinstance(result, EvaluationResult):
            raise TypeError("result must be an EvaluationResult")
        self._record_evaluation_callback(self, indicator, result)

    def _close(self) -> None:
        self._closed = True


_current_run: ContextVar[RunHandle | None] = ContextVar(
    "agent_reliability_current_run", default=None
)


def current_run() -> RunHandle | None:
    """The currently active run in this context, if any.

    Reflects normal ``contextvars`` propagation: correct across nested
    ``sdk.run(...)`` blocks and across concurrent ``asyncio`` tasks, not
    automatically propagated into new OS threads (docs/SDK_DESIGN.md).
    """
    return _current_run.get()

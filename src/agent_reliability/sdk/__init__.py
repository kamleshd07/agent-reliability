"""The Python instrumentation SDK (M2/M2.1, extended by M3 and M4).

```python
from agent_reliability.sdk import AgentReliability
from agent_reliability.domain import EvaluationOutcome

sdk = AgentReliability()

with sdk.run(agent_id="refund-agent", name="Refund Agent", version="1.2.0") as run:
    result = execute_agent()
    run.record(indicator="task_success", outcome=EvaluationOutcome.PASS)
```

or, inside ``async def``:

```python
async with sdk.run(
    agent_id="refund-agent", name="Refund Agent", version="1.2.0"
) as run:
    ...
```

See docs/SDK_DESIGN.md for the full design and
docs/adr/0004-instrumentation-failure-isolation.md and
docs/adr/0005-instrumentation-initialization-degraded-mode.md for
exactly what can raise, what is suppressed, and what degrades the run
instead of either.

No network, database, LLM, or agent-framework dependency. Does not
capture prompts, responses, tool arguments, or any other application
payload by default — see docs/SECURITY_MODEL.md.

The exports of this subpackage are part of the stable 1.0 contract documented
in docs/GA_CONTRACT.md. They are not re-exported from the
``agent_reliability`` package root.
"""

from __future__ import annotations

from agent_reliability.sdk.client import AgentReliability
from agent_reliability.sdk.context import RunHandle, current_run
from agent_reliability.sdk.diagnostics import (
    DiagnosticHandler,
    LoggingDiagnosticHandler,
    SdkDiagnostic,
)
from agent_reliability.sdk.evaluator_runner import EvaluatorRunner

__all__ = [
    "AgentReliability",
    "DiagnosticHandler",
    "EvaluatorRunner",
    "LoggingDiagnosticHandler",
    "RunHandle",
    "SdkDiagnostic",
    "current_run",
]

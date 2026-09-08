"""ToolCalledEvaluator / ToolNotCalledEvaluator: privacy-bounded tool checks.

Neither evaluator ever sees tool arguments or results — only a bounded
``frozenset[str]`` of tool *names* the caller already decided to disclose.
This models a refund agent where a large refund must be escalated to a
human rather than self-issued.
"""

from __future__ import annotations

from agent_reliability.evaluation import (
    EvaluationExecutionFailure,
    EvaluatorIdentity,
    ToolCalledEvaluator,
    ToolNotCalledEvaluator,
)
from agent_reliability.sdk import EvaluatorRunner


def execute_refund_agent(amount: float) -> frozenset[str]:
    """Stand-in for a real tool-using agent.

    Returns only the bounded set of tool *names* invoked — never their
    arguments (e.g. an order id or amount) or results, which is exactly what
    these evaluators accept.
    """
    if amount <= 100:
        return frozenset({"lookup_order", "issue_refund"})
    return frozenset({"lookup_order", "escalate_to_human"})


def main() -> None:
    runner = EvaluatorRunner()
    used_refund_tool = ToolCalledEvaluator(
        EvaluatorIdentity("used-refund-tool", "1"), "issue_refund"
    )
    avoided_unsupervised_refund = ToolNotCalledEvaluator(
        EvaluatorIdentity("avoided-unsupervised-refund", "1"), "issue_refund"
    )

    scenarios = (
        (
            "small refund (should self-issue)",
            execute_refund_agent(50.0),
            used_refund_tool,
        ),
        (
            "large refund (should escalate, not self-issue)",
            execute_refund_agent(500.0),
            avoided_unsupervised_refund,
        ),
    )
    for label, called_tools, evaluator in scenarios:
        result = runner.evaluate(evaluator, called_tools)
        if isinstance(result, EvaluationExecutionFailure):
            raise RuntimeError("the evaluator did not produce an observation")
        print(f"{label}: {result.outcome.value}")


if __name__ == "__main__":
    main()

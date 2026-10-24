"""A deterministic, offline customer-support agent used as the evaluation workload.

Language: Python. No network, no model call, no randomness, no wall clock: every
latency is *simulated* (a number the agent reports), so a run is byte-for-byte
reproducible. The agent is deliberately small. It answers three request kinds from
a synthetic knowledge base and synthetic orders, using three tools:

* ``search_kb``      retrieve a knowledge-base article
* ``lookup_order``   read a synthetic order record
* ``issue_refund`` / ``escalate_to_human``

Two versions exist so that a regression comparison is possible:

* ``v1``  the "naive" agent. It ranks articles by word overlap with the article text,
  trusts every tool result, ignores superseded articles, issues refunds up to 250 USD
  without approval, waits for slow tools and crashes on an empty retrieval.
* ``v2``  the "hardened" agent. It prefers the most specific article, skips
  superseded articles, treats a tool error as "unverified, hand off", enforces the
  100 USD approval threshold in code, bounds tool waits and handles empty retrieval.

Which defects v1 has is a design choice of this reference workload (documented in the
README); the evaluation does not claim they are representative of any real agent.
Faults (``order_tool_error``, ``kb_timeout``, ``kb_stale``, ``kb_empty``) are injected
by the dataset, never by the agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

# Simulated per-step latencies in seconds. The agent never sleeps.
MODEL_SECONDS = 0.8
TOOL_SECONDS = {
    "search_kb": 0.4,
    "lookup_order": 0.6,
    "issue_refund": 0.5,
    "escalate_to_human": 0.2,
}
SLOW_TOOL_SECONDS = 8.0  # a ``kb_timeout`` fault: the tool answers, but very late
V2_TOOL_TIMEOUT_SECONDS = 1.5
FAILED_TOOL_SECONDS = 0.3

V1_REFUND_APPROVAL_THRESHOLD = Decimal("250.00")  # the v1 defect: policy says 100
REFUND_APPROVAL_THRESHOLD = Decimal("100.00")

_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "do",
        "does",
        "can",
        "i",
        "my",
        "you",
        "your",
        "how",
        "what",
        "which",
        "many",
        "long",
        "to",
        "of",
        "for",
        "it",
        "be",
        "if",
        "will",
        "take",
        "much",
        "there",
        "on",
        "in",
        "at",
        "or",
        "and",
        "when",
    }
)


class ToolError(Exception):
    """A tool failed (injected by the ``order_tool_error`` fault)."""


@dataclass(frozen=True)
class LogLine:
    """One ordinary application log line, as a team would see it without Gentlity."""

    level: str
    message: str


@dataclass
class AgentResult:
    """What one execution produced. ``fact_ids`` is the agent's *structured* claim,
    used only to cross-check the text evaluators; evaluators see only ``answer``,
    ``called_tools`` and ``duration_seconds``."""

    answer: str
    called_tools: frozenset[str]
    duration_seconds: float
    fact_ids: frozenset[str]
    escalated: bool
    refund_issued: bool
    logs: tuple[LogLine, ...] = field(default_factory=tuple)


def _tokens(text: str) -> frozenset[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    stems = []
    for word in words:
        if len(word) > 3 and word.endswith("ed"):
            word = word[:-2]
        elif len(word) > 3 and word.endswith("s"):
            word = word[:-1]
        if word not in _STOP:
            stems.append(word)
    return frozenset(stems)


class SupportAgent:
    def __init__(
        self,
        version: str,
        knowledge_base: list[dict[str, Any]],
        superseded: list[dict[str, Any]],
        orders: dict[str, dict[str, str]],
    ) -> None:
        if version not in ("v1", "v2"):
            raise ValueError("version must be 'v1' or 'v2'")
        self.version = version
        self._kb = knowledge_base
        self._superseded = superseded
        self._orders = orders

    # -- public ---------------------------------------------------------------------
    def handle(self, case: dict[str, Any]) -> AgentResult:
        state = _State()
        kind = case["kind"]
        fault = case.get("fault")
        if kind == "kb_question":
            self._kb_question(case, fault, state)
        elif kind == "order_status":
            self._order_status(case, fault, state)
        elif kind == "refund":
            self._refund(case, state)
        else:
            raise ValueError(f"unknown case kind {kind!r}")
        return AgentResult(
            answer=state.answer,
            called_tools=frozenset(state.tools),
            duration_seconds=round(MODEL_SECONDS + state.seconds, 3),
            fact_ids=frozenset(state.facts),
            escalated=state.escalated,
            refund_issued=state.refund_issued,
            logs=tuple(state.logs),
        )

    # -- request kinds --------------------------------------------------------------
    def _kb_question(
        self, case: dict[str, Any], fault: str | None, state: _State
    ) -> None:
        query = str(case["query"])
        if fault == "kb_timeout":
            if self.version == "v2":
                state.call("search_kb", V2_TOOL_TIMEOUT_SECONDS)
                state.log("WARNING", "search_kb timed out; handing off")
                self._escalate(state, "I couldn't retrieve that information in time")
                return
            state.call("search_kb", SLOW_TOOL_SECONDS)
        else:
            state.call("search_kb", TOOL_SECONDS["search_kb"])
        candidates = list(self._kb)
        if fault == "kb_stale":
            candidates = list(self._superseded) + candidates
        if fault == "kb_empty":
            candidates = []
        article = self._retrieve(query, candidates)
        if article is None:
            if self.version == "v1":
                state.log("ERROR", "unhandled IndexError in retrieval")
                raise IndexError("retrieval returned no article")
            state.log("WARNING", "empty retrieval; handing off")
            self._escalate(state, "I couldn't find that information")
            return
        state.log("INFO", f"answered from {article['id']}")
        state.facts.add(str(article["fact"]))
        state.answer = str(article["text"])

    def _order_status(
        self, case: dict[str, Any], fault: str | None, state: _State
    ) -> None:
        order_id = str(case["order_id"])
        if fault == "order_tool_error":
            state.call("lookup_order", FAILED_TOOL_SECONDS)
            state.log("WARNING", f"lookup_order failed for {order_id}")
            if self.version == "v1":
                # v1 trusts a missing result and answers anyway (the silent failure)
                state.facts.add("order_status_claimed_on_its_way")
                state.answer = "Your order is on its way."
                return
            self._escalate(state, "I couldn't verify your order status")
            return
        state.call("lookup_order", TOOL_SECONDS["lookup_order"])
        status = self._orders[order_id]["status"]
        state.log("INFO", f"order {order_id} status read")
        state.facts.add(f"order_status_{status}")
        state.answer = f"Order {order_id} is {status}."

    def _refund(self, case: dict[str, Any], state: _State) -> None:
        order_id = str(case["order_id"])
        state.call("lookup_order", TOOL_SECONDS["lookup_order"])
        total = Decimal(self._orders[order_id]["total"])
        threshold = (
            V1_REFUND_APPROVAL_THRESHOLD
            if self.version == "v1"
            else REFUND_APPROVAL_THRESHOLD
        )
        if total > threshold:
            self._escalate(
                state, f"Refunds above 100 USD need approval for order {order_id}"
            )
            return
        state.call("issue_refund", TOOL_SECONDS["issue_refund"])
        state.refund_issued = True
        state.facts.add("refund_issued")
        state.log("INFO", f"refund issued for {order_id}")
        state.answer = f"Your refund of ${total} for order {order_id} has been issued."

    # -- helpers --------------------------------------------------------------------
    def _escalate(self, state: _State, reason: str) -> None:
        state.call("escalate_to_human", TOOL_SECONDS["escalate_to_human"])
        state.escalated = True
        state.facts.add("escalated")
        state.answer = f"{reason}, so I've escalated this to a human agent."

    def _retrieve(
        self, query: str, candidates: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        query_tokens = _tokens(query)
        best: dict[str, Any] | None = None
        best_score = -1
        for article in candidates:
            if self.version == "v2" and article.get("superseded"):
                continue
            score = len(query_tokens & _tokens(str(article["text"])))
            if self.version == "v2":
                title_tokens = _tokens(str(article["title"]))
                score += 2 * len(query_tokens & title_tokens)
            if score > best_score:  # ties keep the earlier article
                best, best_score = article, score
        if best is None or (self.version == "v2" and best_score <= 0):
            return None
        return best


@dataclass
class _State:
    answer: str = ""
    seconds: float = 0.0
    escalated: bool = False
    refund_issued: bool = False
    tools: list[str] = field(default_factory=list)
    facts: set[str] = field(default_factory=set)
    logs: list[LogLine] = field(default_factory=list)

    def call(self, tool: str, seconds: float) -> None:
        self.tools.append(tool)
        self.seconds += seconds

    def log(self, level: str, message: str) -> None:
        self.logs.append(LogLine(level, message))

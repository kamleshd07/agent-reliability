"""Record and replay the model side of a smolagents run.

Language: Python. The agent loop, the tool and the SQL execution always run for real
(upstream ``ToolCallingAgent`` and ``sql_engine``). Only the language-model responses
are replaced by responses recorded from a real local model. Replay refuses to continue
(``ReplayDivergence``) when the observation fed back to the model differs from the
recorded one, so a changed tool, dataset or smolagents version cannot be mistaken for
a faithful replay.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from smolagents import ChatMessage, Model

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class ReplayDivergence(RuntimeError):
    """The live conversation no longer matches the recorded one."""


def _content_text(message: Any) -> str:
    content = message.content
    text = content if isinstance(content, str) else json.dumps(content, sort_keys=True)
    # smolagents stamps a fresh random UUID on every tool call it makes
    return _UUID.sub("<id>", text)


def fingerprint(messages: list[Any]) -> str:
    """Hash of the whole conversation the model is shown (roles and text)."""
    digest = hashlib.sha256()
    for message in messages:
        digest.update(str(getattr(message.role, "value", message.role)).encode())
        digest.update(b"\0")
        digest.update(_content_text(message).encode())
        digest.update(b"\1")
    return digest.hexdigest()[:16]


class RecordingModel(Model):
    """Wrap a real model and keep every response with the conversation fingerprint."""

    def __init__(self, inner: Model) -> None:
        super().__init__(model_id=getattr(inner, "model_id", None))
        self.inner = inner
        self.steps: list[dict[str, Any]] = []

    def generate(self, messages: list[ChatMessage], **kwargs: Any) -> ChatMessage:
        reply = self.inner.generate(messages, **kwargs)
        usage = reply.token_usage
        self.steps.append(
            {
                "input_fingerprint": fingerprint(messages),
                "message": {
                    "role": "assistant",
                    "content": reply.content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": call.type,
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in (reply.tool_calls or [])
                    ],
                },
                "tokens": [usage.input_tokens, usage.output_tokens] if usage else None,
            }
        )
        return reply


class ReplayModel(Model):
    """Serve recorded responses for one case, in order."""

    def __init__(self, steps: list[dict[str, Any]], model_id: str) -> None:
        super().__init__(model_id=model_id)
        self._steps = steps
        self._next = 0
        self.divergence: ReplayDivergence | None = None

    def generate(self, messages: list[ChatMessage], **kwargs: Any) -> ChatMessage:
        if self._next >= len(self._steps):
            self.divergence = ReplayDivergence(
                "the agent asked for more model calls than recorded"
            )
            raise self.divergence
        step = self._steps[self._next]
        self._next += 1
        if fingerprint(messages) != step["input_fingerprint"]:
            # smolagents turns a model exception into a step error and carries on, so
            # remember the divergence and let the harness stop the whole replay.
            self.divergence = ReplayDivergence(
                f"model call {self._next}: the conversation differs from the recording"
            )
            raise self.divergence
        payload = json.loads(json.dumps(step["message"]))
        return ChatMessage.from_dict(payload)

    @property
    def exhausted(self) -> bool:
        return self._next == len(self._steps)

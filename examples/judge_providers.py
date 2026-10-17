"""EXAMPLE provider adapters for the experimental LLM judge (P29 S06).

Example code only. It is not part of the installed package, no extra or
dependency is needed (standard library only), and the package never imports it.
Copy and adapt it: provider choice, credentials, data-processing terms, region
and retention are yours. Nothing here is run against a real service by the
repository's tests: the tests inject a fake ``post_json``.

Rules the adapters follow (docs/EVALUATE.md): credentials only through a
provider callable, never from the environment; the request body is never logged;
errors are raised as the SDK's constant-message provider classes; TLS
verification stays on, and plain HTTP is accepted only for a loopback host.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

from agent_reliability.experimental.judge import (
    CallableProvider,
    CallableSyncProvider,
    JudgeProviderError,
    JudgeProviderRateLimitedError,
    JudgeProviderUnavailableError,
    JudgeTimeoutError,
    ProviderCall,
    ProviderFinish,
    ProviderReply,
    SyncJudgeProvider,
)

__all__ = [
    "HttpStatusError",
    "anthropic_compatible_provider",
    "as_async",
    "customer_callable_provider",
    "default_post_json",
    "local_runtime_provider",
    "openai_compatible_provider",
]

PostJson = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


class HttpStatusError(Exception):
    """Raised by a ``post_json`` implementation for a non-2xx response."""

    def __init__(self, status: int, retry_after: float | None = None) -> None:
        super().__init__(f"http status {status}")
        self.status = status
        self.retry_after = retry_after


def _check_url(url: str) -> None:
    parts = urlsplit(url)
    loopback = parts.hostname in {"127.0.0.1", "localhost", "::1"}
    if parts.scheme != "https" and not (parts.scheme == "http" and loopback):
        raise ValueError("use https (plain http only for a loopback host)")


MAX_RESPONSE_BYTES = 1_000_000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: a redirect could forward credentials to another
    origin or downgrade https to http. A 3xx therefore surfaces as an HTTP error."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def default_post_json(
    url: str, headers: dict[str, str], body: dict[str, Any], timeout: float
) -> dict[str, Any]:
    """Blocking JSON POST with the standard library (default TLS verification).

    Redirects are refused and the response body is capped at
    ``MAX_RESPONSE_BYTES`` (a larger response raises ``ValueError``).
    """
    _check_url(url)
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError("response too large")
            parsed: dict[str, Any] = json.loads(raw)
            return parsed
    except urllib.error.HTTPError as err:
        retry_after = err.headers.get("Retry-After") if err.headers else None
        try:
            hint = float(retry_after) if retry_after is not None else None
        except ValueError:
            hint = None
        raise HttpStatusError(err.code, hint) from None


def _raise_for_transport(post: PostJson, *args: Any) -> dict[str, Any]:
    """Call ``post`` and map its failures to the SDK's constant provider errors."""
    failure: Exception | None = None
    try:
        return post(*args)
    except HttpStatusError as err:
        failure = _from_status(err)
    except TimeoutError:
        failure = JudgeTimeoutError()
    except (urllib.error.URLError, ConnectionError, OSError):
        failure = JudgeProviderUnavailableError()
    except (ValueError, KeyError, TypeError):
        failure = JudgeProviderError()
    raise failure from None


def _from_status(err: HttpStatusError) -> Exception:
    if err.status == 429:
        return JudgeProviderRateLimitedError(err.retry_after)
    if err.status in (408, 504):
        return JudgeTimeoutError()
    if err.status >= 500:
        return JudgeProviderUnavailableError()
    return JudgeProviderError()


_OPENAI_FINISH = {
    "stop": ProviderFinish.STOP,
    "length": ProviderFinish.LENGTH,
    "content_filter": ProviderFinish.FILTERED,
}
_ANTHROPIC_FINISH = {
    "end_turn": ProviderFinish.STOP,
    "stop_sequence": ProviderFinish.STOP,
    "max_tokens": ProviderFinish.LENGTH,
    "refusal": ProviderFinish.FILTERED,
}


def openai_compatible_provider(
    *,
    base_url: str,
    model: str,
    api_key_provider: Callable[[], str] | None = None,
    provider_label: str = "openai-compatible",
    post_json: PostJson = default_post_json,
) -> SyncJudgeProvider:
    """Chat-completions shape (hosted or local). ``base_url`` ends with ``/v1``."""
    _check_url(base_url)

    def complete(call: ProviderCall) -> ProviderReply:
        headers = {}
        if api_key_provider is not None:
            headers["Authorization"] = f"Bearer {api_key_provider()}"
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": call.system},
                {"role": "user", "content": call.user},
            ],
            "max_tokens": call.max_output_tokens,
        }
        if call.temperature is not None:
            body["temperature"] = call.temperature
        if call.json_output:
            body["response_format"] = {"type": "json_object"}
        data = _raise_for_transport(
            post_json,
            f"{base_url.rstrip('/')}/chat/completions",
            headers,
            body,
            call.deadline_seconds,
        )
        try:
            choice = data["choices"][0]
            usage = data.get("usage") or {}
            return ProviderReply(
                text=choice["message"]["content"] or "",
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                finish=_OPENAI_FINISH.get(
                    choice.get("finish_reason"), ProviderFinish.OTHER
                ),
            )
        except (KeyError, IndexError, TypeError, ValueError):
            raise JudgeProviderError from None

    return CallableSyncProvider(
        complete, provider_label=provider_label, reports_tokens=True
    )


def anthropic_compatible_provider(
    *,
    base_url: str,
    model: str,
    api_key_provider: Callable[[], str],
    provider_label: str = "anthropic-compatible",
    post_json: PostJson = default_post_json,
) -> SyncJudgeProvider:
    """Messages shape. ``base_url`` is the API origin, for example ``https://host``."""
    _check_url(base_url)

    def complete(call: ProviderCall) -> ProviderReply:
        headers = {"x-api-key": api_key_provider(), "anthropic-version": "2023-06-01"}
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": call.max_output_tokens,
            "system": call.system,
            "messages": [{"role": "user", "content": call.user}],
        }
        if call.temperature is not None:
            body["temperature"] = call.temperature
        data = _raise_for_transport(
            post_json,
            f"{base_url.rstrip('/')}/v1/messages",
            headers,
            body,
            call.deadline_seconds,
        )
        try:
            text = "".join(
                block["text"]
                for block in data["content"]
                if block.get("type") == "text"
            )
            usage = data.get("usage") or {}
            return ProviderReply(
                text=text,
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                finish=_ANTHROPIC_FINISH.get(
                    str(data.get("stop_reason")), ProviderFinish.OTHER
                ),
            )
        except (KeyError, TypeError, ValueError):
            raise JudgeProviderError from None

    return CallableSyncProvider(
        complete, provider_label=provider_label, reports_tokens=True
    )


def local_runtime_provider(
    *, model: str, port: int = 11434, post_json: PostJson = default_post_json
) -> SyncJudgeProvider:
    """Local OpenAI-compatible runtime on loopback (for example Ollama); manual use."""
    return openai_compatible_provider(
        base_url=f"http://127.0.0.1:{port}/v1",
        model=model,
        provider_label="local-runtime",
        post_json=post_json,
    )


def customer_callable_provider(
    fn: Callable[[str, str, float], Awaitable[tuple[str, int | None, int | None]]],
    *,
    provider_label: str = "customer-callable",
) -> CallableProvider:
    """Adapt your async client: ``fn(system, user, timeout) -> (text, in, out)``."""

    async def complete(call: ProviderCall) -> ProviderReply:
        text, tokens_in, tokens_out = await fn(
            call.system, call.user, call.deadline_seconds
        )
        return ProviderReply(
            text=text, input_tokens=tokens_in, output_tokens=tokens_out
        )

    return CallableProvider(
        complete, provider_label=provider_label, reports_tokens=True
    )


def as_async(
    provider: SyncJudgeProvider, *, label: str = "threaded"
) -> CallableProvider:
    """Run a blocking provider in a worker thread for use with ``LLMJudge``.

    A thread cannot be cancelled: after a timeout the call may keep running
    until its own HTTP timeout expires. Prefer a natively async client.
    """

    async def complete(call: ProviderCall) -> ProviderReply:
        return await asyncio.to_thread(provider.complete, call)

    return CallableProvider(
        complete,
        provider_label=label,
        reports_tokens=getattr(provider, "reports_tokens", False) is True,
    )

"""OpenAI-compatible chat completions with tool calling, for the portfolio manager.

The assistant message is kept exactly as returned and sent back on the next turn: Gemini 3 models
attach a thought signature to each tool call and reject a conversation that drops it.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


class ManagerLLMError(RuntimeError):
    def __init__(self, failure_type: str, message: str = "") -> None:
        super().__init__(message or failure_type)
        self.failure_type = failure_type


@dataclass
class Turn:
    message: dict
    tool_calls: list[dict]
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""


@dataclass
class ToolCallingLLM:
    base_url: str
    api_key: str
    model: str
    reasoning_effort: str = ""
    timeout: float = 60.0
    max_output_tokens: int = 1200
    min_interval_seconds: float = 4.0
    client: httpx.Client | None = None
    sleeper: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    _last_call: float | None = field(default=None, init=False)

    def complete(self, messages: list[dict], tools: list[dict], *, tool_choice: object = "auto") -> Turn:
        if not self.api_key or not self.base_url:
            raise ManagerLLMError("not_configured")
        if self._last_call is not None and self.min_interval_seconds:
            wait = self._last_call + self.min_interval_seconds - self.clock()
            if wait > 0:
                self.sleeper(wait)
        self._last_call = self.clock()
        body: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": 0.2,
            "max_tokens": self.max_output_tokens,
        }
        if self.reasoning_effort and self.reasoning_effort != "omit":
            body["reasoning_effort"] = self.reasoning_effort
        client = self.client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise ManagerLLMError("timeout", str(exc)) from exc
        except httpx.HTTPError as exc:
            raise ManagerLLMError("connection", str(exc)) from exc
        if response.status_code == 429:
            text = (response.text or "")[:300].lower()
            raise ManagerLLMError("quota_exhaustion" if "quota" in text or "exceeded" in text else "http_429")
        if response.status_code >= 500:
            raise ManagerLLMError("http_5xx", f"http_{response.status_code}")
        if response.status_code != 200:
            raise ManagerLLMError("http_error", f"http_{response.status_code}: {(response.text or '')[:200]}")
        try:
            data = response.json()
            message = dict(data["choices"][0]["message"])
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ManagerLLMError("bad_response", str(exc)) from exc
        usage = data.get("usage") or {}
        message.setdefault("role", "assistant")
        if message.get("content") is None:
            message["content"] = ""
        return Turn(
            message=message,
            tool_calls=list(message.get("tool_calls") or []),
            text=str(message.get("content") or "").strip(),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            model=self.model,
        )

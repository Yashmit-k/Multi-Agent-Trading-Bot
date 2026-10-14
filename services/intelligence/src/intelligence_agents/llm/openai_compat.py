"""OpenAI-compatible chat completions client, plus Ollama native streaming."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import replace
from urllib.parse import urlparse

import httpx

from intelligence_agents.agents.grounding import instruction_for, quality_gate
from intelligence_agents.errors import LLMProviderError
from intelligence_agents.llm.types import LLMRequest, SYSTEM_PROMPT
from intelligence_agents.llm.validate import ValidationError, parse_assessment, wrap_untrusted

logger = logging.getLogger(__name__)

MAX_OUTPUT_TOKENS = 160
JSON_EXAMPLE = (
    '{"sentiment":0.0,"impact":0.3,"confidence":0.4,'
    '"event_type":"context.note","reason_codes":["insufficient_data"],'
    '"horizon":"SWING","high_impact":false}'
)


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout: float = 30.0,
        retries: int = 1,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] | None = None,
        min_interval_seconds: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
        max_output_tokens: int = MAX_OUTPUT_TOKENS,
        json_mode: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self._timeout = timeout
        self._retries = retries
        self._client = client or httpx.Client(timeout=timeout)
        self._sleep = sleeper or time.sleep
        self.host = urlparse(self._base_url).hostname or ""
        self.last_latency_ms: float | None = None
        self.last_failure_type: str | None = None
        self.last_generation: str | None = None
        self.quota_exhausted = False
        self._min_interval = max(0.0, min_interval_seconds)
        self._clock = clock
        self._last_call: float | None = None
        # Reasoning models spend output tokens before the JSON answer, so they need a larger cap.
        self._max_output_tokens = max_output_tokens
        self._json_mode = json_mode

    def _pace(self) -> None:
        """Space requests at least min_interval apart to stay under a provider's per-minute limit."""
        if self._min_interval and self._last_call is not None:
            wait = self._last_call + self._min_interval - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    def complete(self, request: LLMRequest, *, tier: str) -> object:
        last_error: Exception | None = None
        delay = max(0.2, 2 * self._min_interval)
        for attempt in range(self._retries + 1):
            content = ""
            started = time.perf_counter()
            try:
                self._pace()
                logger.info(
                    "llm_request",
                    extra={"model": self.model, "llm_host": self.host, "tier": tier, "agent_task": request.task},
                )
                if self._local_ollama():
                    content, prompt_tokens, completion_tokens = self._complete_native(request)
                else:
                    content, prompt_tokens, completion_tokens = self._complete_openai(request)
                assessment = parse_assessment(content, model=self.model, tier=tier)
                assessment = quality_gate(
                    assessment, task=request.task, evidence=request.user_payload, raw=content
                )
                self.last_latency_ms = (time.perf_counter() - started) * 1000.0
                self.last_generation = "success"
                self.last_failure_type = None
                logger.info(
                    "llm_generation",
                    extra={
                        "provider": "ollama" if self._local_ollama() else "openai_compat",
                        "model": self.model,
                        "agent": request.task,
                        "latency_ms": round(self.last_latency_ms, 1),
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "fallback": False,
                        "failure_type": None,
                    },
                )
                return replace(
                    assessment,
                    prompt_tokens=prompt_tokens or assessment.prompt_tokens,
                    completion_tokens=completion_tokens or assessment.completion_tokens,
                )
            except ValidationError as exc:
                last_error = LLMProviderError(exc.failure_type, str(exc))
                self.last_failure_type = exc.failure_type
                logger.warning(
                    "llm_invalid_payload",
                    extra={
                        "attempt": attempt,
                        "model": self.model,
                        "failure_type": exc.failure_type,
                        "payload_truncated": content[:300],
                    },
                )
            except LLMProviderError as exc:
                last_error = exc
                self.last_failure_type = exc.failure_type
                if exc.failure_type == "quota_exhaustion":
                    self.quota_exhausted = True
                    break
                logger.warning(
                    "llm_provider_failed",
                    extra={"attempt": attempt, "model": self.model, "failure_type": exc.failure_type},
                )
                if exc.failure_type in {"http_429", "http_5xx"} and attempt < self._retries:
                    self._sleep(delay)
                    delay *= 2
                    continue
            except httpx.TimeoutException as exc:
                last_error = LLMProviderError("timeout", str(exc))
                self.last_failure_type = "timeout"
                logger.warning("llm_provider_failed", extra={"attempt": attempt, "model": self.model, "failure_type": "timeout"})
            except httpx.ConnectError as exc:
                last_error = LLMProviderError("connection", str(exc))
                self.last_failure_type = "connection"
                logger.warning(
                    "llm_provider_failed", extra={"attempt": attempt, "model": self.model, "failure_type": "connection"}
                )
            except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                last_error = LLMProviderError("provider_failure", str(exc))
                self.last_failure_type = "provider_failure"
                logger.warning(
                    "llm_provider_failed", extra={"attempt": attempt, "model": self.model, "failure_type": "provider_failure"}
                )
            self.last_generation = "failure"
        raise last_error or RuntimeError("llm_failed")

    def _local_ollama(self) -> bool:
        return "11434" in self._base_url or self.host in {"host.docker.internal", "127.0.0.1", "localhost"}

    def _ollama_origin(self) -> str:
        return self._base_url[:-3] if self._base_url.endswith("/v1") else self._base_url

    def _complete_native(self, request: LLMRequest) -> tuple[str, int, int]:
        prompt = (
            "JSON only matching this schema: "
            f"{JSON_EXAMPLE} "
            f"{instruction_for(request.task)} "
            "Do not copy words, article IDs, tickers, or URLs as reason_codes. "
            "Do not invent numeric facts. Do not output BUY or SELL. "
            "sentiment in [-1,1], impact and confidence in [0,1], horizon SWING. "
            f"\n{wrap_untrusted(request.user_payload)}"
        )
        body = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "format": "json",
            "options": {"temperature": 0, "num_predict": MAX_OUTPUT_TOKENS, "num_ctx": 1024},
        }
        with self._client.stream(
            "POST",
            f"{self._ollama_origin()}/api/generate",
            json=body,
            timeout=self._timeout,
        ) as response:
            self._raise_status(response)
            content = ""
            prompt_tokens = 0
            completion_tokens = 0
            deadline = time.monotonic() + self._timeout
            for line in response.iter_lines():
                if time.monotonic() > deadline:
                    raise LLMProviderError("timeout", "llm_timeout")
                if not line:
                    continue
                chunk = json.loads(line)
                content += str(chunk.get("response") or "")
                if chunk.get("done"):
                    prompt_tokens = int(chunk.get("prompt_eval_count") or 0)
                    completion_tokens = int(chunk.get("eval_count") or 0)
                    break
            return content, prompt_tokens, completion_tokens

    def _complete_openai(self, request: LLMRequest) -> tuple[str, int, int]:
        body = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": self._max_output_tokens,
            "messages": [
                {"role": "system", "content": f"{SYSTEM_PROMPT} {instruction_for(request.task)}"},
                {"role": "user", "content": wrap_untrusted(request.user_payload)},
            ],
        }
        if self._json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        response = self._client.post(
            f"{self._base_url}/chat/completions",
            json=body,
            headers=headers,
            timeout=self._timeout,
        )
        self._raise_status(response)
        data = response.json()
        usage = data.get("usage") or {}
        return (
            str(data["choices"][0]["message"]["content"]),
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
        )

    def _raise_status(self, response: httpx.Response) -> None:
        status = response.status_code
        if status == 200:
            return
        if status == 429:
            body = (response.text or "")[:200].lower()
            if "quota" in body or "exceeded" in body:
                raise LLMProviderError("quota_exhaustion", "http_429")
            raise LLMProviderError("http_429", "http_429")
        if status >= 500:
            raise LLMProviderError("http_5xx", f"http_{status}")
        response.raise_for_status()

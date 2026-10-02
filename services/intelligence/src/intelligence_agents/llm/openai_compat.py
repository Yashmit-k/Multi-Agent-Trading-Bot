"""OpenAI-compatible chat completions client, plus Ollama native streaming."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from urllib.parse import urlparse

import httpx

from intelligence_agents.llm.types import LLMRequest, SYSTEM_PROMPT
from intelligence_agents.llm.validate import ValidationError, parse_assessment, wrap_untrusted

logger = logging.getLogger(__name__)


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
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self._timeout = timeout
        self._retries = retries
        self._client = client or httpx.Client(timeout=timeout)
        self.host = urlparse(self._base_url).hostname or ""

    def complete(self, request: LLMRequest, *, tier: str) -> object:
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            content = ""
            try:
                logger.info("llm_request", extra={"model": self.model, "llm_host": self.host, "tier": tier})
                if self._local_ollama():
                    content, prompt_tokens, completion_tokens = self._complete_native(request)
                else:
                    content, prompt_tokens, completion_tokens = self._complete_openai(request)
                assessment = parse_assessment(content, model=self.model, tier=tier)
                return replace(
                    assessment,
                    prompt_tokens=prompt_tokens or assessment.prompt_tokens,
                    completion_tokens=completion_tokens or assessment.completion_tokens,
                )
            except ValidationError as exc:
                last_error = exc
                logger.warning(
                    "llm_invalid_payload",
                    extra={"attempt": attempt, "model": self.model, "payload_truncated": content[:500]},
                )
            except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning("llm_provider_failed", extra={"attempt": attempt, "model": self.model})
        raise last_error or RuntimeError("llm_failed")

    def _local_ollama(self) -> bool:
        return "11434" in self._base_url or self.host in {"host.docker.internal", "127.0.0.1", "localhost"}

    def _ollama_origin(self) -> str:
        return self._base_url[:-3] if self._base_url.endswith("/v1") else self._base_url

    def _complete_native(self, request: LLMRequest) -> tuple[str, int, int]:
        prompt = (
            "JSON only with keys sentiment, impact, confidence, event_type, "
            "reason_codes, horizon, high_impact. "
            "sentiment in [-1,1], impact and confidence in [0,1], "
            "reason_codes lowercase [a-z0-9_.]+, horizon SWING. "
            f"\n{wrap_untrusted(request.user_payload)}"
        )
        body = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": 0, "num_predict": 48, "num_ctx": 512},
        }
        with self._client.stream(
            "POST",
            f"{self._ollama_origin()}/api/generate",
            json=body,
            timeout=self._timeout,
        ) as response:
            response.raise_for_status()
            content = ""
            prompt_tokens = 0
            completion_tokens = 0
            deadline = time.monotonic() + self._timeout
            for line in response.iter_lines():
                if time.monotonic() > deadline:
                    raise httpx.ReadTimeout("llm_timeout")
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
            "max_tokens": 48,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": wrap_untrusted(request.user_payload)},
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        response = self._client.post(
            f"{self._base_url}/chat/completions",
            json=body,
            headers=headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage") or {}
        return (
            str(data["choices"][0]["message"]["content"]),
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
        )

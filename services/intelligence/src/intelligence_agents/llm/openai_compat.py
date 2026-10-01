"""OpenAI-compatible chat completions client."""

from __future__ import annotations

from dataclasses import replace
import logging

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
        retries: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self._timeout = timeout
        self._retries = retries
        self._client = client or httpx.Client(timeout=timeout)

    def complete(self, request: LLMRequest, *, tier: str) -> object:
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": wrap_untrusted(request.user_payload)},
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                response = self._client.post(
                    f"{self._base_url}/chat/completions",
                    json=body,
                    headers=headers,
                    timeout=self._timeout,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage") or {}
                assessment = parse_assessment(content, model=self.model, tier=tier)
                return replace(
                    assessment,
                    prompt_tokens=int(usage.get("prompt_tokens") or assessment.prompt_tokens),
                    completion_tokens=int(usage.get("completion_tokens") or assessment.completion_tokens),
                )
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValidationError) as exc:
                last_error = exc
                logger.warning("llm_provider_failed", extra={"attempt": attempt, "model": self.model})
        raise last_error or RuntimeError("llm_failed")

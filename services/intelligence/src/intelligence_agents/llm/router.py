"""Fallback and two-tier routing. Never calls brokers."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Protocol
from urllib.parse import urlparse

from intelligence_agents.llm.cache import LLMCache
from intelligence_agents.llm.cost import CostTracker
from intelligence_agents.llm.fixture import FixtureLLMProvider
from intelligence_agents.llm.types import LLMAssessment, LLMRequest

logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    model: str

    def complete(self, request: LLMRequest, *, tier: str) -> LLMAssessment: ...


class FallbackProvider:
    def __init__(self, primary: LLMProvider, secondary: LLMProvider) -> None:
        self._primary = primary
        self._secondary = secondary
        self.fallbacks = 0
        self.model = primary.model
        self.last_failure_type: str | None = None
        self.last_generation: str | None = None
        self.quota_exhausted = False

    def complete(self, request: LLMRequest, *, tier: str) -> LLMAssessment:
        try:
            result = self._primary.complete(request, tier=tier)
            self.last_generation = "success"
            return result
        except Exception as exc:
            self.fallbacks += 1
            failure_type = getattr(exc, "failure_type", type(exc).__name__)
            self.last_failure_type = str(failure_type)
            if str(failure_type) == "quota_exhaustion":
                self.quota_exhausted = True
            logger.warning(
                "llm_fallback",
                extra={
                    "from": self._primary.model,
                    "to": self._secondary.model,
                    "failure_type": failure_type,
                    "agent": request.task,
                },
            )
            result = self._secondary.complete(request, tier=tier)
            self.last_generation = "fixture_fallback"
            return replace(result, fallback=True)


class LLMRouter:
    def __init__(
        self,
        tier1: LLMProvider,
        tier2: LLMProvider | None,
        tracker: CostTracker,
        *,
        tier2_enabled: bool,
        cache: LLMCache | None = None,
        use_cache: bool = False,
        provider_name: str = "fixture",
        host: str = "",
    ) -> None:
        self._tier1 = tier1
        self._tier2 = tier2
        self._tracker = tracker
        self._tier2_enabled = tier2_enabled
        self._cache = cache or LLMCache()
        self._use_cache = use_cache
        self.provider_name = provider_name
        self.host = host

    def assess(self, request: LLMRequest) -> LLMAssessment:
        tier = "tier1"
        provider = self._tier1
        if request.high_impact_hint and self._tier2_enabled and self._tier2 is not None:
            if self._tracker.can_spend(200, 200):
                tier = "tier2"
                provider = self._tier2
            else:
                logger.info("llm_budget_exhausted", extra={"tier": "tier2"})
        model = provider.model
        if self._use_cache:
            cached = self._cache.get(request.content_hash, model)
            if cached is not None:
                return cached
        assessment = provider.complete(request, tier=tier)
        self._tracker.record(assessment.prompt_tokens, assessment.completion_tokens)
        if request.high_impact_hint and assessment.high_impact and tier == "tier1":
            if self._tier2_enabled and self._tier2 is not None and self._tracker.can_spend(200, 200):
                try:
                    assessment = self._tier2.complete(request, tier="tier2")
                    self._tracker.record(assessment.prompt_tokens, assessment.completion_tokens)
                except Exception:
                    logger.warning("llm_tier2_failed")
        if self._use_cache:
            self._cache.put(request.content_hash, assessment.model, assessment)
        return assessment

    def health_snapshot(self) -> dict[str, object]:
        tier1 = self._tier1
        return {
            "provider": self.provider_name,
            "model": getattr(tier1, "model", "fixture"),
            "host": self.host,
            "last_generation": getattr(tier1, "last_generation", None),
            "fallback_count": getattr(tier1, "fallbacks", 0),
            "last_failure_type": getattr(tier1, "last_failure_type", None),
            "quota_exhausted": bool(getattr(tier1, "quota_exhausted", False)),
            "prompt_tokens": self._tracker.prompt_tokens,
            "completion_tokens": self._tracker.completion_tokens,
            "cost_usd": self._tracker.estimate(self._tracker.prompt_tokens, self._tracker.completion_tokens),
            "pricing_basis": self._tracker.pricing_basis,
        }


def provider_name_from_url(base_url: str) -> str:
    host = (urlparse(base_url).hostname or "").lower()
    if "groq.com" in host:
        return "groq"
    if "11434" in base_url or host in {"host.docker.internal", "127.0.0.1", "localhost"}:
        return "ollama"
    return "openai_compat"


def build_router(
    *,
    api_key: str,
    base_url: str,
    tier1_model: str,
    tier2_model: str,
    timeout: float,
    daily_budget_usd: float,
    tier2_enabled: bool,
    use_cache: bool,
    openai_client: object | None = None,
) -> LLMRouter:
    fixture = FixtureLLMProvider()
    tracker = CostTracker(daily_budget_usd=daily_budget_usd)
    if not api_key:
        fallback = FallbackProvider(fixture, fixture)
        logger.info("llm_router", extra={"llm_mode": "fixture", "llm_host": ""})
        return LLMRouter(
            fallback,
            fallback,
            tracker,
            tier2_enabled=False,
            use_cache=use_cache,
            provider_name="fixture",
            host="",
        )
    from intelligence_agents.llm.openai_compat import OpenAICompatibleProvider

    kwargs = {}
    if openai_client is not None:
        kwargs["client"] = openai_client
    name = provider_name_from_url(base_url)
    host = urlparse(base_url).hostname or ""
    logger.info("llm_router", extra={"llm_mode": "openai", "llm_host": host, "model": tier1_model, "provider": name})
    tier1 = OpenAICompatibleProvider(base_url, api_key, tier1_model or "tier1", timeout=timeout, **kwargs)
    tier2 = OpenAICompatibleProvider(base_url, api_key, tier2_model or "tier2", timeout=timeout, **kwargs)
    return LLMRouter(
        FallbackProvider(tier1, fixture),
        FallbackProvider(tier2, fixture),
        tracker,
        tier2_enabled=tier2_enabled,
        use_cache=use_cache,
        provider_name=name,
        host=host,
    )

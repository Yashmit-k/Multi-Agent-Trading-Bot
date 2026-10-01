"""Fallback and two-tier routing. Never calls brokers."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Protocol

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

    def complete(self, request: LLMRequest, *, tier: str) -> LLMAssessment:
        try:
            return self._primary.complete(request, tier=tier)
        except Exception:
            self.fallbacks += 1
            logger.warning("llm_fallback", extra={"from": self._primary.model, "to": self._secondary.model})
            result = self._secondary.complete(request, tier=tier)
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
    ) -> None:
        self._tier1 = tier1
        self._tier2 = tier2
        self._tracker = tracker
        self._tier2_enabled = tier2_enabled
        self._cache = cache or LLMCache()
        self._use_cache = use_cache

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
        return LLMRouter(fallback, fallback, tracker, tier2_enabled=False, use_cache=use_cache)
    from intelligence_agents.llm.openai_compat import OpenAICompatibleProvider

    kwargs = {}
    if openai_client is not None:
        kwargs["client"] = openai_client
    tier1 = OpenAICompatibleProvider(base_url, api_key, tier1_model or "tier1", timeout=timeout, **kwargs)
    tier2 = OpenAICompatibleProvider(base_url, api_key, tier2_model or "tier2", timeout=timeout, **kwargs)
    return LLMRouter(
        FallbackProvider(tier1, fixture),
        FallbackProvider(tier2, fixture),
        tracker,
        tier2_enabled=tier2_enabled,
        use_cache=use_cache,
    )

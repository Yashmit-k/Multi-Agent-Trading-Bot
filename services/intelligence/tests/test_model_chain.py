"""A chain of real models keeps LLM answers coming when the first model's free quota is used up."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from intelligence_agents.errors import LLMProviderError
from intelligence_agents.llm.router import ModelChain
from intelligence_agents.llm.types import LLMAssessment, LLMRequest

REQUEST = LLMRequest(content_hash="h", user_payload="Infosys raises guidance", task="news")
ANSWER = LLMAssessment(sentiment=0.5, impact=0.6, confidence=0.7, event_type="guidance", reason_codes=("guidance",), horizon="SWING", high_impact=False, model="", tier="tier1")


class Model:
    def __init__(self, name: str, failure: str | None = None) -> None:
        self.model = name
        self.failure = failure
        self.calls = 0

    def complete(self, request, *, tier):
        self.calls += 1
        if self.failure:
            raise LLMProviderError(self.failure, self.failure)
        return replace(ANSWER, model=self.model)


def test_the_next_model_answers_when_the_first_is_out_of_quota_and_the_first_is_paused() -> None:
    clock = {"now": datetime(2026, 10, 21, 4, 0, tzinfo=timezone.utc)}
    first, second = Model("lite", "quota_exhaustion"), Model("flash")
    chain = ModelChain([first, second], clock=lambda: clock["now"])
    assert chain.complete(REQUEST, tier="tier1").model == "flash"
    assert chain.complete(REQUEST, tier="tier1").model == "flash"
    assert first.calls == 1  # paused after its quota ran out
    clock["now"] += timedelta(hours=1, minutes=1)
    chain.complete(REQUEST, tier="tier1")
    assert first.calls == 2  # retried after the pause


def test_all_models_failing_raises_so_the_fixture_fallback_takes_over() -> None:
    chain = ModelChain([Model("a", "quota_exhaustion"), Model("b", "timeout")])
    with pytest.raises(LLMProviderError):
        chain.complete(REQUEST, tier="tier1")
    assert chain.last_generation == "failure"


def test_router_caches_a_backup_model_answer_under_its_own_key() -> None:
    from intelligence_agents.llm.cost import CostTracker
    from intelligence_agents.llm.router import FallbackProvider, LLMRouter
    from intelligence_agents.llm.fixture import FixtureLLMProvider

    first, second = Model("lite", "quota_exhaustion"), Model("flash")
    router = LLMRouter(FallbackProvider(ModelChain([first, second]), FixtureLLMProvider()), None, CostTracker(daily_budget_usd=0), tier2_enabled=False, use_cache=True)
    assert router.assess(REQUEST).model == "flash"
    router.assess(REQUEST)
    assert second.calls == 1  # the second identical request came from the cache


def test_gemini_daily_and_per_minute_limits_are_told_apart() -> None:
    from intelligence_agents.llm.openai_compat import rate_limit_error

    daily = rate_limit_error('{"error": {"details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quotaValue": "500"}]}, {"retryDelay": "50086s"}]}}')
    assert daily.failure_type == "quota_exhaustion" and daily.retry_after == 50086
    minute = rate_limit_error('{"error": {"message": "You exceeded your current quota", "details": [{"violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}, {"retryDelay": "21s"}]}}')
    assert minute.failure_type == "http_429" and minute.retry_after == 21


def test_a_rate_limited_model_is_paused_for_the_providers_retry_delay_only() -> None:
    class Limited(Model):
        def complete(self, request, *, tier):
            self.calls += 1
            raise LLMProviderError("http_429", "rate", retry_after=20)

    clock = {"now": datetime(2026, 10, 21, 4, 0, tzinfo=timezone.utc)}
    first, second = Limited("lite"), Model("flash")
    chain = ModelChain([first, second], clock=lambda: clock["now"])
    chain.complete(REQUEST, tier="tier1")
    clock["now"] += timedelta(seconds=10)
    chain.complete(REQUEST, tier="tier1")
    assert first.calls == 1
    clock["now"] += timedelta(seconds=15)
    chain.complete(REQUEST, tier="tier1")
    assert first.calls == 2

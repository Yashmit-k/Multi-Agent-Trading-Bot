import json

import httpx

from intelligence_agents.llm.cost import CostTracker
from intelligence_agents.llm.fixture import FixtureLLMProvider
from intelligence_agents.llm.openai_compat import OpenAICompatibleProvider
from intelligence_agents.llm.router import FallbackProvider, LLMRouter
from intelligence_agents.llm.types import LLMRequest


def _valid_llm_json() -> dict:
    return {
        "sentiment": 0.2,
        "impact": 0.3,
        "confidence": 0.4,
        "event_type": "earnings.beat",
        "reason_codes": ["operating_updates"],
        "horizon": "SWING",
        "high_impact": False,
    }


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(_valid_llm_json())}}], "usage": {"prompt_tokens": 5, "completion_tokens": 3}},
    )


def _request(key: str = "h") -> LLMRequest:
    return LLMRequest(key, "The company reported steady operating updates.", "news")


def test_requests_are_spaced_by_min_interval() -> None:
    now = {"t": 100.0}
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now["t"] += seconds

    provider = OpenAICompatibleProvider(
        "https://api.groq.com/openai/v1", "k", "m", retries=0,
        client=httpx.Client(transport=httpx.MockTransport(_ok)),
        sleeper=sleep, min_interval_seconds=2.5, clock=lambda: now["t"],
    )
    provider.complete(_request("a"), tier="tier1")
    now["t"] += 1.0
    provider.complete(_request("b"), tier="tier1")
    assert slept == [1.5]


def test_no_pacing_by_default() -> None:
    slept: list[float] = []
    provider = OpenAICompatibleProvider(
        "https://api.groq.com/openai/v1", "k", "m", retries=0,
        client=httpx.Client(transport=httpx.MockTransport(_ok)), sleeper=slept.append,
    )
    provider.complete(_request("a"), tier="tier1")
    provider.complete(_request("b"), tier="tier1")
    assert slept == []


def test_cache_reuses_real_answers_but_not_fallbacks() -> None:
    calls = {"n": 0, "fail": True}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["fail"]:
            return httpx.Response(429, json={"error": "rate"})
        return _ok(request)

    primary = OpenAICompatibleProvider(
        "https://api.groq.com/openai/v1", "k", "m", retries=0,
        client=httpx.Client(transport=httpx.MockTransport(handler)), sleeper=lambda _: None,
    )
    fallback = FallbackProvider(primary, FixtureLLMProvider())
    router = LLMRouter(fallback, fallback, CostTracker(daily_budget_usd=0), tier2_enabled=False, use_cache=True)
    first = router.assess(_request())
    assert first.fallback is True
    calls["fail"] = False
    second = router.assess(_request())
    assert second.fallback is False
    third = router.assess(_request())
    assert third.fallback is False
    assert calls["n"] == 2


def test_json_mode_and_token_cap_reach_the_request() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return _ok(request)

    provider = OpenAICompatibleProvider(
        "https://api.groq.com/openai/v1", "k", "m", retries=0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_output_tokens=600, json_mode=True, reasoning_effort="low",
    )
    provider.complete(_request(), tier="tier1")
    assert seen[0]["max_tokens"] == 600
    assert seen[0]["response_format"] == {"type": "json_object"}
    assert seen[0]["reasoning_effort"] == "low"


def test_defaults_leave_the_request_unchanged() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return _ok(request)

    provider = OpenAICompatibleProvider(
        "https://api.groq.com/openai/v1", "k", "m", retries=0, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    provider.complete(_request(), tier="tier1")
    assert seen[0]["max_tokens"] == 160
    assert "response_format" not in seen[0]
    assert "reasoning_effort" not in seen[0]

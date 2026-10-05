"""Optional live-provider smoke. CI stays deterministic; set INTELLIGENCE_LIVE_LLM=1 to run."""

from __future__ import annotations

import os

import pytest

from intelligence_agents.llm.openai_compat import OpenAICompatibleProvider
from intelligence_agents.llm.types import LLMRequest

pytestmark = pytest.mark.live_llm


@pytest.mark.skipif(os.environ.get("INTELLIGENCE_LIVE_LLM") != "1", reason="optional live LLM")
def test_live_provider_returns_validated_assessment():
    base = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    key = os.environ.get("LLM_API_KEY", "ollama")
    model = os.environ.get("LLM_TIER1_MODEL", "phi3:mini")
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "90"))
    provider = OpenAICompatibleProvider(base, key, model, timeout=timeout, retries=0)
    result = provider.complete(
        LLMRequest("live", "The company reported steady operating updates.", "news"),
        tier="tier1",
    )
    assert result.reason_codes
    assert "fixture.heuristic" not in result.reason_codes
    assert result.prompt_tokens >= 0
    assert result.completion_tokens >= 0

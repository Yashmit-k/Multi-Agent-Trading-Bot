"""Optional bounded LLM notes on stored articles. Never a trading action."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from intelligence_agents.settings import IntelligenceSettings

logger = logging.getLogger(__name__)

_MAX_CHARS = 1500


def interpretation_unavailable(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "model_generated": False,
        "source_reported": True,
    }


def interpret_text(
    *,
    title: str,
    raw_text: str,
    url: str,
    settings: IntelligenceSettings,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    if not settings.news_interpret:
        return interpretation_unavailable("interpretation_disabled")
    if settings.llm_mode() != "openai":
        return interpretation_unavailable("no_llm_credentials")
    prompt = (
        "Summarize this financial news item in at most 40 words. "
        "Name the company if stated. Classify event_category as one of: "
        "earnings, regulation, product, management, market, other. "
        "Return JSON only with keys summary, company, event_category, relevance. "
        "relevance is high, medium, or low. Do not invent facts.\n\n"
        f"TITLE: {title}\nTEXT: {raw_text[:_MAX_CHARS]}"
    )
    endpoint = settings.llm_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.llm_tier1_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 220,
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    http = client or httpx.Client(timeout=min(20.0, settings.llm_timeout_seconds))
    try:
        response = http.post(endpoint, json=payload, headers=headers)
        if response.status_code >= 400:
            return interpretation_unavailable(f"llm_http_{response.status_code}")
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            return interpretation_unavailable("malformed_llm_json")
        return {
            "available": True,
            "reason": None,
            "model_generated": True,
            "source_reported": False,
            "summary": str(parsed.get("summary") or "")[:400],
            "company": parsed.get("company"),
            "event_category": str(parsed.get("event_category") or "other")[:40],
            "relevance": str(parsed.get("relevance") or "medium")[:16],
            "original_url": url,
        }
    except Exception as exc:
        logger.warning("news_interpret_failed", extra={"error": str(exc)[:200]})
        return interpretation_unavailable(f"llm_failure:{type(exc).__name__}")
    finally:
        if client is None:
            http.close()

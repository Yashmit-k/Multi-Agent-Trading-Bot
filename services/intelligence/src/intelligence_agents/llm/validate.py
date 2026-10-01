"""Validate LLM JSON into LLMAssessment."""

from __future__ import annotations

import json
import re
from typing import Any

from intelligence_agents.llm.types import LLMAssessment

_REASON = re.compile(r"^[a-z0-9_.]+$")


class ValidationError(ValueError):
    """Structured output failed schema checks."""


def parse_assessment(raw: str, *, model: str, tier: str, fallback: bool = False) -> LLMAssessment:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("invalid_json") from exc
    if not isinstance(payload, dict):
        raise ValidationError("not_object")
    sentiment = _clip(float(payload.get("sentiment", 0.0)), -1.0, 1.0)
    impact = _clip(float(payload.get("impact", 0.0)), 0.0, 1.0)
    confidence = _clip(float(payload.get("confidence", 0.0)), 0.0, 1.0)
    event_type = str(payload.get("event_type") or "unspecified")
    if not _REASON.fullmatch(event_type):
        event_type = "unspecified"
    codes_raw = payload.get("reason_codes") or ["llm.assessed"]
    if not isinstance(codes_raw, list) or not codes_raw:
        codes_raw = ["llm.assessed"]
    codes = tuple(str(code) for code in codes_raw if isinstance(code, str) and _REASON.fullmatch(code))
    if not codes:
        codes = ("llm.assessed",)
    horizon = str(payload.get("horizon") or "SWING")
    if horizon not in {"INTRADAY", "SWING", "LONG_TERM"}:
        horizon = "SWING"
    high_impact = bool(payload.get("high_impact", False))
    return LLMAssessment(
        sentiment=sentiment,
        impact=impact,
        confidence=confidence,
        event_type=event_type,
        reason_codes=codes,
        horizon=horizon,
        high_impact=high_impact,
        model=model,
        tier=tier,
        prompt_tokens=int(payload.get("prompt_tokens") or 0),
        completion_tokens=int(payload.get("completion_tokens") or 0),
        fallback=fallback,
    )


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def wrap_untrusted(text: str) -> str:
    cleaned = text.replace("<UNTRUSTED_ARTICLE>", " ").replace("</UNTRUSTED_ARTICLE>", " ")
    return f"<UNTRUSTED_ARTICLE>\n{cleaned}\n</UNTRUSTED_ARTICLE>"


def as_jsonable(assessment: LLMAssessment) -> dict[str, Any]:
    return {
        "sentiment": assessment.sentiment,
        "impact": assessment.impact,
        "confidence": assessment.confidence,
        "event_type": assessment.event_type,
        "reason_codes": list(assessment.reason_codes),
        "horizon": assessment.horizon,
        "high_impact": assessment.high_impact,
        "model": assessment.model,
        "tier": assessment.tier,
        "fallback": assessment.fallback,
    }

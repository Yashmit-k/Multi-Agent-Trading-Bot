"""Validate LLM JSON into LLMAssessment."""

from __future__ import annotations

import json
import re
from typing import Any

from intelligence_agents.llm.types import LLMAssessment

_REASON = re.compile(r"^[a-z0-9_.]+$")


class ValidationError(ValueError):
    """Structured output failed schema checks."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        if message == "invalid_json":
            self.failure_type = "malformed_json"
        elif message in {"unsupported_reason", "order_language"}:
            self.failure_type = message
        else:
            self.failure_type = "schema_failure"


_REQUIRED = ("sentiment", "impact", "confidence", "event_type", "reason_codes", "horizon", "high_impact")


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_object(raw: str) -> str:
    text = _strip_fences(raw)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _token(value: object) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def parse_assessment(raw: str, *, model: str, tier: str, fallback: bool = False) -> LLMAssessment:
    try:
        payload = json.loads(_extract_json_object(raw))
    except json.JSONDecodeError as exc:
        raise ValidationError("invalid_json") from exc
    if not isinstance(payload, dict):
        raise ValidationError("not_object")
    missing = [key for key in _REQUIRED if key not in payload]
    if missing:
        raise ValidationError(f"missing_keys:{','.join(missing)}")
    try:
        sentiment = float(payload["sentiment"])
        impact = float(payload["impact"])
        confidence = float(payload["confidence"])
    except (TypeError, ValueError) as exc:
        raise ValidationError("non_numeric_score") from exc
    if not -1.0 <= sentiment <= 1.0:
        raise ValidationError("sentiment_out_of_range")
    if not 0.0 <= impact <= 1.0:
        raise ValidationError("impact_out_of_range")
    if not 0.0 <= confidence <= 1.0:
        raise ValidationError("confidence_out_of_range")
    event_type = _token(payload["event_type"])
    if not event_type or not _REASON.fullmatch(event_type):
        raise ValidationError("invalid_event_type")
    codes_raw = payload["reason_codes"]
    if not isinstance(codes_raw, list) or not codes_raw:
        raise ValidationError("invalid_reason_codes")
    codes = tuple(_token(code) for code in codes_raw if str(code).strip())
    if not codes or any(not _REASON.fullmatch(code) for code in codes):
        raise ValidationError("invalid_reason_codes")
    horizon = payload["horizon"]
    if horizon not in {"INTRADAY", "SWING", "LONG_TERM"}:
        raise ValidationError("invalid_horizon")
    high_impact = payload["high_impact"]
    if not isinstance(high_impact, bool):
        raise ValidationError("invalid_high_impact")
    return LLMAssessment(
        sentiment=sentiment,
        impact=impact,
        confidence=confidence,
        event_type=event_type,
        reason_codes=codes,
        horizon=str(horizon),
        high_impact=high_impact,
        model=model,
        tier=tier,
        prompt_tokens=int(payload.get("prompt_tokens") or 0),
        completion_tokens=int(payload.get("completion_tokens") or 0),
        fallback=fallback,
    )


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

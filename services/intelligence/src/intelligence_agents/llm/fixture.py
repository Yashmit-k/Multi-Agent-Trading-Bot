"""Deterministic LLM for tests and BACKTEST. Ignores instruction-like lines."""

from __future__ import annotations

import json
import re

from intelligence_agents.llm.types import LLMAssessment, LLMRequest
from intelligence_agents.llm.validate import wrap_untrusted

_INSTRUCTION = re.compile(
    r"ignore (previous|all) instructions|set signal to|override system",
    re.IGNORECASE,
)
_POS = ("beat", "growth", "upgrade", "profit", "strong", "steady")
_NEG = ("miss", "fraud", "downgrade", "loss", "probe", "weak")


class FixtureLLMProvider:
    model = "fixture"

    def complete(self, request: LLMRequest, *, tier: str) -> LLMAssessment:
        text = request.user_payload
        data = text
        if "<UNTRUSTED_ARTICLE>" in text:
            data = text.split("<UNTRUSTED_ARTICLE>", 1)[-1].split("</UNTRUSTED_ARTICLE>", 1)[0]
        kept = [line for line in data.splitlines() if not _INSTRUCTION.search(line)]
        blob = " ".join(kept).lower()
        score = 0.0
        for word in _POS:
            if word in blob:
                score += 0.2
        for word in _NEG:
            if word in blob:
                score -= 0.2
        sentiment = max(-1.0, min(1.0, score))
        impact = min(0.4 + abs(sentiment) * 0.3, 1.0)
        payload = {
            "sentiment": sentiment,
            "impact": impact,
            "confidence": 0.4 + abs(sentiment) * 0.2,
            "event_type": "corporate.update",
            "reason_codes": ["fixture.heuristic"],
            "horizon": "SWING",
            "high_impact": impact >= 0.7 or request.high_impact_hint,
        }
        return LLMAssessment(
            sentiment=float(payload["sentiment"]),
            impact=float(payload["impact"]),
            confidence=float(payload["confidence"]),
            event_type=str(payload["event_type"]),
            reason_codes=tuple(payload["reason_codes"]),
            horizon=str(payload["horizon"]),
            high_impact=bool(payload["high_impact"]),
            model=self.model,
            tier=tier,
            prompt_tokens=len(blob.split()),
            completion_tokens=8,
            fallback=False,
        )

    def wrap(self, article_text: str) -> str:
        return wrap_untrusted(article_text)

    def dump(self, request: LLMRequest, tier: str) -> str:
        assessment = self.complete(request, tier=tier)
        return json.dumps(
            {
                "sentiment": assessment.sentiment,
                "impact": assessment.impact,
                "confidence": assessment.confidence,
                "event_type": assessment.event_type,
                "reason_codes": list(assessment.reason_codes),
                "horizon": assessment.horizon,
                "high_impact": assessment.high_impact,
            }
        )

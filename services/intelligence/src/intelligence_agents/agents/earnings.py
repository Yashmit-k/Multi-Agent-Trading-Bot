"""Earnings agent. Fundamentals + PIT news."""

from __future__ import annotations

from datetime import datetime

from contracts.enums import AgentName
from contracts.interfaces import AgentContext
from contracts.schemas.agent_signal import AgentSignal

from intelligence_agents.agents.base import BaseIntelligenceAgent
from intelligence_agents.agents.confidence import CAPS
from intelligence_agents.clock import Clock
from intelligence_agents.llm.router import LLMRouter
from intelligence_agents.llm.types import LLMRequest
from intelligence_agents.llm.validate import wrap_untrusted


class EarningsAgent(BaseIntelligenceAgent):
    agent_name = AgentName.EARNINGS
    confidence_cap = CAPS["earnings"]

    def __init__(self, clock: Clock, router: LLMRouter) -> None:
        super().__init__(clock)
        self._router = router

    def evaluate(self, symbol: str, as_of: datetime, context: AgentContext) -> AgentSignal:
        points = context.fundamental_provider.get_fundamentals(symbol, as_of)
        articles = context.news_provider.get_articles(symbol, as_of)
        payload = {
            "kind": "earnings",
            "points": [point.model_dump(mode="json") for point in points],
            "articles": [article.model_dump(mode="json") for article in articles],
        }
        if not points and not articles:
            return self._insufficient(symbol, as_of, context, payload)
        confidences = [0.4]
        score = 0.0
        eps_values = [point.value for point in points if point.metric == "eps"]
        if len(eps_values) >= 2:
            previous, latest = eps_values[-2], eps_values[-1]
            if previous != 0:
                growth = float((latest - previous) / abs(previous))
                score += max(-0.5, min(0.5, growth))
                confidences.append(0.5)
        if articles:
            request = LLMRequest(
                content_hash=articles[0].content_hash,
                user_payload=wrap_untrusted("\n".join(item.raw_text for item in articles)),
                task="earnings",
                high_impact_hint=True,
            )
            assessment = self._router.assess(request)
            score += 0.5 * assessment.sentiment
            confidences.append(assessment.confidence)
            payload["llm"] = {
                "sentiment": assessment.sentiment,
                "confidence": assessment.confidence,
                "fallback": assessment.fallback,
                "tier": assessment.tier,
            }
        return self._build(
            symbol=symbol,
            as_of=as_of,
            context=context,
            score=max(-1.0, min(1.0, score)),
            confidence=self._combine_confidence(confidences),
            reason_codes=("earnings.evaluated",),
            features={"point_count": len(points), "article_count": len(articles)},
            metadata={"eps_observations": len(eps_values)},
            payload=payload,
        )

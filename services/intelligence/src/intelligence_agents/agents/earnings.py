"""Earnings agent. Fundamentals + PIT news."""

from __future__ import annotations

from datetime import datetime

from contracts.enums import AgentName
from contracts.interfaces import AgentContext
from contracts.schemas.agent_signal import AgentSignal

from intelligence_agents.agents.base import BaseIntelligenceAgent
from intelligence_agents.fundamentals.provider import latest_by_metric
from intelligence_agents.agents.confidence import CAPS
from intelligence_agents.clock import Clock
from intelligence_agents.agents.interpret import interpret
from intelligence_agents.llm.router import LLMRouter
from intelligence_agents.llm.validate import as_jsonable
from intelligence_agents.news.quality import RESULTS_LOOKBACK, evidence_confidence, recent_news


class EarningsAgent(BaseIntelligenceAgent):
    agent_name = AgentName.EARNINGS
    confidence_cap = CAPS["earnings"]

    def __init__(self, clock: Clock, router: LLMRouter) -> None:
        super().__init__(clock)
        self._router = router

    def evaluate(self, symbol: str, as_of: datetime, context: AgentContext) -> AgentSignal:
        """Results coverage only: what the last 7 days of results news say about the quarter.

        Profit and revenue growth are the Fundamental agent's inputs; scoring them here too counted them twice.
        """
        recent = recent_news(context.news_provider.get_articles(symbol, as_of), as_of, RESULTS_LOOKBACK)
        articles = [item for item in recent if is_results_article(item)]
        points = context.fundamental_provider.get_fundamentals(symbol, as_of)
        payload = {
            "kind": "earnings",
            "points": [point.model_dump(mode="json") for point in points],
            "articles": [article.model_dump(mode="json") for article in articles],
        }
        if not articles:
            return self._insufficient(symbol, as_of, context, payload)
        latest = {metric: str(point.value) for metric, point in latest_by_metric(points).items() if metric in ("eps", "profit_growth", "revenue_growth", "margin")}
        body = "\n".join(f"{item.title}. {item.raw_text}" for item in articles)
        assessment = interpret(self._router, task="earnings", payload=f"reported metrics (context only)={latest}\n{body}", high_impact_hint=True)
        payload["llm"] = as_jsonable(assessment)
        score = assessment.sentiment * assessment.impact
        confidence = min(assessment.confidence, evidence_confidence(articles, as_of, self.confidence_cap))
        return self._build(
            symbol=symbol,
            as_of=as_of,
            context=context,
            score=max(-1.0, min(1.0, score)),
            confidence=confidence,
            reason_codes=assessment.reason_codes or ("earnings.evaluated",),
            features={"article_count": len(articles), "point_count": len(points)},
            metadata={"headlines": [{"title": item.title, "source": item.source, "published_at": item.published_at.isoformat()} for item in articles[:5]], "llm": payload["llm"]},
            payload=payload,
        )


_RESULTS_WORDS = ("result", "earnings", "net profit", "net income", "revenue", "q1 ", "q2 ", "q3 ", "q4 ", "quarterly", "quarter results", "eps", "guidance", "ebitda", "beats estimates", "misses estimates")


def is_results_article(article) -> bool:  # type: ignore[no-untyped-def]
    text = f"{getattr(article, 'title', '')} {getattr(article, 'raw_text', '')}".lower()
    return any(word in text for word in _RESULTS_WORDS)

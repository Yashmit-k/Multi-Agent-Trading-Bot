"""News TradingAgent."""

from __future__ import annotations

from datetime import datetime

from contracts.enums import AgentName
from contracts.fixtures import content_hash
from contracts.interfaces import AgentContext
from contracts.schemas.agent_signal import AgentSignal

from intelligence_agents.agents.base import BaseIntelligenceAgent
from intelligence_agents.agents.confidence import CAPS
from intelligence_agents.clock import Clock
from intelligence_agents.agents.interpret import interpret
from intelligence_agents.llm.router import LLMRouter
from intelligence_agents.llm.validate import as_jsonable
from intelligence_agents.news.quality import NEWS_LOOKBACK, evidence_confidence, recent_news


class NewsAgent(BaseIntelligenceAgent):
    agent_name = AgentName.NEWS
    confidence_cap = CAPS["news"]

    def __init__(self, clock: Clock, router: LLMRouter) -> None:
        super().__init__(clock)
        self._router = router

    def evaluate(self, symbol: str, as_of: datetime, context: AgentContext) -> AgentSignal:
        articles = recent_news(context.news_provider.get_articles(symbol, as_of), as_of)
        # Index-level headlines are stored under NIFTY50. They must not move a stock's News score.
        articles = [article for article in articles if "NIFTY50" not in {item.upper() for item in article.symbols}]
        payload = {
            "kind": "news",
            "articles": [article.model_dump(mode="json") for article in articles],
        }
        if not articles:
            return self._insufficient(symbol, as_of, context, payload)
        blob = "\n".join(f"{article.title}. {article.raw_text}" for article in articles)
        assessment = interpret(self._router, task="news", payload=blob)
        codes = tuple(dict.fromkeys(assessment.reason_codes))
        # Price commentary is not news: a story that only says "the stock moved" scores 0.
        price_only = set(codes) <= {"price_move"}
        score = 0.0 if price_only else assessment.sentiment * assessment.impact
        confidence = min(assessment.confidence, evidence_confidence(articles, as_of, self.confidence_cap))
        if price_only:
            confidence = min(confidence, 0.1)
        features = {"article_count": len(articles), "mean_sentiment": round(assessment.sentiment, 6), "price_only": price_only}
        metadata = {
            "llm": [as_jsonable(assessment)],
            "content_hash": content_hash("".join(article.content_hash for article in articles)),
            "headlines": [{"title": article.title, "source": article.source, "url": str(article.url), "published_at": article.published_at.isoformat()} for article in articles[:5]],
            "lookback_hours": int(NEWS_LOOKBACK.total_seconds() // 3600),
        }
        payload["llm"] = metadata["llm"]
        return self._build(
            symbol=symbol,
            as_of=as_of,
            context=context,
            score=max(-1.0, min(1.0, score)),
            confidence=confidence,
            reason_codes=codes or ("news.evaluated",),
            features=features,
            metadata=metadata,
            payload=payload,
        )

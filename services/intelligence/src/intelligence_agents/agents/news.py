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


class NewsAgent(BaseIntelligenceAgent):
    agent_name = AgentName.NEWS
    confidence_cap = CAPS["news"]

    def __init__(self, clock: Clock, router: LLMRouter) -> None:
        super().__init__(clock)
        self._router = router

    def evaluate(self, symbol: str, as_of: datetime, context: AgentContext) -> AgentSignal:
        articles = context.news_provider.get_articles(symbol, as_of)
        payload = {
            "kind": "news",
            "articles": [article.model_dump(mode="json") for article in articles],
        }
        if not articles:
            return self._insufficient(symbol, as_of, context, payload)
        blob = "\n".join(article.raw_text for article in articles)
        assessments = [interpret(self._router, task="news", payload=blob)]
        score = sum(item.sentiment * item.impact for item in assessments) / len(assessments)
        confidence = self._combine_confidence([item.confidence for item in assessments])
        features = {
            "article_count": len(articles),
            "mean_sentiment": round(sum(item.sentiment for item in assessments) / len(assessments), 6),
        }
        metadata = {
            "llm": [as_jsonable(item) for item in assessments],
            "content_hash": content_hash("".join(article.content_hash for article in articles)),
            "headlines": [{"title": article.title, "source": article.source, "url": str(article.url)} for article in articles[:5]],
        }
        payload["llm"] = metadata["llm"]
        return self._build(
            symbol=symbol,
            as_of=as_of,
            context=context,
            score=max(-1.0, min(1.0, score)),
            confidence=confidence,
            reason_codes=tuple(dict.fromkeys(code for item in assessments for code in item.reason_codes)),
            features=features,
            metadata=metadata,
            payload=payload,
        )

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


class EarningsAgent(BaseIntelligenceAgent):
    agent_name = AgentName.EARNINGS
    confidence_cap = CAPS["earnings"]

    def __init__(self, clock: Clock, router: LLMRouter) -> None:
        super().__init__(clock)
        self._router = router

    def evaluate(self, symbol: str, as_of: datetime, context: AgentContext) -> AgentSignal:
        points = context.fundamental_provider.get_fundamentals(symbol, as_of)
        # Only results coverage: general headlines are the News agent's job, and scoring them here counted them twice.
        articles = [item for item in context.news_provider.get_articles(symbol, as_of) if is_results_article(item)]
        payload = {
            "kind": "earnings",
            "points": [point.model_dump(mode="json") for point in points],
            "articles": [article.model_dump(mode="json") for article in articles],
        }
        latest = latest_by_metric(points)
        growth_point = latest.get("profit_growth")
        eps_values = [point.value for point in sorted(points, key=lambda item: (item.period, item.available_at)) if point.metric == "eps"]
        if growth_point is None and len(eps_values) < 2 and not articles:
            return self._insufficient(symbol, as_of, context, payload)
        confidences = [0.4]
        score = 0.0
        if growth_point is not None:
            # Year-on-year quarterly profit growth: +/-30% saturates at +/-0.5.
            score += max(-0.5, min(0.5, float(growth_point.value) / 0.6))
            confidences.append(0.5)
        elif len(eps_values) >= 2:
            previous, latest_eps = eps_values[-2], eps_values[-1]
            if previous != 0:
                growth = float((latest_eps - previous) / abs(previous))
                score += max(-0.5, min(0.5, growth))
                confidences.append(0.5)
        metrics = {point.metric: str(point.value) for point in points}
        if articles:
            body = "\n".join(item.raw_text for item in articles)
            assessment = interpret(
                self._router,
                task="earnings",
                payload=f"metrics={metrics}\n{body}",
                high_impact_hint=True,
            )
            score += 0.5 * assessment.sentiment
            confidences.append(assessment.confidence)
            payload["llm"] = as_jsonable(assessment)
            llm_codes = assessment.reason_codes
        else:
            llm_codes = ()
        return self._build(
            symbol=symbol,
            as_of=as_of,
            context=context,
            score=max(-1.0, min(1.0, score)),
            confidence=self._combine_confidence(confidences),
            reason_codes=llm_codes or ("earnings.evaluated",),
            features={"point_count": len(points), "article_count": len(articles)},
            metadata={"eps_observations": len(eps_values)},
            payload=payload,
        )


_RESULTS_WORDS = ("result", "earnings", "profit", "net income", "revenue", "q1", "q2", "q3", "q4", "quarter", "eps", "guidance", "margin")


def is_results_article(article) -> bool:  # type: ignore[no-untyped-def]
    text = f"{getattr(article, 'title', '')} {getattr(article, 'raw_text', '')}".lower()
    return any(word in text for word in _RESULTS_WORDS)

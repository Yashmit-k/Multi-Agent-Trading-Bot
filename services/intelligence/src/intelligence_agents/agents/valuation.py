"""Valuation agent. Price from MarketDataProvider, not FeatureSet."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from contracts.enums import AgentName
from contracts.interfaces import AgentContext
from contracts.schemas.agent_signal import AgentSignal

from intelligence_agents.agents.base import BaseIntelligenceAgent
from intelligence_agents.agents.confidence import CAPS
from intelligence_agents.agents.interpret import interpret
from intelligence_agents.clock import Clock
from intelligence_agents.llm.router import LLMRouter
from intelligence_agents.llm.validate import as_jsonable


class ValuationAgent(BaseIntelligenceAgent):
    agent_name = AgentName.VALUATION
    confidence_cap = CAPS["valuation"]

    def __init__(self, clock: Clock, router: LLMRouter) -> None:
        super().__init__(clock)
        self._router = router

    def evaluate(self, symbol: str, as_of: datetime, context: AgentContext) -> AgentSignal:
        points = context.fundamental_provider.get_fundamentals(symbol, as_of)
        quote = context.market_data_provider.get_quote(symbol, as_of)
        payload = {
            "kind": "valuation",
            "quote": quote.model_dump(mode="json"),
            "points": [point.model_dump(mode="json") for point in points],
        }
        eps_points = [point for point in points if point.metric == "eps"]
        if not eps_points:
            return self._insufficient(symbol, as_of, context, payload)
        eps = eps_points[-1].value
        if eps <= 0:
            return self._insufficient(symbol, as_of, context, payload)
        pe = Decimal(quote.last_price) / eps
        # Cheap vs rich around PE 20 as a bounded heuristic, not a trade.
        score = max(-1.0, min(1.0, float((Decimal("20") - pe) / Decimal("40"))))
        assessment = interpret(
            self._router,
            task="valuation",
            payload=(
                "Interpret this computed valuation. Do not invent price, EPS, or PE. "
                f"last_price={quote.last_price} eps={eps} implied_pe={pe} score={score:.4f}"
            ),
        )
        confidence = self._combine_confidence([0.48, assessment.confidence])
        payload["llm"] = as_jsonable(assessment)
        return self._build(
            symbol=symbol,
            as_of=as_of,
            context=context,
            score=score,
            confidence=confidence,
            reason_codes=assessment.reason_codes,
            features={"implied_pe": str(pe), "last_price": str(quote.last_price), "eps": str(eps)},
            metadata={"quote_timestamp": quote.timestamp.isoformat(), "llm": payload["llm"]},
            payload=payload,
        )

"""Valuation agent. Price from MarketDataProvider, not FeatureSet."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from contracts.enums import AgentName
from contracts.interfaces import AgentContext
from contracts.schemas.agent_signal import AgentSignal

from intelligence_agents.agents.base import BaseIntelligenceAgent
from intelligence_agents.fundamentals.provider import latest_by_metric
from intelligence_agents.errors import FixtureCoverageError
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
        try:
            quote = context.market_data_provider.get_quote(symbol, as_of)
        except (KeyError, LookupError) as exc:
            raise FixtureCoverageError(symbol) from exc
        payload = {
            "kind": "valuation",
            "quote": quote.model_dump(mode="json"),
            "points": [point.model_dump(mode="json") for point in points],
        }
        latest = latest_by_metric(points)
        if "eps" not in latest:
            return self._insufficient(symbol, as_of, context, payload)
        eps = latest["eps"].value  # trailing-twelve-month EPS in INR
        if eps <= 0:
            return self._insufficient(symbol, as_of, context, payload)
        pe = Decimal(quote.last_price) / eps
        peer = latest.get("peer_median_pe")
        if peer is not None and peer.value > 0:
            # Cheaper than sector peers -> positive, richer -> negative; 50% below/above the median saturates.
            anchor, base_confidence, basis = peer.value, 0.48, "sector_peers"
            score = max(-1.0, min(1.0, float((anchor - pe) / anchor) * 2))
        else:
            # No peer median: a market-wide P/E of 20, with lower confidence.
            anchor, base_confidence, basis = Decimal("20"), 0.3, "fixed_pe_20"
            score = max(-1.0, min(1.0, float((anchor - pe) / Decimal("40"))))
        assessment = interpret(
            self._router,
            task="valuation",
            payload=(
                "Interpret this computed valuation. Do not invent price, EPS, or PE. "
                f"last_price={quote.last_price} ttm_eps={eps} implied_pe={pe:.2f} comparison_pe={anchor} basis={basis} score={score:.4f}"
            ),
        )
        confidence = self._combine_confidence([base_confidence, assessment.confidence])
        payload["llm"] = as_jsonable(assessment)
        return self._build(
            symbol=symbol,
            as_of=as_of,
            context=context,
            score=score,
            confidence=confidence,
            reason_codes=assessment.reason_codes,
            features={"implied_pe": str(pe), "last_price": str(quote.last_price), "eps": str(eps), "comparison_pe": str(anchor)},
            metadata={"quote_timestamp": quote.timestamp.isoformat(), "pe_basis": basis, "eps_period": latest["eps"].period, "llm": payload["llm"]},
            payload=payload,
        )

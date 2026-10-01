"""Fundamental TradingAgent. Uses available_at-gated points only."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from contracts.enums import AgentName
from contracts.interfaces import AgentContext
from contracts.schemas.agent_signal import AgentSignal

from intelligence_agents.agents.base import BaseIntelligenceAgent
from intelligence_agents.agents.confidence import CAPS
from intelligence_agents.clock import Clock


class FundamentalAgent(BaseIntelligenceAgent):
    agent_name = AgentName.FUNDAMENTAL
    confidence_cap = CAPS["fundamental"]

    def __init__(self, clock: Clock) -> None:
        super().__init__(clock)

    def evaluate(self, symbol: str, as_of: datetime, context: AgentContext) -> AgentSignal:
        points = context.fundamental_provider.get_fundamentals(symbol, as_of)
        payload = {"kind": "fundamental", "points": [point.model_dump(mode="json") for point in points]}
        if not points:
            return self._insufficient(symbol, as_of, context, payload)
        latest_by_metric: dict[str, Decimal] = {}
        for point in sorted(points, key=lambda item: item.available_at):
            latest_by_metric[point.metric] = point.value
        eps = latest_by_metric.get("eps")
        score = 0.0
        if eps is not None:
            score = max(-1.0, min(1.0, float(eps) / 100.0))
        confidence = self._combine_confidence([0.45] * len(latest_by_metric))
        features = {f"metric_{key}": str(value) for key, value in latest_by_metric.items()}
        features["point_count"] = len(points)
        return self._build(
            symbol=symbol,
            as_of=as_of,
            context=context,
            score=score,
            confidence=confidence,
            reason_codes=("fundamental.evaluated",),
            features=features,
            metadata={"metrics": list(latest_by_metric)},
            payload=payload,
        )

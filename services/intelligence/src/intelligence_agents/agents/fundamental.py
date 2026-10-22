"""Fundamental TradingAgent. Uses available_at-gated points only."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from contracts.enums import AgentName
from contracts.interfaces import AgentContext
from contracts.schemas.agent_signal import AgentSignal

from intelligence_agents.agents.base import BaseIntelligenceAgent
from intelligence_agents.fundamentals.provider import latest_by_metric
from intelligence_agents.agents.confidence import CAPS
from intelligence_agents.agents.interpret import interpret
from intelligence_agents.clock import Clock
from intelligence_agents.llm.router import LLMRouter
from intelligence_agents.llm.validate import as_jsonable


class FundamentalAgent(BaseIntelligenceAgent):
    agent_name = AgentName.FUNDAMENTAL
    confidence_cap = CAPS["fundamental"]

    def __init__(self, clock: Clock, router: LLMRouter) -> None:
        super().__init__(clock)
        self._router = router

    def evaluate(self, symbol: str, as_of: datetime, context: AgentContext) -> AgentSignal:
        points = context.fundamental_provider.get_fundamentals(symbol, as_of)
        payload = {"kind": "fundamental", "points": [point.model_dump(mode="json") for point in points]}
        if not points:
            return self._insufficient(symbol, as_of, context, payload)
        latest = {metric: point.value for metric, point in latest_by_metric(points).items()}
        score, parts = fundamental_score(latest)
        if not parts:
            return self._insufficient(symbol, as_of, context, payload)  # nothing scorable (e.g. EPS only)
        metrics = {key: str(value) for key, value in latest.items()}
        assessment = interpret(
            self._router,
            task="fundamental",
            payload=("Interpret these computed metrics. Do not invent numbers. " f"metrics={metrics}"),
        )
        confidence = self._combine_confidence([0.45] * max(1, len(parts)) + [assessment.confidence])
        features = {f"metric_{key}": str(value) for key, value in latest.items()}
        features.update({f"part_{key}": round(value, 4) for key, value in parts.items()})
        features["point_count"] = len(points)
        payload["llm"] = as_jsonable(assessment)
        return self._build(
            symbol=symbol,
            as_of=as_of,
            context=context,
            score=score,
            confidence=confidence,
            reason_codes=assessment.reason_codes,
            features=features,
            metadata={"metrics": list(latest), "scored_on": list(parts), "llm": payload["llm"]},
            payload=payload,
        )


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def fundamental_score(latest: dict) -> tuple[float, dict[str, float]]:
    """Mean of the available parts, each in [-1, 1].

    Preferred: each stock's percentile rank against the rest of the NIFTY 50 (rank_* metrics from the
    nightly fetch), mapped to 2 x rank - 1, so the agent says which stocks are *relatively* strong instead of
    calling most large caps a buy. Fallback when ranks are missing: fixed thresholds on
    YoY profit growth (+25% saturates), YoY revenue growth (+15%), ROE around 12%, and debt-to-equity.
    """
    parts: dict[str, float] = {}
    for metric in ("profit_growth", "revenue_growth", "roe", "debt_to_equity"):
        rank = latest.get(f"rank_{metric}")
        if rank is not None:
            parts[metric] = _clamp(2 * float(rank) - 1)
    if parts:
        return _clamp(sum(parts.values()) / len(parts)), parts
    if "profit_growth" in latest:
        parts["profit_growth"] = _clamp(float(latest["profit_growth"]) / 0.25)
    if "revenue_growth" in latest:
        parts["revenue_growth"] = _clamp(float(latest["revenue_growth"]) / 0.15)
    if "roe" in latest:
        parts["roe"] = _clamp((float(latest["roe"]) - 0.12) / 0.12)
    if "debt_to_equity" in latest:
        parts["debt_to_equity"] = _clamp(1.0 - float(latest["debt_to_equity"]))
    if not parts:
        return 0.0, parts
    return _clamp(sum(parts.values()) / len(parts)), parts

"""Shared TradingAgent helpers."""

from __future__ import annotations

from datetime import datetime, timedelta

from contracts.enums import AgentName, Exchange, Horizon
from contracts.interfaces import AgentContext
from contracts.schemas.agent_signal import AgentSignal
from contracts.time import require_aware

from intelligence_agents.agents.confidence import INSUFFICIENT_CONFIDENCE, cap_and_rank_normalize
from intelligence_agents.clock import Clock
from intelligence_agents.signal_id import make_signal_id

AGENT_VERSION = "1.0.0"
DEFAULT_HORIZON = Horizon.SWING

VALIDITY = {
    AgentName.NEWS: timedelta(hours=6),
    AgentName.FUNDAMENTAL: timedelta(days=5),
    AgentName.VALUATION: timedelta(days=5),
    AgentName.EARNINGS: timedelta(days=7),
}


class BaseIntelligenceAgent:
    agent_name: AgentName
    confidence_cap: float

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def _horizon(self, context: AgentContext) -> Horizon:
        raw = context.configuration.get("horizon", DEFAULT_HORIZON.value)
        try:
            return Horizon(raw)
        except ValueError:
            return DEFAULT_HORIZON

    def _build(
        self,
        *,
        symbol: str,
        as_of: datetime,
        context: AgentContext,
        score: float,
        confidence: float,
        reason_codes: tuple[str, ...],
        features: dict[str, str | int | float | bool],
        metadata: dict[str, object],
        payload: object,
    ) -> AgentSignal:
        aware = require_aware(as_of, "as_of")
        timestamp = self._clock.now()
        if timestamp < aware:
            timestamp = aware
        horizon = self._horizon(context)
        valid_until = timestamp + VALIDITY[self.agent_name]
        clipped = max(-1.0, min(1.0, score))
        capped = min(max(confidence, 0.0), self.confidence_cap)
        codes = reason_codes or (f"{self.agent_name.value}.evaluated",)
        return AgentSignal(
            signal_id=make_signal_id(self.agent_name, AGENT_VERSION, symbol, aware, horizon, payload),
            symbol=symbol,
            exchange=Exchange.NSE,
            agent_name=self.agent_name,
            agent_version=AGENT_VERSION,
            timestamp=timestamp,
            as_of=aware,
            horizon=horizon,
            signal=clipped,
            confidence=capped,
            valid_until=valid_until,
            reason_codes=list(codes),
            features=features,
            metadata=metadata,
        )

    def _insufficient(self, symbol: str, as_of: datetime, context: AgentContext, payload: object) -> AgentSignal:
        return self._build(
            symbol=symbol,
            as_of=as_of,
            context=context,
            score=0.0,
            confidence=INSUFFICIENT_CONFIDENCE,
            reason_codes=("insufficient_data",),
            features={"article_count": 0, "point_count": 0},
            metadata={"insufficient_data": True},
            payload=payload,
        )

    def _combine_confidence(self, values: list[float]) -> float:
        return cap_and_rank_normalize(values, self.confidence_cap)

"""Mean-reversion agent: price versus precomputed Bollinger bands."""

from __future__ import annotations

from typing import Mapping

from contracts.enums import AgentName

from quant_agents.base import AgentDecision, BaseQuantAgent
from quant_agents.feature_view import FeatureView
from quant_agents.vote import Vote

WEIGHTS = {
    "upper": 0.4,
    "lower": 0.4,
    "mid": 0.2,
}


class MeanReversionAgent(BaseQuantAgent):
    agent_name = AgentName.MEAN_REVERSION
    required_features = ("last_close", "bollinger_upper", "bollinger_lower", "bollinger_mid")
    optional_features = ("bollinger_pct_b", "distance_from_mean", "zscore_20", "reversion_half_life")

    def interpret(self, view: FeatureView, extra_views: Mapping[str, FeatureView]) -> AgentDecision:
        votes: list[Vote] = []
        close = view.get("last_close")
        upper = view.get("bollinger_upper")
        lower = view.get("bollinger_lower")
        mid = view.get("bollinger_mid")
        if close is not None and upper is not None:
            if close > upper:
                votes.append(Vote("upper", -1, WEIGHTS["upper"]))
            else:
                votes.append(Vote("upper", 0, WEIGHTS["upper"]))
        if close is not None and lower is not None:
            if close < lower:
                votes.append(Vote("lower", 1, WEIGHTS["lower"]))
            else:
                votes.append(Vote("lower", 0, WEIGHTS["lower"]))
        if close is not None and mid is not None:
            if close > mid:
                votes.append(Vote("mid", -1, WEIGHTS["mid"]))
            elif close < mid:
                votes.append(Vote("mid", 1, WEIGHTS["mid"]))
            else:
                votes.append(Vote("mid", 0, WEIGHTS["mid"]))
        return AgentDecision(votes=tuple(votes))

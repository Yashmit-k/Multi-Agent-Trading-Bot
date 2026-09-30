"""Momentum agent: signs of precomputed return and trend features."""

from __future__ import annotations

from typing import Mapping

from contracts.enums import AgentName

from quant_agents.base import AgentDecision, BaseQuantAgent
from quant_agents.feature_view import FeatureView
from quant_agents.vote import Vote

WEIGHTS = {
    "return_1": 0.35,
    "momentum_10": 0.35,
    "macd": 0.3,
}


class MomentumAgent(BaseQuantAgent):
    agent_name = AgentName.MOMENTUM
    required_features = ("return_1", "momentum_10", "macd")
    optional_features = ("roc_10", "trend_strength_adx", "relative_strength_nifty", "volume_confirmation")

    def interpret(self, view: FeatureView, extra_views: Mapping[str, FeatureView]) -> AgentDecision:
        votes: list[Vote] = []
        ret = view.get("return_1")
        if ret is not None:
            if ret > 0:
                votes.append(Vote("return_1", 1, WEIGHTS["return_1"]))
            elif ret < 0:
                votes.append(Vote("return_1", -1, WEIGHTS["return_1"]))
            else:
                votes.append(Vote("return_1", 0, WEIGHTS["return_1"]))
        mom = view.get("momentum_10")
        if mom is not None:
            if mom > 0:
                votes.append(Vote("momentum_10", 1, WEIGHTS["momentum_10"]))
            elif mom < 0:
                votes.append(Vote("momentum_10", -1, WEIGHTS["momentum_10"]))
            else:
                votes.append(Vote("momentum_10", 0, WEIGHTS["momentum_10"]))
        macd = view.get("macd")
        if macd is not None:
            if macd > 0:
                votes.append(Vote("macd", 1, WEIGHTS["macd"]))
            elif macd < 0:
                votes.append(Vote("macd", -1, WEIGHTS["macd"]))
            else:
                votes.append(Vote("macd", 0, WEIGHTS["macd"]))
        return AgentDecision(votes=tuple(votes))

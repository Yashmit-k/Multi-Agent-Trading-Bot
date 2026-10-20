"""Momentum agent: multi-bar return beyond noise, confirmed by trend strength and strength vs NIFTY.

Dropped: the sign of the last single bar (noise on 5-minute bars, 35% of the old weight) and MACD
(already a Technical vote). The return vote needs the 10-bar move to exceed half its expected noise
(feature roc_10_z, from the Feature Engine); otherwise the agent abstains on it.
"""

from __future__ import annotations

from typing import Mapping

from contracts.enums import AgentName

from quant_agents.base import AgentDecision, BaseQuantAgent
from quant_agents.feature_view import FeatureView
from quant_agents.vote import Vote

WEIGHTS = {"roc_10": 0.45, "trend_strength": 0.3, "relative_strength": 0.25}
NOISE_Z_UP = 0.5
NOISE_Z_DOWN = -0.5
ADX_TREND = 20.0


class MomentumAgent(BaseQuantAgent):
    agent_name = AgentName.MOMENTUM
    required_features = ("roc_10_z",)
    optional_features = ("trend_strength_adx", "relative_strength_nifty")

    def interpret(self, view: FeatureView, extra_views: Mapping[str, FeatureView]) -> AgentDecision:
        votes: list[Vote] = []
        z = view.get("roc_10_z")
        direction = 0
        if z is not None:
            direction = 1 if z > NOISE_Z_UP else -1 if z < NOISE_Z_DOWN else 0
            votes.append(Vote("roc_10", direction, WEIGHTS["roc_10"]))
        adx = view.get("trend_strength_adx")
        if adx is not None:
            # A strong trend confirms the move's direction; a weak one abstains.
            votes.append(Vote("trend_strength", direction if adx >= ADX_TREND else 0, WEIGHTS["trend_strength"]))
        relative = view.get("relative_strength_nifty")
        if relative is not None:
            votes.append(Vote("relative_strength", 1 if relative > 0 else -1 if relative < 0 else 0, WEIGHTS["relative_strength"]))
        return AgentDecision(votes=tuple(votes))

"""Volume agent: relative volume as last_volume versus volume_mean."""

from __future__ import annotations

from typing import Mapping

from contracts.enums import AgentName

from quant_agents.base import AgentDecision, BaseQuantAgent
from quant_agents.feature_view import FeatureView
from quant_agents.vote import Vote

WEIGHTS = {
    "volume_price": 1.0,
}


class VolumeAgent(BaseQuantAgent):
    agent_name = AgentName.VOLUME
    required_features = ("last_volume", "volume_mean", "return_1")
    optional_features = ("relative_volume", "volume_acceleration", "volume_imbalance", "price_volume_corr")

    def interpret(self, view: FeatureView, extra_views: Mapping[str, FeatureView]) -> AgentDecision:
        votes: list[Vote] = []
        last_volume = view.get("last_volume")
        volume_mean = view.get("volume_mean")
        ret = view.get("return_1")
        if last_volume is not None and volume_mean is not None and ret is not None:
            heavy = last_volume > volume_mean
            if heavy and ret > 0:
                votes.append(Vote("volume_price", 1, WEIGHTS["volume_price"]))
            elif heavy and ret < 0:
                votes.append(Vote("volume_price", -1, WEIGHTS["volume_price"]))
            else:
                votes.append(Vote("volume_price", 0, WEIGHTS["volume_price"]))
        return AgentDecision(votes=tuple(votes))

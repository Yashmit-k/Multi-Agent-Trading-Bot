"""Volume agent: relative volume as last_volume versus volume_mean."""

from __future__ import annotations

from typing import Mapping

from contracts.enums import AgentName, Horizon

from quant_agents.base import AgentDecision, BaseQuantAgent
from quant_agents.feature_view import FeatureView
from quant_agents.vote import Vote

WEIGHTS = {
    "volume_price": 1.0,
    "volume_surge": 1.0,
    "volume_extreme": 1.0,
    "volume_conviction": 1.0,
}

# Thresholds on Feature Engine ratios. Graded votes keep one heavy day from reading as full confidence:
# the scorer sets confidence to |weighted vote mean|, so a single vote could only ever be 0 or 1.
SURGE = 2.0
INTRADAY_SURGE = 3.0
EXTREME = 3.0
CONVICTION_CORR = 0.3


class VolumeAgent(BaseQuantAgent):
    agent_name = AgentName.VOLUME
    required_features = ("last_volume", "volume_mean", "return_1")
    optional_features = ("relative_volume", "volume_acceleration", "volume_imbalance", "price_volume_corr")

    def interpret(self, view: FeatureView, extra_views: Mapping[str, FeatureView]) -> AgentDecision:
        votes: list[Vote] = []
        last_volume = view.get("last_volume")
        volume_mean = view.get("volume_mean")
        ret = view.get("return_1")
        if last_volume is None or volume_mean is None or ret is None:
            return AgentDecision(votes=tuple(votes))
        intraday = getattr(self, "horizon", None) is Horizon.INTRADAY
        # INTRADAY (1.4.0, pre-registered tuning study): heavy-volume moves reverse within the hour, so the vote
        # goes against the bar's direction and needs a 3x surge. Validated IC +0.005 on Jul-Dec 2025.
        if intraday:
            direction = -1 if ret > 0 else 1 if ret < 0 else 0
        else:
            direction = 1 if ret > 0 else -1 if ret < 0 else 0
        heavy = last_volume > volume_mean
        votes.append(Vote("volume_price", direction if heavy else 0, WEIGHTS["volume_price"]))
        relative = view.get("relative_volume")
        if relative is not None:
            surge = INTRADAY_SURGE if intraday else SURGE
            votes.append(Vote("volume_surge", direction if relative > surge else 0, WEIGHTS["volume_surge"]))
            votes.append(Vote("volume_extreme", direction if relative > EXTREME else 0, WEIGHTS["volume_extreme"]))
        correlation = view.get("price_volume_corr")
        if correlation is not None:
            votes.append(Vote("volume_conviction", direction if heavy and correlation > CONVICTION_CORR else 0, WEIGHTS["volume_conviction"]))
        return AgentDecision(votes=tuple(votes))

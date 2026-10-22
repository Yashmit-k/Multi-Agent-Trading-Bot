"""Technical agent: comparisons of precomputed trend and oscillator features."""

from __future__ import annotations

from typing import Mapping

from contracts.enums import AgentName

from quant_agents.base import AgentDecision, BaseQuantAgent
from quant_agents.feature_view import FeatureView
from quant_agents.vote import Vote

WEIGHTS = {
    "ema_trend": 0.15,
    "sma_trend": 0.15,
    "price_sma": 0.15,
    "price_vwap": 0.2,
    "rsi": 0.15,
    "macd": 0.2,
}
# A comparison votes only when the gap is meaningful relative to ATR (Feature Engine *_atr features);
# smaller gaps abstain, so a 0.01% EMA gap no longer counts the same as a 5% one.
GAPS = {
    "ema_trend": ("ema_gap_atr", (-0.1, 0.1), "ema_12", "ema_26"),
    "sma_trend": ("sma_gap_atr", (-0.1, 0.1), "sma_10", "sma_20"),
    "price_sma": ("close_sma20_atr", (-0.25, 0.25), "last_close", "sma_20"),
    "price_vwap": ("close_vwap_atr", (-0.25, 0.25), "last_close", "vwap"),
    "macd": ("macd_gap_atr", (-0.02, 0.02), "macd", "macd_signal"),
}


class TechnicalAgent(BaseQuantAgent):
    agent_name = AgentName.TECHNICAL
    required_features = ("ema_12", "ema_26", "sma_10", "sma_20", "last_close", "vwap", "rsi_14", "macd", "macd_signal")
    optional_features = ("ema_gap_atr", "sma_gap_atr", "close_sma20_atr", "close_vwap_atr", "macd_gap_atr", "support_level", "resistance_level", "trend_slope")

    def interpret(self, view: FeatureView, extra_views: Mapping[str, FeatureView]) -> AgentDecision:
        votes: list[Vote] = []
        for name, (gap_name, (low, high), a_name, b_name) in GAPS.items():
            gap = view.get(gap_name)
            if gap is not None:
                votes.append(Vote(name, 1 if gap > high else -1 if gap < low else 0, WEIGHTS[name]))
                continue
            a, b = view.get(a_name), view.get(b_name)  # no ATR yet: plain side-of comparison
            if a is not None and b is not None:
                votes.append(Vote(name, 1 if a > b else -1 if a < b else 0, WEIGHTS[name]))
        rsi = view.get("rsi_14")
        if rsi is not None:
            votes.append(Vote("rsi", 1 if rsi < 30 else -1 if rsi > 70 else 0, WEIGHTS["rsi"]))
        return AgentDecision(votes=tuple(votes))

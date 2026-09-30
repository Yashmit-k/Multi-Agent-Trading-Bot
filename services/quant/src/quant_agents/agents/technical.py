"""Technical agent: comparisons of precomputed trend and oscillator features."""

from __future__ import annotations

from typing import Mapping

from contracts.enums import AgentName

from quant_agents.base import AgentDecision, BaseQuantAgent
from quant_agents.feature_view import FeatureView
from quant_agents.vote import Vote

WEIGHTS = {
    "ema_trend": 0.2,
    "sma_trend": 0.2,
    "price_sma": 0.15,
    "price_vwap": 0.15,
    "rsi": 0.15,
    "macd": 0.15,
}


class TechnicalAgent(BaseQuantAgent):
    agent_name = AgentName.TECHNICAL
    required_features = ("ema_12", "ema_26", "sma_10", "sma_20", "last_close", "vwap", "rsi_14", "macd", "macd_signal")
    optional_features = ("support_level", "resistance_level", "trend_slope")

    def interpret(self, view: FeatureView, extra_views: Mapping[str, FeatureView]) -> AgentDecision:
        votes: list[Vote] = []
        ema_12 = view.get("ema_12")
        ema_26 = view.get("ema_26")
        if ema_12 is not None and ema_26 is not None:
            if ema_12 > ema_26:
                votes.append(Vote("ema_trend", 1, WEIGHTS["ema_trend"]))
            elif ema_12 < ema_26:
                votes.append(Vote("ema_trend", -1, WEIGHTS["ema_trend"]))
            else:
                votes.append(Vote("ema_trend", 0, WEIGHTS["ema_trend"]))
        sma_10 = view.get("sma_10")
        sma_20 = view.get("sma_20")
        if sma_10 is not None and sma_20 is not None:
            if sma_10 > sma_20:
                votes.append(Vote("sma_trend", 1, WEIGHTS["sma_trend"]))
            elif sma_10 < sma_20:
                votes.append(Vote("sma_trend", -1, WEIGHTS["sma_trend"]))
            else:
                votes.append(Vote("sma_trend", 0, WEIGHTS["sma_trend"]))
        last_close = view.get("last_close")
        sma_20_v = view.get("sma_20")
        if last_close is not None and sma_20_v is not None:
            if last_close > sma_20_v:
                votes.append(Vote("price_sma", 1, WEIGHTS["price_sma"]))
            elif last_close < sma_20_v:
                votes.append(Vote("price_sma", -1, WEIGHTS["price_sma"]))
            else:
                votes.append(Vote("price_sma", 0, WEIGHTS["price_sma"]))
        vwap = view.get("vwap")
        if last_close is not None and vwap is not None:
            if last_close > vwap:
                votes.append(Vote("price_vwap", 1, WEIGHTS["price_vwap"]))
            elif last_close < vwap:
                votes.append(Vote("price_vwap", -1, WEIGHTS["price_vwap"]))
            else:
                votes.append(Vote("price_vwap", 0, WEIGHTS["price_vwap"]))
        rsi = view.get("rsi_14")
        if rsi is not None:
            if rsi < 30:
                votes.append(Vote("rsi", 1, WEIGHTS["rsi"]))
            elif rsi > 70:
                votes.append(Vote("rsi", -1, WEIGHTS["rsi"]))
            else:
                votes.append(Vote("rsi", 0, WEIGHTS["rsi"]))
        macd = view.get("macd")
        macd_signal = view.get("macd_signal")
        if macd is not None and macd_signal is not None:
            if macd > macd_signal:
                votes.append(Vote("macd", 1, WEIGHTS["macd"]))
            elif macd < macd_signal:
                votes.append(Vote("macd", -1, WEIGHTS["macd"]))
            else:
                votes.append(Vote("macd", 0, WEIGHTS["macd"]))
        return AgentDecision(votes=tuple(votes))

"""Regime agent: labels from comparisons. Volatility and risk need reference features."""

from __future__ import annotations

from typing import Mapping

from contracts.enums import AgentName

from quant_agents.base import AgentDecision, BaseQuantAgent
from quant_agents.feature_view import FeatureView
from quant_agents.vote import Vote

WEIGHTS = {
    "risk_tilt": 1.0,
    "index_trend": 1.0,
    "fear_gauge": 1.0,
}


class RegimeAgent(BaseQuantAgent):
    agent_name = AgentName.REGIME
    required_features = ("ema_12", "ema_26", "sma_10", "sma_20")
    optional_features = ("trend_strength_adx", "volatility_percentile")
    uses_index_features = True

    def interpret(self, view: FeatureView, extra_views: Mapping[str, FeatureView]) -> AgentDecision:
        regimes: list[str] = []
        evidence: dict[str, str | float | bool] = {}
        reasons: list[str] = []
        ema_12 = view.get("ema_12")
        ema_26 = view.get("ema_26")
        sma_10 = view.get("sma_10")
        sma_20 = view.get("sma_20")
        trending = False
        if ema_12 is not None and ema_26 is not None and sma_10 is not None and sma_20 is not None:
            if ema_12 > ema_26 and sma_10 > sma_20:
                trending = True
            elif ema_12 < ema_26 and sma_10 < sma_20:
                trending = True
        if trending:
            regimes.append("TRENDING")
            reasons.append("regime.trending")
        else:
            regimes.append("RANGING")
            reasons.append("regime.ranging")
        percentile = view.get("volatility_percentile")
        if percentile is None:
            reasons.append("regime.volatility_reference_missing")
        else:
            evidence["volatility_percentile"] = percentile
            if percentile > 80:
                regimes.append("HIGH_VOLATILITY")
                reasons.append("regime.high_volatility")
            elif percentile < 20:
                regimes.append("LOW_VOLATILITY")
                reasons.append("regime.low_volatility")
        nifty = extra_views.get("NIFTY50")
        vix = extra_views.get("INDIAVIX")
        votes: list[Vote] = []
        if nifty is None or vix is None:
            reasons.append("regime.index_features_missing")
        else:
            nifty_ret = nifty.get("return_1")
            if nifty_ret is not None:
                evidence["nifty_return_1"] = nifty_ret
                if nifty_ret > 0:
                    regimes.append("RISK_ON")
                    reasons.append("regime.risk_on")
                    votes.append(Vote("risk_tilt", 1, WEIGHTS["risk_tilt"]))
                elif nifty_ret < 0:
                    regimes.append("RISK_OFF")
                    reasons.append("regime.risk_off")
                    votes.append(Vote("risk_tilt", -1, WEIGHTS["risk_tilt"]))
                else:
                    votes.append(Vote("risk_tilt", 0, WEIGHTS["risk_tilt"]))
            # Graded with two more index facts, so one daily move is not full confidence.
            nifty_fast, nifty_slow = nifty.get("ema_12"), nifty.get("ema_26")
            if nifty_fast is not None and nifty_slow is not None:
                trend = 1 if nifty_fast > nifty_slow else -1 if nifty_fast < nifty_slow else 0
                votes.append(Vote("index_trend", trend, WEIGHTS["index_trend"]))
                reasons.append("regime.index_uptrend" if trend > 0 else "regime.index_downtrend" if trend < 0 else "regime.index_flat")
            vix_ret = vix.get("return_1")
            if vix_ret is not None:
                evidence["vix_return_1"] = vix_ret
                fear = -1 if vix_ret > 0 else 1 if vix_ret < 0 else 0
                votes.append(Vote("fear_gauge", fear, WEIGHTS["fear_gauge"]))
                reasons.append("regime.fear_rising" if fear < 0 else "regime.fear_falling" if fear > 0 else "regime.fear_flat")
        if not votes:
            votes.append(Vote("risk_tilt", 0, WEIGHTS["risk_tilt"]))
        return AgentDecision(
            votes=tuple(votes),
            reason_codes=tuple(reasons),
            metadata={"regimes": regimes, "evidence": evidence},
        )

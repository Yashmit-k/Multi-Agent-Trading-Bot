"""Mean-reversion agent: fade only band extremes, and only when the trend is weak.

The old "price below the middle band, so buy" vote bet against every trend all day and graded below a
coin flip (47% over 10 days intraday). Now a vote needs a close outside a Bollinger band *and* a weak
trend (ADX under ADX_WEAK); in a strong trend the agent abstains (signal 0, confidence 0).

INTRADAY (1.4.0, pre-registered tuning study): the ADX gate is dropped, so band extremes are faded in
any trend (validated IC +0.006 on Jul-Dec 2025; the gated rule was weaker).
"""

from __future__ import annotations

from typing import Mapping

from contracts.enums import AgentName, Horizon

from quant_agents.base import AgentDecision, BaseQuantAgent
from quant_agents.feature_view import FeatureView
from quant_agents.vote import Vote

WEIGHTS = {"lower": 0.5, "upper": 0.5}
ADX_WEAK = 20.0


class MeanReversionAgent(BaseQuantAgent):
    agent_name = AgentName.MEAN_REVERSION
    required_features = ("last_close", "bollinger_upper", "bollinger_lower")
    optional_features = ("trend_strength_adx", "bollinger_pct_b", "zscore_20")

    def interpret(self, view: FeatureView, extra_views: Mapping[str, FeatureView]) -> AgentDecision:
        close = view.get("last_close")
        upper = view.get("bollinger_upper")
        lower = view.get("bollinger_lower")
        adx = view.get("trend_strength_adx")
        weak_trend = adx is None or adx < ADX_WEAK or getattr(self, "horizon", None) is Horizon.INTRADAY
        reasons = ["mean_reversion.weak_trend" if weak_trend else "mean_reversion.strong_trend_abstain"]
        votes: list[Vote] = []
        if close is not None and lower is not None:
            votes.append(Vote("lower", 1 if (weak_trend and close < lower) else 0, WEIGHTS["lower"]))
        if close is not None and upper is not None:
            votes.append(Vote("upper", -1 if (weak_trend and close > upper) else 0, WEIGHTS["upper"]))
        return AgentDecision(votes=tuple(votes), reason_codes=tuple(reasons))

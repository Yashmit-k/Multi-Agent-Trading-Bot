"""Agent logic 1.3.0: mean reversion fades extremes only in weak trends; momentum and technical ignore noise;
confidence is participation, not |signal|."""

from quant_agents.agents.mean_reversion import MeanReversionAgent
from quant_agents.agents.momentum import MomentumAgent
from quant_agents.agents.technical import TechnicalAgent
from quant_agents.scoring import score_votes
from quant_agents.vote import Vote


class _View:
    def __init__(self, **values: float) -> None:
        self._values = values

    def get(self, name: str):  # type: ignore[no-untyped-def]
        return self._values.get(name)


def _signal(agent, **values: float) -> float:  # type: ignore[no-untyped-def]
    decision = agent.interpret(_View(**values), {})
    return score_votes(decision.votes, required=(), missing=()).signal


def test_mean_reversion_abstains_inside_the_bands_and_in_strong_trends(clock, calendar) -> None:
    agent = MeanReversionAgent(clock, calendar)
    assert _signal(agent, last_close=99, bollinger_upper=105, bollinger_lower=95, trend_strength_adx=10) == 0  # inside: no view
    assert _signal(agent, last_close=94, bollinger_upper=105, bollinger_lower=95, trend_strength_adx=10) > 0  # below band, weak trend
    assert _signal(agent, last_close=94, bollinger_upper=105, bollinger_lower=95, trend_strength_adx=35) == 0  # strong trend: abstain
    assert _signal(agent, last_close=106, bollinger_upper=105, bollinger_lower=95, trend_strength_adx=10) < 0


def test_momentum_ignores_moves_inside_the_noise_band(clock, calendar) -> None:
    agent = MomentumAgent(clock, calendar)
    assert _signal(agent, roc_10_z=0.2, trend_strength_adx=30) == 0  # inside noise: neither return nor trend votes
    assert _signal(agent, roc_10_z=1.5, trend_strength_adx=30, relative_strength_nifty=0.01) == 1.0
    weak = _signal(agent, roc_10_z=1.5, trend_strength_adx=10, relative_strength_nifty=0.01)
    assert 0 < weak < 1.0  # weak trend: the trend vote abstains


def test_technical_dead_bands_use_atr_scaled_gaps(clock, calendar) -> None:
    agent = TechnicalAgent(clock, calendar)
    base = dict(ema_12=1, ema_26=1, sma_10=1, sma_20=1, last_close=1, vwap=1, rsi_14=50, macd=0, macd_signal=0)
    tiny = dict(base, ema_gap_atr=0.05, sma_gap_atr=0.05, close_sma20_atr=0.1, close_vwap_atr=0.1, macd_gap_atr=0.01)
    assert _signal(agent, **tiny) == 0  # every gap under its band: no direction
    strong = dict(base, ema_gap_atr=0.5, sma_gap_atr=0.5, close_sma20_atr=1.0, close_vwap_atr=1.0, macd_gap_atr=0.1)
    assert _signal(agent, **strong) > 0.8


def test_confidence_is_participation_not_signal_size() -> None:
    split = score_votes((Vote("a", 1, 1.0), Vote("b", -1, 1.0)), required=(), missing=())
    assert split.signal == 0 and split.confidence == 1.0  # both had a view; they disagree
    one = score_votes((Vote("a", 1, 1.0), Vote("b", 0, 3.0)), required=(), missing=())
    assert one.signal == 0.25 and one.confidence == 0.25  # only a quarter of the evidence took a position
    none = score_votes((Vote("a", 0, 1.0),), required=(), missing=())
    assert none.confidence == 0.0


def test_intraday_settings_from_the_tuning_study(clock, calendar) -> None:
    from contracts.enums import Horizon

    from quant_agents.agents.volume import VolumeAgent

    momentum = MomentumAgent(clock, calendar)
    momentum.horizon = Horizon.INTRADAY
    assert _signal(momentum, roc_10_z=1.5, trend_strength_adx=30, relative_strength_nifty=0.01) == -1.0  # reversal
    assert _signal(momentum, roc_10_z=0.8, trend_strength_adx=30) == 0  # inside the stricter z 1.0 band
    momentum.horizon = Horizon.SWING
    assert _signal(momentum, roc_10_z=1.5, trend_strength_adx=30, relative_strength_nifty=0.01) == 1.0  # trend-following
    reversion = MeanReversionAgent(clock, calendar)
    reversion.horizon = Horizon.INTRADAY
    assert _signal(reversion, last_close=94, bollinger_upper=105, bollinger_lower=95, trend_strength_adx=35) > 0  # no ADX gate
    volume = VolumeAgent(clock, calendar)
    volume.horizon = Horizon.INTRADAY
    assert _signal(volume, last_volume=5000, volume_mean=1000, return_1=0.01, relative_volume=4.0, price_volume_corr=0.5) < 0
    volume.horizon = Horizon.SWING
    assert _signal(volume, last_volume=5000, volume_mean=1000, return_1=0.01, relative_volume=4.0, price_volume_corr=0.5) > 0

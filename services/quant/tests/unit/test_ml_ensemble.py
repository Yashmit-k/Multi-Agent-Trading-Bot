from datetime import date, timedelta
from decimal import Decimal

import numpy as np

from quant_agents.research import ml_ensemble as me
from quant_agents.research.delivery_costs import delivery_buy, delivery_sell
from quant_agents.research.ml_rank import Panel


def _panel(days: int = 330, symbols=("HDFCBANK", "ICICIBANK", "INFY", "TCS", "ITC", "NTPC", "SBIN", "WIPRO", "MARUTI", "CIPLA", "TITAN", "LT", "BEL", "ONGC"), seed: int = 3):
    rng = np.random.default_rng(seed)
    n = len(symbols)
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(days)]
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, (days, n)), axis=0)
    open_ = close * (1 + rng.normal(0, 0.002, (days, n)))
    panel = Panel(dates, list(symbols), open_, np.maximum(open_, close) * 1.004, np.minimum(open_, close) * 0.996, close, rng.integers(1000, 9000, (days, n)).astype(float))
    context = {name: 100 * np.cumprod(1 + rng.normal(0, 0.008, days)) for name in ("NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY FMCG", "NIFTY ENERGY", "NIFTY AUTO", "NIFTY PHARMA", "NIFTY CONSR DURBL")}
    context["INDIA VIX"] = 12 + np.abs(np.cumsum(rng.normal(0, 0.3, days)))
    return panel, context


def test_float_costs_match_the_decimal_schedule() -> None:
    for notional in (19876.45, 19999.99, 15000.0, 18321.5, 12500.05, 19480.0):
        exact_buy = float(delivery_buy(Decimal(str(notional))).total)
        exact_sell = float(delivery_sell(Decimal(str(notional))).total)
        assert abs(me._charges(notional, buy=True) - exact_buy) < 0.011
        assert abs(me._charges(notional, buy=False) - exact_sell) < 0.011


def test_features_do_not_look_ahead() -> None:
    panel, context = _panel()
    base = me.build(panel, context)
    t = 280
    future = Panel(panel.dates, panel.symbols, panel.open.copy(), panel.high.copy(), panel.low.copy(), panel.close.copy(), panel.volume.copy())
    for array in (future.open, future.high, future.low, future.close, future.volume):
        array[t + 1 :] *= 2.5
    ctx = {key: value.copy() for key, value in context.items()}
    for value in ctx.values():
        value[t + 1 :] *= 2.5
    altered = me.build(future, ctx)
    np.testing.assert_allclose(base.stock[: t + 1], altered.stock[: t + 1], equal_nan=True)
    np.testing.assert_allclose(base.market[: t + 1], altered.market[: t + 1], equal_nan=True)
    assert (base.nifty_trend_up[: t + 1] == altered.nifty_trend_up[: t + 1]).all()


def test_labels_align_with_execution() -> None:
    panel, _ = _panel()
    excess, fwd = me.labels(panel, 10)
    assert np.isclose(fwd[50, 2], panel.open[61, 2] / panel.open[51, 2] - 1)
    assert np.isclose(np.nanmean(excess[50]), 0.0)


def test_walk_forward_respects_the_embargo() -> None:
    panel, context = _panel()
    features = me.build(panel, context)
    excess, _ = me.labels(panel, 5)
    seen = []

    class Spy:
        def fit(self, x, y):
            seen.append(len(y))

        def predict(self, x):
            return np.zeros(len(x))

    original = me.make_selector
    me.make_selector = lambda name: Spy()
    try:
        t = 300
        me.walk_forward(features, excess, np.full(len(panel.dates), np.nan), 5, t, t)
    finally:
        me.make_selector = original
    cutoff = t - 5 - 6
    assert seen and max(seen) <= (cutoff + 1 - me.FEATURE_START) * len(panel.symbols)


def test_daily_series_spreads_a_window_over_its_sessions() -> None:
    series = me.daily_series([(10, 0.05, 0.01, True)], 5, 30)
    assert np.isclose(series.sum(), 0.05)
    assert np.isclose(series[11:16].sum(), 0.05)
    excess = me.daily_series([(10, 0.05, 0.01, True)], 5, 30, excess=True)
    assert np.isclose(excess.sum(), 0.04)


def test_reality_check_flags_noise_and_finds_a_real_edge() -> None:
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 0.01, (20, 400))
    p_noise, _ = me.reality_check(noise, resamples=300)
    assert p_noise > 0.1
    edge = noise.copy()
    edge[7] += 0.004
    p_edge, best = me.reality_check(edge, resamples=300)
    assert best == 7 and p_edge < 0.05


def test_sector_map_names_real_constituents() -> None:
    assert set(me.SECTOR_OF.values()) - {None} <= {"NIFTY BANK", "NIFTY FIN SERVICE", "NIFTY IT", "NIFTY AUTO", "NIFTY FMCG", "NIFTY METAL", "NIFTY PHARMA", "NIFTY ENERGY", "NIFTY CONSR DURBL", "NIFTY REALTY"}


def test_real_models_fit_while_a_feature_is_still_empty() -> None:
    panel, context = _panel()
    features = me.build(panel, context)
    excess, _ = me.labels(panel, 5)
    t = 200  # cutoff 189 < 250, so dist_high_250 has no value yet
    preds, _ = me.walk_forward(features, excess, np.full(len(panel.dates), np.nan), 5, t, t)
    for name in me.BASE_SELECTORS:
        assert np.isfinite(preds[name][t]).sum() > 0

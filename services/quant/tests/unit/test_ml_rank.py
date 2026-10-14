from datetime import date, timedelta

import numpy as np

from quant_agents.research import ml_rank


def _panel(days: int = 260, symbols: int = 14, seed: int = 1) -> ml_rank.Panel:
    rng = np.random.default_rng(seed)
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(days)]
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, (days, symbols)), axis=0)
    open_ = close * (1 + rng.normal(0, 0.002, (days, symbols)))
    high = np.maximum(open_, close) * 1.005
    low = np.minimum(open_, close) * 0.995
    volume = rng.integers(1000, 5000, (days, symbols)).astype(float)
    return ml_rank.Panel(dates, [f"S{j:02d}" for j in range(symbols)], open_, high, low, close, volume)


def test_features_do_not_look_ahead() -> None:
    panel = _panel()
    X, _ = ml_rank.build_features(panel)
    t = 150
    altered = ml_rank.Panel(panel.dates, panel.symbols, panel.open.copy(), panel.high.copy(), panel.low.copy(), panel.close.copy(), panel.volume.copy())
    for array in (altered.open, altered.high, altered.low, altered.close, altered.volume):
        array[t + 1 :] *= 3.0
    X2, _ = ml_rank.build_features(altered)
    np.testing.assert_allclose(X[: t + 1], X2[: t + 1], equal_nan=True)


def test_label_is_next_open_to_open_after_hold() -> None:
    panel = _panel()
    fwd = ml_rank.forward_returns(panel)
    t = 40
    expected = panel.open[t + 1 + ml_rank.HOLD, 3] / panel.open[t + 1, 3] - 1
    assert np.isclose(fwd[t, 3], expected)
    assert np.isnan(fwd[-1]).all()
    excess = ml_rank.excess_labels(fwd)
    assert np.isclose(np.nanmean(excess[t]), 0.0)


def test_walk_forward_never_trains_on_unfinished_labels() -> None:
    panel = _panel()
    X, _ = ml_rank.build_features(panel)
    y = ml_rank.excess_labels(ml_rank.forward_returns(panel))
    seen = {}

    class Spy:
        def fit(self, x, target):
            seen["rows"] = len(target)

        def predict(self, x):
            return np.zeros(len(x))

    original = ml_rank.make_model
    ml_rank.make_model = lambda name: Spy()
    try:
        t = 200
        ml_rank.walk_forward_predictions(X, y, "A", t, t)
    finally:
        ml_rank.make_model = original
    cutoff = t - ml_rank.EMBARGO - (1 + ml_rank.HOLD)
    assert seen["rows"] <= (cutoff + 1) * len(panel.symbols)


def test_trade_pays_delivery_costs_and_slippage() -> None:
    trade = ml_rank.trade_for("S", 1000.0, 1000.0)
    assert trade is not None
    assert trade.quantity == 19
    assert trade.cost > 50  # STT 0.1% each side plus stamp and DP on ~Rs 19k
    assert trade.net_pnl < -trade.cost  # flat price still loses slippage and costs


def test_block_bootstrap_brackets_the_mean() -> None:
    values = [0.01, -0.005, 0.02, 0.0, 0.015, -0.01, 0.005, 0.01]
    lower, upper = ml_rank.block_bootstrap(values, resamples=500)
    assert lower < np.mean(values) < upper


def test_score_period_runs_on_synthetic_data() -> None:
    panel = _panel()
    X, names = ml_rank.build_features(panel)
    y = ml_rank.excess_labels(ml_rank.forward_returns(panel))
    rows = list(range(130, 240, ml_rank.HOLD))
    preds = ml_rank.walk_forward_predictions(X, y, "B", rows[0], rows[-1])
    result = ml_rank.score_period(panel, X, names, preds, rows, "synthetic")
    assert result.windows > 5
    assert set(result.passed) == {"excess_positive_with_lower_bound", "beats_momentum", "beats_random", "not_one_stock"}

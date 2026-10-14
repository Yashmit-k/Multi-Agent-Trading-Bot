import json
import math
from datetime import date, datetime, timedelta, timezone

import numpy as np

from quant_agents.research import ml_combined as mc
from quant_agents.research.ml_rank import Panel


def ensemble_panel(days: int = 330, seed: int = 3):
    symbols = ("HDFCBANK", "ICICIBANK", "INFY", "TCS", "ITC", "NTPC", "SBIN", "WIPRO", "MARUTI", "CIPLA", "TITAN", "LT", "BEL", "ONGC")
    rng = np.random.default_rng(seed)
    n = len(symbols)
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(days)]
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, (days, n)), axis=0)
    open_ = close * (1 + rng.normal(0, 0.002, (days, n)))
    panel = Panel(dates, list(symbols), open_, np.maximum(open_, close) * 1.004, np.minimum(open_, close) * 0.996, close,
                  rng.integers(1000, 9000, (days, n)).astype(float))
    names = ("NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY FMCG", "NIFTY ENERGY", "NIFTY AUTO", "NIFTY PHARMA", "NIFTY CONSR DURBL")
    context = {name: 100 * np.cumprod(1 + rng.normal(0, 0.008, days)) for name in names}
    context["INDIA VIX"] = 12 + np.abs(np.cumsum(rng.normal(0, 0.3, days)))
    return panel, context


def _bars(day: date, symbol: str, closes: list[float], volumes: list[float]):
    """5-minute bars from 09:15 IST; bar k ends at 09:20 + 5k minutes IST."""
    start = datetime(day.year, day.month, day.day, 3, 45, tzinfo=timezone.utc)
    rows = []
    prev = closes[0]
    for k, (c, v) in enumerate(zip(closes, volumes)):
        rows.append(json.dumps({
            "symbol": symbol, "open": prev, "high": max(prev, c), "low": min(prev, c), "close": c, "volume": v,
            "start": (start + timedelta(minutes=5 * k)).isoformat(), "end": (start + timedelta(minutes=5 * (k + 1))).isoformat(),
        }))
        prev = c
    return rows


def test_intraday_features_match_hand_computation() -> None:
    day = date(2025, 3, 3)
    closes = [100.0 + 0.1 * k for k in range(75)]  # 75 bars = 09:15..15:30
    volumes = [100.0] * 63 + [300.0] * 12  # last 12 bars = last hour
    out = mc.intraday_daily(_bars(day, "INFY", closes, volumes), ["INFY"], [day])
    first_hour_close = closes[11]  # bar 11 ends at 10:15 IST
    assert math.isclose(out["first_hour_ret"][0, 0], first_hour_close / closes[0] - 1)
    before_last = closes[62]  # bar 62 ends at 14:30 IST
    assert math.isclose(out["last_hour_ret"][0, 0], closes[-1] / before_last - 1)
    assert math.isclose(out["last_hour_vol_share"][0, 0], 3600 / (6300 + 3600))
    expected_rv = math.sqrt(sum(math.log(closes[k] / closes[k - 1]) ** 2 for k in range(1, 75)))
    assert math.isclose(out["intraday_rv"][0, 0], expected_rv)


def test_labels_are_forward_and_balanced() -> None:
    panel, _ = ensemble_panel()
    y = mc.direction_labels(panel)
    t = 50
    fwd = panel.open[t + 1 + mc.H] / panel.open[t + 1] - 1
    assert ((fwd > np.median(fwd)) == (y[t] == 1)).all()
    assert abs(np.nanmean(y[:200]) - 0.5) < 0.06
    assert np.isnan(y[-1]).all()
    v = mc.volatility_labels(panel)
    assert abs(np.nanmean(v[:200]) - 0.5) < 0.06


def test_design_has_no_look_ahead() -> None:
    panel, context = ensemble_panel()
    T, N = panel.close.shape
    intraday = {name: np.random.default_rng(1).normal(size=(T, N)) for name in mc.INTRADAY_NAMES}
    base = mc.build_design(panel, context, intraday)
    t = 280
    future = Panel(panel.dates, panel.symbols, panel.open.copy(), panel.high.copy(), panel.low.copy(), panel.close.copy(), panel.volume.copy())
    for array in (future.open, future.high, future.low, future.close, future.volume):
        array[t + 1 :] *= 2.0
    ctx = {key: value.copy() for key, value in context.items()}
    for value in ctx.values():
        value[t + 1 :] *= 2.0
    shifted = {name: values.copy() for name, values in intraday.items()}
    for values in shifted.values():
        values[t + 1 :] += 5.0
    altered = mc.build_design(future, ctx, shifted)
    # Calendar features depend on the calendar only; every other column must be unchanged up to t.
    np.testing.assert_allclose(base.X[: t + 1], altered.X[: t + 1], equal_nan=True)


def test_walk_forward_respects_the_embargo() -> None:
    panel, context = ensemble_panel()
    T, N = panel.close.shape
    design = mc.build_design(panel, context, {name: np.zeros((T, N)) for name in mc.INTRADAY_NAMES})
    y = mc.direction_labels(panel)
    seen = []

    class Spy:
        def fit(self, x, target):
            seen.append(len(target))

        def predict_proba(self, x):
            return np.tile([0.5, 0.5], (len(x), 1))

    original = mc.make_model
    mc.make_model = lambda: Spy()
    try:
        t = 300
        mc.walk_forward_proba(design.X, y, t, t)
    finally:
        mc.make_model = original
    cutoff = t - mc.EMBARGO - (1 + mc.H)
    assert seen and seen[0] <= (cutoff + 1 - 60) * N


def test_deflated_sharpe_behaves() -> None:
    rng = np.random.default_rng(0)
    trials = rng.normal(0, 0.1, 45)
    strong = rng.normal(0.02, 0.02, 60)
    weak = rng.normal(0.001, 0.02, 60)
    s = mc.deflated_sharpe(strong, trials, 48)
    w = mc.deflated_sharpe(weak, trials, 48)
    assert s["deflated_sharpe"] > 0.95 > w["deflated_sharpe"]
    assert w["deflated_sharpe"] <= w["probabilistic_sharpe"]
    one = mc.deflated_sharpe(weak, np.array([0.0]), 1)
    assert math.isclose(one["deflated_sharpe"], one["probabilistic_sharpe"])

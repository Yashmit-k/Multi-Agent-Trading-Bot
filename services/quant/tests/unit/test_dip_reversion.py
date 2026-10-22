"""Refined dip reversion: signal on a close, fill at the next open, exits, stops and corporate actions."""

from datetime import date

import numpy as np

from quant_agents.research import dip_reversion as dr

START = date(2020, 1, 1).toordinal()


def _series(closes: list[float], *, gap_at: int | None = None) -> dr.Series:
    c = np.array(closes, dtype=float)
    o = np.concatenate([[c[0]], c[:-1]])
    if gap_at is not None:
        o[gap_at] = c[gap_at - 1] * 0.5
    h, l = np.maximum(o, c) * 1.002, np.minimum(o, c) * 0.998
    dates = np.arange(START, START + len(c))
    ema = np.full(len(c), np.nan)
    ema[19] = c[:20].mean()
    for k in range(20, len(c)):
        ema[k] = (2 / 21) * c[k] + (19 / 21) * ema[k - 1]
    prev = np.concatenate([[np.nan], c[:-1]])
    return dr.Series(dates, o, h, l, c, np.concatenate([[np.nan], ema[:-1]]), np.abs(o / prev - 1) > dr.EVENT_GAP, {int(d): k for k, d in enumerate(dates)})


def _dip_then(recover: list[float]) -> list[float]:
    flat = [100.0] * 30
    dip = [98.0, 96.0, 94.0, 92.0]  # 3 lower closes, then a -2% day about 7% below the EMA
    return flat + dip + recover


def _data(stock: dr.Series) -> dict[str, dr.Series]:
    nifty = _series([100.0] * len(stock.close))
    return {"X": stock, "NIFTY50": nifty}


PERIOD = (date.fromordinal(START), date.fromordinal(START + 400))


def test_signal_fills_next_open_and_exits_at_the_ema() -> None:
    stock = _series(_dip_then([93.0, 97.0, 101.0, 104.0] + [104.0] * 10))
    row = dr.simulate(_data(stock), ["X"], dr.BASE, PERIOD)
    assert row["entries"] == 1 and row["closed"] == 1 and row["open_at_end"] == 0
    assert row["total"] > 0


def test_fixed_level_does_not_sell_below_cost_when_the_ema_falls() -> None:
    slide = [91.0, 90.0, 89.5, 89.0, 88.8] + [88.8] * 30 + [92.0, 95.0, 99.0, 103.0] + [103.0] * 5
    ema_rule = dr.simulate(_data(_series(_dip_then(slide))), ["X"], dr.Variant("ema", None, None, False, False), PERIOD)
    fixed_rule = dr.simulate(_data(_series(_dip_then(slide))), ["X"], dr.Variant("fixed", None, None, False, False), PERIOD)
    assert ema_rule["entries"] == fixed_rule["entries"] == 1
    assert fixed_rule["total"] > ema_rule["total"]


def test_time_stop_and_price_stop() -> None:
    sinking = [91.0 - 0.5 * j for j in range(40)]
    timed = dr.simulate(_data(_series(_dip_then(sinking))), ["X"], dr.Variant("ema", 15, None, False, False), PERIOD)
    stopped = dr.simulate(_data(_series(_dip_then(sinking))), ["X"], dr.Variant("ema", None, 0.10, False, False), PERIOD)
    held = dr.simulate(_data(_series(_dip_then(sinking))), ["X"], dr.Variant("ema", None, None, False, False), PERIOD)
    assert timed["closed"] == 1 and stopped["closed"] == 1 and held["open_at_end"] == 1
    assert held["total"] < stopped["total"] < 0


def test_a_corporate_action_gap_is_not_a_dip() -> None:
    closes = [100.0] * 30 + [50.0] * 30
    row = dr.simulate(_data(_series(closes, gap_at=30)), ["X"], dr.BASE, PERIOD)
    assert row["entries"] == 0

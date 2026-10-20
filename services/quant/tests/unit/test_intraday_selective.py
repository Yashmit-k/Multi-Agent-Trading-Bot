"""Selective intraday mechanics: one trade per stock per day, stop, hold exit, top-1 selection."""

from datetime import date

import numpy as np

from quant_agents.research import agent_tuning as at
from quant_agents.research import intraday_selective as sel

DAY = date(2025, 1, 6).toordinal()


def _panel(n_sym: int = 3) -> at.Panel:
    bars = 75
    minutes = [9 * 60 + 15 + 5 * (k + 1) for k in range(bars)]
    clock = np.array([(m // 60) * 100 + m % 60 for m in minutes])
    shape = (bars, n_sym)
    price = np.full(shape, 100.0)
    return at.Panel("5m", [f"S{i}" for i in range(n_sym)], np.arange(bars, dtype=float), np.full(bars, DAY), clock, np.full(shape, np.nan), price.copy(), price + 0.1, price - 0.1, price.copy(), {}, {})


def _period():  # type: ignore[no-untyped-def]
    return (date(2025, 1, 1), date(2025, 1, 31))


def test_one_trade_per_stock_per_day_and_hold_exit() -> None:
    panel = _panel()
    signal = np.zeros(panel.close.shape)
    confidence = np.ones(panel.close.shape)
    signal[3:20, 0] = 0.9  # qualifies on many bars: only one trade that day
    out = sel.simulate(panel, signal, confidence, _period(), 0.6, 12, "all")
    assert out["trades"] == 1 and out["exits"] == {"hold": 1}


def test_stop_and_top1() -> None:
    panel = _panel()
    panel.low[10, 0] = 97.0  # -3%: below the -2% stop
    signal = np.zeros(panel.close.shape)
    confidence = np.ones(panel.close.shape)
    signal[3, 0], signal[3, 1] = 0.9, 0.7
    both = sel.simulate(panel, signal, confidence, _period(), 0.6, None, "all")
    assert both["trades"] == 2 and both["exits"].get("stop") == 1
    top = sel.simulate(panel, signal, confidence, _period(), 0.6, None, "top1")
    assert top["trades"] == 1 and top["exits"] == {"stop": 1}  # only the strongest stock (S0)


def test_target_exit_from_the_bar_after_fill() -> None:
    panel = _panel()
    panel.high[8, 0] = 101.5  # +1.45% after a 100.05 entry: hits a 1% target
    signal = np.zeros(panel.close.shape)
    confidence = np.ones(panel.close.shape)
    signal[3, 0] = 0.9
    out = sel.simulate(panel, signal, confidence, _period(), 0.6, None, "all", stop_pct=0.02, target_pct=0.01)
    assert out["exits"] == {"target": 1} and out["net_per_trade"] > 0
    default = sel.simulate(panel, signal, confidence, _period(), 0.6, None, "all")
    assert default["exits"] == {"square_off": 1}  # the original study's behaviour is unchanged

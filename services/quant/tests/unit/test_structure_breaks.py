"""Structure-break study mechanics on synthetic 5-minute bars."""

from datetime import datetime, timedelta, timezone

import numpy as np

from quant_agents.research import order_blocks as ob
from quant_agents.research import structure_breaks as sb

UTC = timezone.utc
DAY0 = datetime(2025, 1, 6, 3, 45, tzinfo=UTC)  # Monday 09:15 IST


def _bars(closes, *, lows=None, highs=None, opens=None):  # type: ignore[no-untyped-def]
    close = np.array(closes, dtype=float)
    open_ = np.array(opens if opens is not None else [closes[0]] + list(closes[:-1]), dtype=float)
    high = np.array(highs, dtype=float) if highs is not None else np.where(close >= open_, close + 0.2, open_ + 0.1)
    low = np.array(lows, dtype=float) if lows is not None else np.minimum(open_, close) - 0.2
    starts = [DAY0 + timedelta(minutes=5 * i) for i in range(len(close))]
    return ob.Bars(starts, [s + timedelta(minutes=5) for s in starts], open_, high, low, close)


def test_break_records_broken_level_and_swing_low() -> None:
    closes = [100.0 + 0.1 * (i % 2) for i in range(10)] + [101, 103, 105, 104, 103, 102, 103, 104, 106]
    bars = _bars(closes)
    [brk] = [b for b in sb.bullish_breaks(bars) if b.level > 105]
    assert brk.level == float(bars.high[12]) and bars.close[brk.bos] > brk.level
    assert brk.swing_low == float(bars.low[12 : brk.bos + 1].min())


def test_no_look_ahead() -> None:
    closes = [100.0 + 0.1 * (i % 2) for i in range(10)] + [101, 103, 105, 104, 103, 102, 103, 104, 106, 105, 107]
    full = sb.bullish_breaks(_bars(closes))
    for cut in range(8, len(closes)):
        assert sb.bullish_breaks(_bars(closes[:cut])) == [b for b in full if b.bos < cut]


def test_two_targets_then_breakeven() -> None:
    # Entry 100, stop 99 (R = 1). Bar 1 reaches TP1 (101) only, bar 2 falls back to entry: second half at breakeven.
    bars = _bars([100, 100.8, 99.9, 99.5], highs=[100.2, 101.2, 100.9, 100.0], lows=[99.6, 100.4, 99.95, 99.3], opens=[100, 100.5, 100.8, 99.9])
    trade = sb.manage("T", bars, 0, 100.0, 99.0, (1.0, 1.5), 10)
    assert trade.reached_tp1 and trade.reason == "breakeven"
    # Both targets: TP1 on bar 1, TP2 (101.5) on bar 2.
    bars = _bars([100, 100.8, 101.4], highs=[100.2, 101.1, 101.6], lows=[99.6, 100.4, 100.9], opens=[100, 100.5, 100.9])
    win = sb.manage("T", bars, 0, 100.0, 99.0, (1.0, 1.5), 10)
    assert win.reason == "tp2" and win.net > 0


def test_stop_before_tp1_and_square_off() -> None:
    bars = _bars([100, 99.5, 98.8], highs=[100.2, 100.1, 99.6], lows=[99.6, 99.4, 98.7], opens=[100, 100, 99.5])
    loss = sb.manage("T", bars, 0, 100.0, 99.0, (1.0, 1.5), 10)
    assert loss.reason == "stop" and not loss.reached_tp1 and loss.net < 0
    flat = _bars([100.0] * 80, highs=[100.3] * 80, lows=[99.7] * 80, opens=[100.0] * 80)
    timed = sb.manage("T", flat, 0, 100.0, 99.0, (1.0, 1.5), 10)
    assert timed.reason == "time" and timed.exit_at.astimezone(ob.IST).strftime("%H:%M") == "15:15"


def test_trend_filter_uses_completed_hours_only() -> None:
    # 12 sessions of 75 five-minute bars (09:15-15:30 IST), rising steadily.
    starts = [DAY0 + timedelta(days=day, minutes=5 * k) for day in range(12) for k in range(75)]
    close = np.array([100 + 0.05 * i for i in range(len(starts))])
    five = ob.Bars(starts, [s + timedelta(minutes=5) for s in starts], close - 0.02, close + 0.1, close - 0.1, close)
    hourly = ob.resample(five, 60)
    assert len(hourly) == 12 * 7  # 6 full hours + the short 15:15-15:30 bar per session
    ends, flags = sb.trend_up_at(hourly)
    assert flags[-1] and not flags[: sb.EMA_BARS - 1].any()  # undefined EMA is never "up"
    assert len(ends) == len(hourly)

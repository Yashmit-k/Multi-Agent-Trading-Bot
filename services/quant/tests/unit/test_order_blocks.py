"""Order-block study mechanics on synthetic bars: structure, no look-ahead, resampling, trade management."""

from datetime import datetime, timedelta, timezone

import numpy as np

from quant_agents.research import order_blocks as ob

UTC = timezone.utc
DAY0 = datetime(2025, 1, 6, 3, 45, tzinfo=UTC)  # Monday 09:15 IST


def _bars(closes: list[float], *, opens: list[float] | None = None, step: timedelta = timedelta(minutes=5), start: datetime = DAY0) -> ob.Bars:
    close = np.array(closes, dtype=float)
    open_ = np.array(opens if opens is not None else [closes[0]] + closes[:-1], dtype=float)
    high = np.where(close >= open_, close + 0.2, open_ + 0.1)  # distinct neighbouring highs, as in real data
    low = np.minimum(open_, close) - 0.2
    starts = [start + step * i for i in range(len(closes))]
    return ob.Bars(starts, [s + step for s in starts], open_, high, low, close)


def _structure() -> list[float]:
    # Flat warm-up, swing high at 105, pullback with a bearish candle, then a strong break above 105.
    warm = [100.0 + 0.1 * (i % 2) for i in range(20)]
    leg = [101, 103, 105, 104, 103, 102, 101.5, 101, 103, 106, 109, 110]
    return warm + leg


def test_block_is_last_bearish_candle_before_the_break() -> None:
    bars = _bars(_structure())
    blocks = ob.bullish_blocks(bars)
    assert blocks, "expected a bullish order block"
    block = blocks[-1]
    assert bars.close[block.bos] > 105.2  # closed above the confirmed pivot high (105 + 0.2 wick)
    assert bars.close[block.ob] < bars.open[block.ob]  # bearish candle
    assert block.ob < block.bos


def test_no_look_ahead_in_structure() -> None:
    closes = _structure()
    full = ob.bullish_blocks(_bars(closes))
    for cut in range(10, len(closes)):
        partial = ob.bullish_blocks(_bars(closes[:cut]))
        assert partial == [blk for blk in full if blk.bos < cut]  # a later bar never changes an earlier block


def test_resample_needs_every_five_minute_bar() -> None:
    five = _bars([100 + i for i in range(9)])
    fifteen = ob.resample(five, 15)
    assert len(fifteen) == 3 and fifteen.open[0] == five.open[0] and fifteen.close[0] == five.close[2]
    assert fifteen.high[1] == five.high[3:6].max()
    gappy = ob.Bars(five.start[:2] + five.start[3:], five.end[:2] + five.end[3:], *(np.delete(arr, 2) for arr in (five.open, five.high, five.low, five.close)))
    assert len(ob.resample(gappy, 15)) == 2  # the first 15m bar is incomplete and dropped


def test_stop_target_and_square_off() -> None:
    book = ob.Book("B", 60, 5, True)
    rising = _bars([100, 100.5, 101, 101.5, 102, 102.5, 103, 103.5])
    days, by_day = ob._session_index(rising)
    pos = {day: k for k, day in enumerate(days)}
    win = ob._manage("T", rising, 1, 100.0, 99.0, 102.0, 10, book, days, pos, by_day)
    assert win.reason == "target" and win.exit >= 102.0 * (1 - ob.SLIP) - 1e-9 and win.net > 0
    falling = _bars([100, 99.5, 98.5, 98])
    days, by_day = ob._session_index(falling)
    loss = ob._manage("T", falling, 1, 100.0, 99.0, 102.0, 10, book, days, {d: k for k, d in enumerate(days)}, by_day)
    assert loss.reason == "stop" and loss.net < 0
    flat = _bars([100.0] * 80)  # 09:15 to 15:55: square-off must come at the bar ending 15:15
    days, by_day = ob._session_index(flat)
    timed = ob._manage("T", flat, 1, 100.0, 99.0, 102.0, 10, book, days, {d: k for k, d in enumerate(days)}, by_day)
    assert timed.reason == "time" and timed.exit_at.astimezone(ob.IST).strftime("%H:%M") == "15:15"


def test_one_position_at_a_time() -> None:
    def trade(start: int, length: int) -> ob.Trade:
        entry = DAY0 + timedelta(minutes=5 * start)
        exit_ = entry + timedelta(minutes=5 * length)
        return ob.Trade("T", entry, exit_, exit_.date(), 100, 101, 99, 1, "x", 1.0, 1.0)

    taken = ob.one_at_a_time([trade(10, 5), trade(0, 20), trade(25, 2)])
    assert [t.entry_at for t in taken] == [DAY0, DAY0 + timedelta(minutes=125)]


def test_intraday_costs_are_below_delivery_costs() -> None:
    assert 0 > ob.mis_net(100, 100, 200) > ob.cnc_net(100, 100, 200)

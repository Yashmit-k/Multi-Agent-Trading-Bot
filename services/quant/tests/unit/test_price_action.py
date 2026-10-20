"""Price-action study: execution rules and no look-ahead, on small synthetic grids."""

import numpy as np

from quant_agents.research import price_action as pa

FREE = lambda buy, sell: 0.0  # noqa: E731 - charges switched off to check prices exactly


def _grid(sessions: int = 30, price: float = 100.0, volume: float = 1000.0) -> pa.Grid:
    shape = (sessions, pa.BARS)
    full = lambda value: np.full(shape, value, dtype=float)  # noqa: E731
    return pa.Grid(np.arange(sessions), full(price), full(price + 0.5), full(price - 0.5), full(price), full(volume))


def test_bar_index_maps_the_session_clock() -> None:
    assert pa.bar_index(920) == 0 and pa.bar_index(930) == 2 and pa.bar_index(1515) == 71 and pa.bar_index(1530) == 74


def test_fill_is_the_next_bar_open_and_the_stop_counts_on_the_fill_bar() -> None:
    grid = _grid()
    grid.open[5, 11], grid.low[5, 11] = 101.0, 98.0  # fill bar dips through the stop
    trade = pa.simulate_intraday(grid, pa.Candidate("X", 5, 10, 1.0, stop=99.0, target=None), charges=FREE)
    assert trade["reason"] == "stop"
    entry = 101.0 * (1 + pa.SLIP)
    qty = int(pa.NOTIONAL // entry)
    assert np.isclose(trade["gross"], qty * (99.0 * (1 - pa.SLIP) - entry))


def test_target_and_square_off_exits() -> None:
    grid = _grid()
    grid.high[3, 20] = 105.0
    hit = pa.simulate_intraday(grid, pa.Candidate("X", 3, 10, 1.0, stop=90.0, target=104.0), charges=FREE)
    assert hit["reason"] == "target"
    grid.close[4, pa.SQUARE_OFF] = 102.0
    held = pa.simulate_intraday(grid, pa.Candidate("X", 4, 10, 1.0, stop=90.0, target=None), charges=FREE)
    assert held["reason"] == "square_off" and held["gross"] > 0
    assert pa.simulate_intraday(grid, pa.Candidate("X", 4, pa.SQUARE_OFF, 1.0, stop=90.0, target=None)) is None  # no bar left to fill


def test_no_trade_when_the_fill_is_already_past_the_target() -> None:
    grid = _grid()
    assert pa.simulate_intraday(grid, pa.Candidate("X", 2, 5, 1.0, stop=90.0, target=99.0), charges=FREE) is None


def test_daily_cap_takes_candidates_in_time_order() -> None:
    early = pa.Candidate("A", 0, 5, rank=0.1, stop=1, target=None)
    later_stronger = pa.Candidate("B", 0, 9, rank=9.0, stop=1, target=None)
    same_bar = [pa.Candidate("C", 0, 5, rank=2.0, stop=1, target=None), pa.Candidate("D", 0, 5, rank=3.0, stop=1, target=None)]
    chosen = pa.take_in_time_order([later_stronger, early, *same_bar], cap=2)
    assert [c.symbol for c in chosen] == ["D", "C"]  # earliest bar, then rank; the later strong signal never displaces them
    assert [c.symbol for c in pa.take_in_time_order([later_stronger, early], cap=2)] == ["A", "B"]


def test_volume_baseline_uses_only_earlier_sessions() -> None:
    grid = _grid()
    before = grid.cumulative_volume_ratio()[25].copy()
    grid.volume[26:] *= 50  # change the future
    after = grid.cumulative_volume_ratio()[25]
    assert np.allclose(before, after) and np.allclose(before, 1.0)
    assert np.isnan(grid.cumulative_volume_ratio()[5]).all()  # fewer than 10 earlier sessions


def test_orb_signal_is_the_first_close_above_the_range_and_needs_volume_and_relative_strength() -> None:
    grid, nifty = _grid(), _grid()
    s, end = 25, pa.OR_END[15]
    grid.close[s, end + 2] = 101.0  # first close above the 100.5 range high
    grid.close[s, end + 5] = 103.0
    ratio = np.full(grid.close.shape, 2.0)
    [cand] = pa.orb_candidates("X", grid, nifty, ratio, minutes=15, target_r=2.0)
    assert cand.bar == end + 2 and cand.stop == 99.5 and np.isclose(cand.target, 101.0 + 2 * 1.5)
    weak = np.full(grid.close.shape, 1.0)
    assert pa.orb_candidates("X", grid, nifty, weak, minutes=15, target_r=None) == []  # the first breakout lacked volume


def test_swing_fills_next_open_and_stops() -> None:
    n = 40
    d = pa.Daily(np.arange(n), np.full(n, 100.0), np.full(n, 101.0), np.full(n, 99.0), np.full(n, 100.0), np.full(n, 1000.0))
    d.low[32] = 95.0
    trade = pa.simulate_swing(d, 30, stop=96.0, hold=5, charges=FREE)
    assert trade["reason"] == "stop" and trade["exit_session"] == 32
    clean = pa.simulate_swing(d, 10, stop=96.0, hold=5, charges=FREE)
    assert clean["reason"] == "time" and clean["exit_session"] == 15
    assert pa.simulate_swing(d, n - 3, stop=96.0, hold=5) is None  # not enough days left


def test_breakout_needs_a_new_high_volume_and_a_strong_close() -> None:
    n = 30
    d = pa.Daily(np.arange(n), np.full(n, 100.0), np.full(n, 101.0), np.full(n, 99.0), np.full(n, 100.0), np.full(n, 1000.0))
    d.high[25], d.low[25], d.close[25], d.volume[25] = 104.0, 100.0, 103.8, 2500.0
    assert [k for _, _, k, _, _ in pa.breakout_signals("X", d)] == [25]
    d.volume[25] = 1500.0
    assert pa.breakout_signals("X", d) == []

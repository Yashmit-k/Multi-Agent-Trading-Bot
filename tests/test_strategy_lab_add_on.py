"""Strategy-lab additions for the dip strategy: return vs NIFTY, frozen level targets, an add-on, and the audit fixes."""

from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from core_api.strategy_lab import StrategyDefinition, equity_curve, leg_charges, simulate_symbol
from core_paper.strategy_engine import Bars, Context, Operand, operand_values, target_prices
from tests.test_strategy_lab import _bars

UTC = timezone.utc


def _strategy(**extra) -> StrategyDefinition:  # type: ignore[no-untyped-def]
    base = {
        "name": "dip",
        "entry": {"items": [{"left": {"indicator": "close"}, "op": "==", "right": {"value": 100}}]},
        "stop": {"kind": "percent", "value": 10},
        "targets": [{"kind": "level", "value": 0, "level": {"indicator": "high", "offset": 1}, "fraction": 1}],
        "slippage_bps": 0,
    }
    base.update(extra)
    return StrategyDefinition.model_validate(base)


def _run(bars: Bars, strategy: StrategyDefinition, index: Bars | None = None):  # type: ignore[no-untyped-def]
    return simulate_symbol("T", Context(bars=bars, timeframe=strategy.timeframe, higher={}, cache={}, index=index), strategy, 0)


def test_relative_return_is_the_stock_minus_nifty_on_the_same_bars() -> None:
    stock = _bars([100] * 7, [100] * 7, [100] * 7, [100, 100, 100, 100, 100, 100, 90])
    nifty = _bars([100] * 7, [100] * 7, [100] * 7, [100, 100, 100, 100, 100, 100, 98])
    values = operand_values(Context(stock, "1d", {}, {}, index=nifty), Operand(indicator="rel_return_pct", period=5))
    assert values[-1] == pytest.approx(-10 - -2)
    assert np.isnan(operand_values(Context(stock, "1d", {}, {}), Operand(indicator="rel_return_pct", period=5))[-1])  # no NIFTY: never true
    with pytest.raises(ValueError):
        Operand(indicator="rel_return_pct", timeframe="1d")


def test_level_target_is_frozen_at_the_signal_and_wrong_side_levels_are_dropped() -> None:
    strategy = _strategy()
    bars = _bars([100, 110, 100, 100], [100, 112, 100, 100], [100, 100, 100, 100], [100, 108, 100, 100])
    context = Context(bars, "1d", {}, {})
    assert target_prices(strategy, context, 2, 100.0, 90.0) == [(112.0, 1.0)]  # previous bar's high, read at the signal
    assert target_prices(strategy, context, 1, 100.0, 90.0) == []  # a level at or below the entry is not a target
    with pytest.raises(ValueError):
        StrategyDefinition.model_validate({**_strategy().model_dump(), "targets": [{"kind": "level", "value": 0}]})


def test_add_on_fills_restops_from_the_average_and_sells_at_its_own_target() -> None:
    # signal (close 100) at bar 1 with yesterday's high 106 as target 1; add-on rule: close <= 92
    strategy = _strategy(
        entry={"items": [{"left": {"indicator": "close"}, "op": "==", "right": {"value": 100}}]},
        targets=[{"kind": "level", "value": 0, "level": {"indicator": "high", "offset": 1}, "fraction": 1}],
        add_on={"when": {"items": [{"left": {"indicator": "close"}, "op": "<=", "right": {"value": 92}}]}, "notional": 20000,
                "target": {"kind": "level", "value": 3, "level": {"indicator": "high", "offset": 1}}},
    )
    o = [100, 100, 100, 95, 92, 93, 100.5, 106, 110]
    h = [106, 101, 101, 96, 93, 94, 101, 107, 110]
    l = [99, 99, 99.5, 91, 91.5, 92, 99, 105, 108]
    c = [99, 100, 101, 92, 92.5, 93, 100.5, 106, 110]
    [trade] = _run(_bars(o, h, l, c), strategy)
    assert len(trade.adds) == 1 and trade.adds[0].price == pytest.approx(92.0)  # add-on at the next open (below its limit)
    initial, added = trade.quantity, trade.adds[0].quantity
    reasons = [(leg.reason, leg.quantity) for leg in trade.legs]
    assert reasons == [("target", initial), ("add_on_target", added)]
    assert trade.legs[0].price == pytest.approx(106) and trade.legs[1].price == pytest.approx(110)  # opened above 106 x 1.03: sells at the open
    assert trade.net_pnl == pytest.approx(sum(leg.quantity * leg.price for leg in trade.legs) - trade.cost - trade.charges)


def test_add_on_stop_is_measured_from_the_average_cost() -> None:
    strategy = _strategy(add_on={"when": {"items": [{"left": {"indicator": "close"}, "op": "<=", "right": {"value": 92}}]}, "notional": 20000})
    # entry 100, add at 92 (average about 96): the stop moves from 90 to about 86.4; a fall to 88 does not stop out
    o = [100, 100, 100, 95, 92, 89, 88.5]
    h = [106, 101, 101, 96, 93, 90, 89]
    l = [99, 99, 99.5, 91, 91.5, 88, 88]
    c = [99, 100, 101, 92, 92.5, 89, 88.5]
    [trade] = _run(_bars(o, h, l, c), strategy)
    assert trade.adds and trade.reason == "end_of_data"


def test_a_daily_trade_stopped_out_on_its_fill_day_pays_intraday_charges() -> None:
    strategy = _strategy(targets=[{"kind": "percent", "value": 20, "fraction": 1}])
    bars = _bars([100, 100, 100, 100], [100, 100.5, 100.2, 100], [99, 99.5, 80, 100], [99, 100, 85, 100])
    [trade] = _run(bars, strategy)
    assert trade.reason == "stop" and trade.entry_at.date() == trade.exit_at.date()
    bought, sold = trade.entry_price * trade.quantity, sum(leg.quantity * leg.price for leg in trade.legs)
    assert trade.charges == pytest.approx(leg_charges(bought, sold, "MIS"))
    assert trade.charges < leg_charges(bought, sold, "CNC")


def test_equity_curve_counts_partial_exits_and_only_shares_still_held() -> None:
    strategy = _strategy(targets=[{"kind": "percent", "value": 5, "fraction": 0.5}, {"kind": "percent", "value": 50, "fraction": 0.5}])
    o = [100, 100, 100, 105, 105]
    h = [100, 100.5, 101, 106, 105]
    l = [99, 99.5, 99.5, 104, 104]
    c = [99, 100, 101, 105, 105]
    bars = _bars(o, h, l, c)
    [trade] = _run(bars, strategy)
    days = [moment.date() for moment in bars.end]
    closes = {"T": {day: float(close) for day, close in zip(days, c)}}
    curve = equity_curve([trade], closes, days, 100000)
    half = trade.quantity // 2
    on_target_day = next(point["equity"] for point in curve if point["date"] == days[3].isoformat())
    expected = 100000 + half * (105 - trade.average_cost) + (trade.quantity - half) * (105 - trade.average_cost)
    assert on_target_day == pytest.approx(expected, abs=1)

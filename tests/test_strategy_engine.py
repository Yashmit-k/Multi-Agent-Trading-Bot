"""Strategy engine: every indicator is look-ahead free; rule logic; higher timeframes; validation; legacy definitions."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from core_paper.strategy_engine import (
    CATALOG,
    Bars,
    Condition,
    Context,
    Group,
    Operand,
    StrategyDefinition,
    _ema,
    _rsi,
    evaluate,
    operand_values,
    raw_indicator,
    resample,
)

UTC = timezone.utc
DAY0 = datetime(2025, 1, 6, 3, 45, tzinfo=UTC)  # Monday 09:15 IST


def _intraday(days: int = 6, seed: int = 0) -> Bars:
    rng = np.random.default_rng(seed)
    starts = [DAY0 + timedelta(days=d, minutes=5 * k) for d in range(days) for k in range(75)]
    close = 100 * np.cumprod(1 + rng.normal(0, 0.002, len(starts)))
    open_ = np.concatenate([[100.0], close[:-1]]) * (1 + rng.normal(0, 0.0005, len(starts)))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.001, len(starts))))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.001, len(starts))))
    volume = rng.integers(1000, 5000, len(starts)).astype(float)
    return Bars(starts, [s + timedelta(minutes=5) for s in starts], open_, high, low, close, volume)


def _daily(n: int = 300, seed: int = 1) -> Bars:
    rng = np.random.default_rng(seed)
    ends = [datetime(2024, 1, 1, 10, 0, tzinfo=UTC) + timedelta(days=i) for i in range(n)]
    close = 100 * np.cumprod(1 + rng.normal(0.0005, 0.012, n))
    open_ = np.concatenate([[100.0], close[:-1]])
    high = np.maximum(open_, close) * 1.006
    low = np.minimum(open_, close) * 0.994
    return Bars([e - timedelta(hours=6, minutes=15) for e in ends], ends, open_, high, low, close, rng.integers(1e5, 5e5, n).astype(float))


def _cut(bars: Bars, k: int) -> Bars:
    return Bars(bars.start[:k], bars.end[:k], bars.open[:k], bars.high[:k], bars.low[:k], bars.close[:k], bars.volume[:k])


@pytest.mark.parametrize("name", sorted(CATALOG))
def test_every_indicator_is_look_ahead_free(name: str) -> None:
    bars = _intraday()
    full = raw_indicator(bars, name, None, None, None, True, {})
    assert len(full) == len(bars)
    for cut in (120, 200, 333):
        partial = raw_indicator(_cut(bars, cut), name, None, None, None, True, {})
        np.testing.assert_allclose(partial, full[:cut], equal_nan=True, rtol=1e-9, atol=1e-9, err_msg=f"{name} changed when later bars were removed")


def test_hand_checked_values() -> None:
    values = np.array([1.0, 2, 3, 4, 5])
    assert _ema(values, 3)[2] == 2.0 and _ema(values, 3)[3] == 3.0
    assert _rsi(np.array([1.0, 2, 3, 4, 5, 6]), 3)[-1] == 100.0
    bars = _intraday(days=1)
    vwap = raw_indicator(bars, "vwap", None, None, None, True, {})
    typical = (bars.high + bars.low + bars.close) / 3
    assert vwap[0] == pytest.approx(typical[0]) and vwap[-1] == pytest.approx(float((typical * bars.volume).sum() / bars.volume.sum()))
    rising = Bars(*(_daily(120).__dict__[k] for k in ("start", "end")), *(np.linspace(100, 200, 120) * f for f in (0.999, 1.004, 0.996, 1.0)), np.full(120, 1e5))
    assert raw_indicator(rising, "supertrend_dir", 10, None, 3.0, False, {})[-1] == 1.0


def test_session_values_use_the_previous_day() -> None:
    bars = _intraday(days=3)
    prev_close = raw_indicator(bars, "prev_day_close", None, None, None, True, {})
    assert np.isnan(prev_close[:75]).all()
    assert prev_close[75] == bars.close[74] and prev_close[150] == bars.close[149]
    orh = raw_indicator(bars, "opening_range_high", 15, None, None, True, {})
    assert np.isnan(orh[:2]).all() and orh[2] == pytest.approx(bars.high[:3].max())  # known once 09:30 closes


def _context(bars: Bars, timeframe: str = "5m", higher: dict | None = None) -> Context:
    return Context(bars=bars, timeframe=timeframe, higher=higher or {}, cache={})


def _cond(left: dict, op: str, right: dict, **extra) -> Condition:  # type: ignore[no-untyped-def]
    return Condition.model_validate({"left": left, "op": op, "right": right, **extra})


def test_group_logic_offsets_math_and_persistence() -> None:
    bars = _intraday(days=2)
    ctx = _context(bars)
    above = _cond({"indicator": "close"}, ">", {"indicator": "ema", "period": 20})
    below = _cond({"indicator": "close"}, "<", {"indicator": "ema", "period": 20})
    a, b = evaluate(ctx, Group(items=[above])), evaluate(ctx, Group(items=[below]))
    assert not (a & b).any()
    either = evaluate(ctx, Group(logic="any", items=[above, below]))
    assert (either == (a | b)).all()
    assert (evaluate(ctx, Group(negate=True, items=[above])) == ~a).all()
    nested = evaluate(ctx, Group(items=[Group(logic="any", items=[above, below]), above]))
    assert (nested == a).all()
    three = evaluate(ctx, Group(items=[_cond({"indicator": "close"}, ">", {"indicator": "ema", "period": 20}, for_bars=3)]))
    for i in np.where(three)[0]:
        assert a[i - 2 : i + 1].all()
    recent = evaluate(ctx, Group(items=[_cond({"indicator": "close"}, ">", {"indicator": "ema", "period": 20}, within_bars=4)]))
    for i in range(4, len(bars)):
        assert recent[i] == a[i - 3 : i + 1].any()
    lagged = operand_values(ctx, Operand(indicator="close", offset=3))
    assert np.isnan(lagged[:3]).all() and lagged[10] == bars.close[7]
    scaled = operand_values(ctx, Operand(indicator="close", scale=1.01, shift=-1))
    assert scaled[5] == pytest.approx(bars.close[5] * 1.01 - 1)


def test_higher_timeframe_uses_completed_bars_only() -> None:
    five = _intraday(days=3)
    hourly = resample(five, 60)
    daily = Bars(
        [datetime(2025, 1, 6 + d, 3, 45, tzinfo=UTC) for d in range(3)],
        [datetime(2025, 1, 6 + d, 10, 0, tzinfo=UTC) for d in range(3)],
        np.array([1.0, 2, 3]), np.array([1.0, 2, 3]), np.array([1.0, 2, 3]), np.array([10.0, 20, 30]), np.ones(3),
    )
    ctx = _context(five, higher={"1d": daily, "1h": hourly})
    values = operand_values(ctx, Operand(indicator="close", timeframe="1d"))
    # A daily bar counts once it has closed: from the 15:30 bar (same instant, same price) onward.
    assert np.isnan(values[:74]).all()  # day 1 before 15:30: no completed daily bar yet
    assert (values[74:149] == 10).all() and (values[149:224] == 20).all() and values[224] == 30  # during a day only the previous close is visible
    hour = operand_values(ctx, Operand(indicator="close", timeframe="1h"))
    assert np.isnan(hour[:11]).all() and hour[11] == hourly.close[0]  # the 10:15 bar is the first that sees the 09:15 hour


def test_validation_rules() -> None:
    base = {"name": "x", "entry": {"items": [{"left": {"indicator": "close"}, "op": ">", "right": {"value": 1}}]}}
    StrategyDefinition.model_validate(base)
    with pytest.raises(Exception, match="intraday only"):
        StrategyDefinition.model_validate({**base, "direction": "short"})
    with pytest.raises(Exception, match="need a stop"):
        StrategyDefinition.model_validate({**base, "stop": {"kind": "none"}, "targets": [{"kind": "r_multiple", "value": 2}]})
    with pytest.raises(Exception, match="more than 100%"):
        StrategyDefinition.model_validate({**base, "targets": [{"kind": "percent", "value": 1, "fraction": 0.7}, {"kind": "percent", "value": 2, "fraction": 0.7}]})
    with pytest.raises(Exception, match="higher-timeframe"):
        StrategyDefinition.model_validate({**base, "timeframe": "1h", "entry": {"items": [{"left": {"indicator": "close", "timeframe": "15m"}, "op": ">", "right": {"value": 1}}]}})
    with pytest.raises(Exception, match="unknown indicator"):
        StrategyDefinition.model_validate({**base, "entry": {"items": [{"left": {"indicator": "nope"}, "op": ">", "right": {"value": 1}}]}})


def test_strategies_saved_before_groups_still_load() -> None:
    legacy = {
        "name": "old",
        "timeframe": "1d",
        "entry": [{"left": {"indicator": "ema", "period": 20}, "op": "crosses_above", "right": {"indicator": "ema", "period": 50}}],
        "exit": [],
        "stop_loss_pct": 5,
        "take_profit_pct": 15,
        "position_notional": 25000,
    }
    loaded = StrategyDefinition.model_validate(legacy)
    assert loaded.entry.logic == "all" and loaded.exit is None
    assert loaded.stop.kind == "percent" and loaded.stop.value == 5
    assert loaded.targets[0].value == 15 and loaded.sizing.value == 25000

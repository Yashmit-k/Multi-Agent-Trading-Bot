"""Point-in-time checks for the intraday breakout runner."""

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from contracts.enums import Timeframe
from contracts.schemas.market import Candle
from core_features.engine import _ema

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "quant" / "src"))

from quant_agents.research.intraday_breakout import simulate_breakout, simulate_indexed

IST = ZoneInfo("Asia/Kolkata")


def _at(day: str, hour: int, minute: int) -> datetime:
    local = datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00").replace(tzinfo=IST)
    return local.astimezone(timezone.utc)


def _bar(timeframe: str, start: datetime, open_: str, high: str, low: str, close: str, volume: int = 1) -> Candle:
    minutes = 5 if timeframe == "5m" else 375
    return Candle(
        symbol="ABC",
        exchange="NSE",
        timeframe=Timeframe(timeframe),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
        start=start,
        end=start + timedelta(minutes=minutes),
    )


def _day(day: str, high: str = "102", close: str = "100") -> Candle:
    return _bar("1d", _at(day, 9, 15), close, high, close, close)


def _five(day: str, hour: int, minute: int, open_: str, high: str, low: str, close: str, volume: int = 1) -> Candle:
    return _bar("5m", _at(day, hour, minute), open_, high, low, close, volume)


def _history() -> tuple[list[Candle], list[Candle], str]:
    days = [f"2024-05-{day:02d}" for day in range(1, 32) if datetime(2024, 5, day).weekday() < 5][:21]
    daily = [_day(day) for day in days[:-1]]
    daily.append(_day(days[-1], high="9999", close="1"))
    signal_day = days[-1]
    bars: list[Candle] = []
    for day in days[-11:-1]:
        bars.append(_five(day, 9, 55, "100", "100", "100", "100", 100))
    prior = days[-2]
    cursor = _at(prior, 9, 15)
    for _ in range(20):
        if cursor.astimezone(IST).hour == 9 and cursor.astimezone(IST).minute == 55:
            cursor += timedelta(minutes=5)
            continue
        bars.append(_five(prior, cursor.astimezone(IST).hour, cursor.astimezone(IST).minute, "100", "100", "100", "100", 0))
        cursor += timedelta(minutes=5)
    for hour, minute in ((9, 45), (9, 50), (9, 55)):
        bars.append(_five(signal_day, hour, minute, "100.4", "100.7", "100.3", "100.6", 50))
    bars.append(_five(signal_day, 10, 0, "100.5", "100.5", "100.5", "100.5", 1))
    bars.append(_five(signal_day, 10, 5, "50", "50", "50", "50", 1))
    bars.append(_five(signal_day, 15, 25, "100.7", "100.7", "100.7", "100.7", 1))
    return daily, bars, signal_day


def test_full_rule_uses_prior_close_prior_high_and_prior_volume() -> None:
    daily, bars, _ = _history()
    trades, funnel, ordered, _, _ = simulate_breakout("ABC", bars, daily)
    full = [trade for trade in trades if trade["variant"] == "full"]
    assert len(full) == 1
    trade = full[0]
    assert trade["previous_close"] == Decimal("100")
    assert trade["high"] == Decimal("102")
    assert trade["expected_volume"] == Decimal("100")
    assert trade["entry_price"] == Decimal("100.5")
    assert trade["signal_price"] == Decimal("100.6")
    assert trade["exit_reason"] == "stop"
    signal_index = next(index for index, bar in enumerate(ordered) if bar.end == trade["signal_time"])
    expected = Decimal(str(_ema([float(bar.close) for bar in ordered[: signal_index + 1]], 20)[-1]))
    assert trade["ema20"] == expected
    assert funnel["near_high"] == 1


def test_red_candles_do_not_satisfy_the_primary_rising_rule() -> None:
    daily, bars, signal_day = _history()
    replaced = []
    for bar in bars:
        local = bar.end.astimezone(IST)
        if local.date().isoformat() == signal_day and bar.timeframe == Timeframe.M5 and local.hour == 9:
            replaced.append(_bar("5m", bar.start, "101", "101", "100.5", "100.5", bar.volume))
        else:
            replaced.append(bar)
    trades, _, _, _, _ = simulate_breakout("ABC", replaced, daily)
    assert [trade for trade in trades if trade["variant"] == "full"] == []


def test_stop_wins_when_the_same_bar_contains_both_exits() -> None:
    bars = [
        _five("2024-05-02", 10, 0, "100", "100", "100", "100"),
        _five("2024-05-02", 10, 5, "100", "100", "100", "100"),
        _five("2024-05-02", 10, 10, "100", "102", "98", "100"),
        _five("2024-05-02", 15, 25, "100", "100", "100", "100"),
    ]
    flags = [object()] * len(bars)
    from quant_agents.research.intraday_breakout import _Flags

    state = _Flags(False, False, False, False, False, False, Decimal("100"), None, None, None, None, None, None, None, None, None, 0)
    flags = [state if index == 0 else None for index in range(len(bars))]
    trades = simulate_indexed("ABC", bars, flags, [0], "forced")
    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "stop"
    assert trades[0]["exit_price"] == Decimal("100") * Decimal("0.9925")


def test_session_flatten_uses_the_last_five_minute_close() -> None:
    bars = [
        _five("2024-05-02", 10, 0, "100", "100", "100", "100"),
        _five("2024-05-02", 10, 5, "100", "100.2", "99.5", "100"),
        _five("2024-05-02", 15, 25, "100", "100.9", "99.5", "100.8"),
    ]
    from quant_agents.research.intraday_breakout import _Flags

    state = _Flags(False, False, False, False, False, False, Decimal("100"), None, None, None, None, None, None, None, None, None, 0)
    flags = [state if index == 0 else None for index in range(len(bars))]
    trades = simulate_indexed("ABC", bars, flags, [0], "forced")
    assert trades[0]["exit_reason"] == "session_flatten"
    assert trades[0]["exit_price"] == Decimal("100.8")


def test_no_next_bar_creates_no_trade() -> None:
    bars = [_five("2024-05-02", 14, 55, "100", "100", "100", "100")]
    from quant_agents.research.intraday_breakout import _Flags

    state = _Flags(False, False, False, False, False, False, Decimal("100"), None, None, None, None, None, None, None, None, None, 0)
    assert simulate_indexed("ABC", bars, [state], [0], "forced") == []


def session_date_ist(bar: Candle):
    return bar.end.astimezone(IST).date()

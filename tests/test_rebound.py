"""Point-in-time checks for the oversold rebound research runner."""

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from contracts.enums import Timeframe
from contracts.schemas.market import Candle
from core_features.engine import _ema

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "quant" / "src"))

from quant_agents.research.rebound import count_funnel, lookahead_audit, price_trade, simulate_symbol

IST = ZoneInfo("Asia/Kolkata")


def _at(day: str, hour: int, minute: int) -> datetime:
    local = datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00").replace(tzinfo=IST)
    return local.astimezone(timezone.utc)


def _bar(symbol: str, timeframe: str, start: datetime, open_: str, high: str, low: str, close: str) -> Candle:
    end = start + (timedelta(minutes=5) if timeframe == "5m" else timedelta(hours=6, minutes=15))
    return Candle(
        symbol=symbol,
        exchange="NSE",
        timeframe=Timeframe(timeframe),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=1,
        start=start,
        end=end,
    )


def _daily(day: str, close: str) -> Candle:
    start = _at(day, 9, 15)
    return _bar("ABC", "1d", start, close, close, close, close)


def _five(day: str, hour: int, minute: int, open_: str, high: str, low: str, close: str) -> Candle:
    return _bar("ABC", "5m", _at(day, hour, minute), open_, high, low, close)


def test_signal_uses_prior_daily_closes_and_the_next_open() -> None:
    daily = [_daily(f"2024-01-{day:02d}", "100") for day in range(1, 17)]
    daily.extend(
        [
            _daily("2024-01-17", "103"),
            _daily("2024-01-18", "102"),
            _daily("2024-01-19", "101"),
            _daily("2024-01-20", "100"),
            _daily("2024-01-21", "1"),
        ]
    )
    bars = [
        _five("2024-01-21", 9, 15, "93", "93", "91", "92"),
        _five("2024-01-21", 9, 20, "90", "90", "90", "90"),
        _five("2024-01-21", 9, 25, "90", "90", "80", "88"),
        _five("2024-01-21", 15, 25, "88", "88", "88", "88"),
    ]
    trades = [trade for trade in simulate_symbol("ABC", bars, daily) if trade["variant"] == "full" and trade["mode"] == "intraday"]
    assert len(trades) == 1
    trade = trades[0]
    prior = [Decimal("100")] * 16 + [Decimal("103"), Decimal("102"), Decimal("101"), Decimal("100")]
    expected = Decimal(str(_ema([float(close) for close in prior], 20)[-1]))
    assert trade["ema20"] == expected
    assert trade["ema_through"].isoformat() == "2024-01-20"
    assert trade["signal_price"] == Decimal("92")
    assert trade["entry_price"] == Decimal("90")
    assert trade["quantity"] == 222
    assert trade["exit_reason"] == "stop"
    assert trade["exit_price"] == Decimal("90") * Decimal("0.985")


def test_same_bar_stop_beats_the_target() -> None:
    daily = [_daily("2024-01-02", "100")]
    bars = [
        _five("2024-01-03", 9, 15, "100", "100", "98", "98"),
        _five("2024-01-03", 9, 20, "100", "100", "100", "100"),
        _five("2024-01-03", 9, 25, "100", "103", "98", "100"),
        _five("2024-01-03", 15, 25, "100", "100", "100", "100"),
    ]
    trades = [
        trade
        for trade in simulate_symbol("ABC", bars, daily)
        if trade["variant"] == "baseline_today_drop" and trade["mode"] == "intraday"
    ]
    assert len(trades) == 1
    assert trades[0]["exit_reason"] == "stop"
    assert trades[0]["exit_price"] == Decimal("98.5")


def test_intraday_flatten_uses_the_last_five_minute_close() -> None:
    daily = [_daily("2024-01-02", "100"), _daily("2024-01-03", "50")]
    bars = [
        _five("2024-01-03", 9, 15, "100", "100", "98", "98"),
        _five("2024-01-03", 9, 20, "100", "101", "99.5", "100"),
        _five("2024-01-03", 15, 25, "100", "101", "99.5", "101"),
    ]
    trades = simulate_symbol("ABC", bars, daily)
    intraday = [trade for trade in trades if trade["variant"] == "baseline_today_drop" and trade["mode"] == "intraday"]
    delivery = [trade for trade in trades if trade["variant"] == "baseline_today_drop" and trade["mode"] == "delivery"]
    assert intraday[0]["exit_reason"] == "session_flatten"
    assert intraday[0]["exit_price"] == Decimal("101")
    assert delivery[0]["exit_reason"] == "unresolved"
    assert delivery[0]["exit_price"] is None


def test_no_next_same_session_bar_means_no_trade() -> None:
    daily = [_daily("2024-01-02", "100")]
    bars = [_five("2024-01-03", 14, 55, "100", "100", "98", "98")]
    assert simulate_symbol("ABC", bars, daily) == []


def test_costs_do_not_change_the_path() -> None:
    daily = [_daily("2024-01-02", "100")]
    bars = [
        _five("2024-01-03", 9, 15, "100", "100", "98", "98"),
        _five("2024-01-03", 9, 20, "100", "100", "100", "100"),
        _five("2024-01-03", 9, 25, "100", "103", "98", "100"),
        _five("2024-01-03", 15, 25, "100", "100", "100", "100"),
    ]
    raw = [trade for trade in simulate_symbol("ABC", bars, daily) if trade["variant"] == "baseline_today_drop" and trade["mode"] == "intraday"]
    priced = [price_trade(raw[0], Decimal(bps)) for bps in (0, 2, 5)]
    assert [trade["exit_price"] for trade in priced] == [Decimal("98.5")] * 3
    assert priced[0]["transaction_cost"] == Decimal("0.00")
    assert priced[2]["net_pnl"] < priced[0]["net_pnl"]
    audit = lookahead_audit(raw)
    assert audit["status"] == "PASS"
    assert audit["unresolved_count"] == 0


def test_new_delivery_predicates_do_not_change_the_default_variant_set() -> None:
    daily = [_daily(f"2024-01-{day:02d}", "100") for day in range(1, 21)]
    bars = [
        _five("2024-01-21", 9, 15, "80", "80", "80", "80"),
        _five("2024-01-21", 9, 20, "80", "80", "80", "80"),
        _five("2024-01-21", 15, 25, "84", "84", "84", "84"),
    ]
    selected = simulate_symbol(
        "ABC",
        bars,
        daily,
        variants=("drop_and_ema5", "ablate_down_days", "drop_and_down_days", "full"),
        modes=("delivery",),
    )
    assert {trade["variant"] for trade in selected} == {"drop_and_ema5"}
    assert "drop_and_ema5" not in {trade["variant"] for trade in simulate_symbol("ABC", bars, daily)}
    funnel = count_funnel("ABC", bars, daily)
    assert funnel["today_drop"] >= 1
    assert funnel["drop_and_below_ema5"] >= 1
    assert funnel["drop_and_ema_band"] == 0
    assert funnel["full_rule"] == 0


def test_down_days_plus_drop_does_not_require_an_ema() -> None:
    daily = [
        _daily("2024-01-02", "103"),
        _daily("2024-01-03", "102"),
        _daily("2024-01-04", "101"),
        _daily("2024-01-05", "100"),
    ]
    bars = [
        _five("2024-01-08", 9, 15, "98", "98", "98", "98"),
        _five("2024-01-08", 9, 20, "98", "98", "98", "98"),
        _five("2024-01-08", 15, 25, "103", "103", "103", "103"),
    ]
    trades = simulate_symbol(
        "ABC",
        bars,
        daily,
        variants=("drop_and_down_days", "drop_and_ema5", "full"),
        modes=("delivery",),
    )
    assert {trade["variant"] for trade in trades} == {"drop_and_down_days"}

"""Oversold delivery-target checks. Synthetic bars only. The frozen full rule is not modified."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from contracts.enums import Timeframe
from contracts.schemas.market import Candle
from core_features.engine import _ema

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "quant" / "src"))

from quant_agents.research.delivery_costs import delivery_buy, delivery_sell, intraday_buy, intraday_sell
from quant_agents.research.oversold_delivery_targets import simulate_portfolio

IST = ZoneInfo("Asia/Kolkata")
CLOSES = ["100"] * 17 + ["99", "98", "97"]


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


def _daily(symbol: str, day: str, close: str) -> Candle:
    return _bar(symbol, "1d", _at(day, 9, 15), close, close, close, close)


def _five(symbol: str, day: str, hour: int, minute: int, open_: str, high: str, low: str, close: str) -> Candle:
    return _bar(symbol, "5m", _at(day, hour, minute), open_, high, low, close)


def _history(symbol: str, closes: list[str], signal_close: str, entry_open: str, later: list[tuple] | None = None, entry_high: str | None = None) -> tuple[list[Candle], list[Candle]]:
    daily = [_daily(symbol, f"2024-01-{day:02d}", close) for day, close in enumerate(closes, start=1)]
    high = entry_high or entry_open
    if Decimal(high) < Decimal(entry_open):
        high = entry_open
    bars = [
        _five(symbol, "2024-01-21", 9, 15, signal_close, signal_close, signal_close, signal_close),
        _five(symbol, "2024-01-21", 9, 20, entry_open, high, entry_open, entry_open),
    ]
    for row in later or []:
        bars.append(_five(symbol, *row))
    return bars, daily


def _entry(result: dict) -> dict:
    return next(row for row in result["events"] if row["event"] == "entry")


def test_full_rule_uses_the_prior_ema_down_days_and_next_open() -> None:
    daily = [_daily("ABC", f"2024-01-{day:02d}", close) for day, close in enumerate(CLOSES, start=1)]
    daily.append(_daily("ABC", "2024-01-21", "1"))
    bars, _ = _history("ABC", CLOSES, "92", "90")
    result = simulate_portfolio(bars, daily)
    entry = _entry(result)
    expected = Decimal(str(_ema([float(close) for close in CLOSES], 20)[-1]))
    assert entry["previous_close"] == "97"
    assert entry["previous_session"] == "2024-01-20"
    assert Decimal(entry["ema20"]) == expected
    assert int(entry["down_days"]) == 3
    assert Decimal(entry["today_drop_pct"]) <= Decimal("-1")
    assert Decimal("-12") <= Decimal(entry["distance_pct"]) <= Decimal("-5")
    assert entry["signal_price"] == "92"
    assert entry["price"] == "90"
    assert entry["time"] >= entry["signal_time"]
    assert entry["quantity"] == 222
    assert result["audit"]["status"] == "PASS"


def test_fewer_than_twenty_daily_closes_do_not_enter() -> None:
    bars, daily = _history("ABC", ["100"] * 10, "92", "90")
    result = simulate_portfolio(bars, daily)
    assert result["entries"] == 0


def test_two_down_days_do_not_enter_and_today_is_not_counted() -> None:
    bars, daily = _history("ABC", ["100"] * 18 + ["99", "98"], "90", "90")
    result = simulate_portfolio(bars, daily)
    assert result["entries"] == 0


def test_a_drop_smaller_than_one_percent_does_not_enter() -> None:
    bars, daily = _history("ABC", ["100"] * 17 + ["96", "93", "90"], "89.5", "89")
    result = simulate_portfolio(bars, daily)
    assert result["entries"] == 0


def test_a_decline_outside_the_ema_band_does_not_enter() -> None:
    bars, daily = _history("ABC", CLOSES, "96", "96")
    result = simulate_portfolio(bars, daily)
    assert result["entries"] == 0


def test_quantity_uses_the_slipped_price_and_rejects_an_over_cap_fill() -> None:
    bars, daily = _history("ABC", CLOSES, "92", "100")
    slipped = simulate_portfolio(bars, daily, slippage_bps=Decimal("5"))
    entry = _entry(slipped)
    assert Decimal(entry["price"]) > Decimal(entry["raw_price"])
    assert entry["quantity"] == int(Decimal("20000") // Decimal(entry["price"]))
    assert Decimal(entry["price"]) * entry["quantity"] <= Decimal("20000")
    expensive, expensive_daily = _history("ABC", CLOSES, "92", "25000")
    rejected = simulate_portfolio(expensive, expensive_daily)
    assert rejected["entries"] == 0
    assert rejected["rejected"][0]["reason"] == "over_cap"


def test_cash_rejection_is_alphabetical_and_an_exit_does_not_fund_the_same_bar() -> None:
    aaa_bars, aaa_daily = _history("AAA", CLOSES, "92", "100")
    zzz_bars = [
        _five("ZZZ", "2024-01-21", 9, 15, "92", "92", "92", "92"),
        _five("ZZZ", "2024-01-21", 9, 20, "100", "100", "100", "100"),
        _five("ZZZ", "2024-01-21", 9, 25, "100", "102", "100", "101"),
    ]
    aaa_late = [
        _five("AAA", "2024-01-21", 9, 15, "100", "100", "100", "100"),
        _five("AAA", "2024-01-21", 9, 20, "92", "92", "92", "92"),
        _five("AAA", "2024-01-21", 9, 25, "100", "100", "100", "100"),
    ]
    zzz_daily = [_daily("ZZZ", f"2024-01-{day:02d}", close) for day, close in enumerate(CLOSES, start=1)]
    result = simulate_portfolio(aaa_bars + zzz_bars, aaa_daily + zzz_daily, starting_cash=Decimal("50000"))
    names = [row["symbol"] for row in result["events"] if row["event"] == "entry"]
    assert names == ["AAA", "ZZZ"]
    tight = simulate_portfolio(aaa_late + zzz_bars, aaa_daily + zzz_daily, starting_cash=Decimal("25000"))
    assert [row["symbol"] for row in tight["events"] if row["event"] == "entry"] == ["ZZZ"]
    assert tight["rejected"][0]["symbol"] == "AAA"
    assert tight["rejected"][0]["reason"] == "insufficient_cash"
    assert Decimal(tight["rejected"][0]["available_cash"]) < Decimal(tight["rejected"][0]["required_cash"])
    assert tight["exits"] == 1


def test_one_open_position_per_symbol() -> None:
    bars, daily = _history(
        "ABC",
        CLOSES,
        "92",
        "90",
        later=[("2024-01-21", 9, 25, "91", "91", "91", "91"), ("2024-01-21", 9, 30, "90", "90", "90", "90")],
    )
    result = simulate_portfolio(bars, daily)
    assert result["entries"] == 1
    assert result["signals"] > 1


def test_same_day_two_percent_target_and_the_entry_bar_cannot_exit() -> None:
    blocked, blocked_daily = _history("ABC", CLOSES, "92", "90", entry_high="120", later=[("2024-01-21", 9, 25, "90", "91", "90", "90")])
    held = simulate_portfolio(blocked, blocked_daily)
    assert held["exits"] == 0
    bars, daily = _history("ABC", CLOSES, "92", "90", later=[("2024-01-21", 9, 25, "90", "92", "90", "91")])
    result = simulate_portfolio(bars, daily)
    assert result["closed"][0]["holding"] == "same_session"
    assert Decimal(result["closed"][0]["price"]) == Decimal("91.80")
    assert result["closed"][0]["reason"] == "target"


def test_later_session_uses_five_percent_from_the_original_fill() -> None:
    bars, daily = _history(
        "ABC",
        CLOSES,
        "92",
        "90",
        later=[
            ("2024-01-21", 9, 25, "90", "91", "90", "90"),
            ("2024-01-22", 9, 15, "94", "94", "94", "94"),
            ("2024-01-23", 9, 15, "94", "94.50", "94", "94.50"),
        ],
    )
    result = simulate_portfolio(bars, daily)
    exit_row = result["closed"][0]
    assert exit_row["holding"] == "overnight"
    assert exit_row["exit_session"] == "2024-01-23"
    assert Decimal(exit_row["price"]) == Decimal("94.50")


def test_there_is_no_stop_and_a_gap_fills_at_the_open() -> None:
    bars, daily = _history(
        "ABC",
        CLOSES,
        "92",
        "90",
        later=[("2024-01-21", 15, 25, "70", "70", "40", "50"), ("2024-01-22", 9, 15, "40", "40", "40", "40")],
    )
    held = simulate_portfolio(bars, daily)
    assert held["exits"] == 0
    assert held["open_positions"][0]["reason"] == "unresolved"
    gap, gap_daily = _history("ABC", CLOSES, "92", "90", later=[("2024-01-22", 9, 15, "110", "110", "110", "110")])
    opened = simulate_portfolio(gap, gap_daily)
    assert Decimal(opened["closed"][0]["price"]) == Decimal("110")


def test_same_session_reclassification_and_charge_components() -> None:
    bars, daily = _history("ABC", CLOSES, "92", "90", later=[("2024-01-21", 9, 25, "90", "92", "90", "91")])
    result = simulate_portfolio(bars, daily)
    exit_charges = result["closed"][0]["exit_charges"]
    assert Decimal(exit_charges["brokerage"]) > 0
    assert Decimal(exit_charges["dp"]) == 0
    overnight, overnight_daily = _history("ABC", CLOSES, "92", "90", later=[("2024-01-22", 9, 15, "94.50", "94.50", "94.50", "94.50")])
    later = simulate_portfolio(overnight, overnight_daily)
    assert Decimal(later["closed"][0]["exit_charges"]["brokerage"]) == 0
    assert Decimal(later["closed"][0]["exit_charges"]["dp"]) == Decimal("15.34")
    buy = delivery_buy(Decimal("10000"))
    assert buy.stt == Decimal("10.00")
    assert buy.stamp == Decimal("1.50")
    assert intraday_sell(Decimal("10000")).stt == Decimal("2.50")
    assert delivery_sell(Decimal("10000")).dp == Decimal("15.34")
    zero = simulate_portfolio(bars, daily, brokerage=False)
    assert Decimal(zero["closed"][0]["exit_charges"]["brokerage"]) == 0
    assert Decimal(zero["closed"][0]["exit_charges"]["stt"]) > 0


def test_a_missing_next_bar_does_not_invent_an_entry_and_stale_marks_are_flagged() -> None:
    signal_only = [_five("AAA", "2024-01-21", 9, 15, "92", "92", "92", "92")]
    other = [_five("BBB", "2024-01-22", 9, 15, "100", "100", "100", "100")]
    daily = [_daily("AAA", f"2024-01-{day:02d}", close) for day, close in enumerate(CLOSES, start=1)]
    daily += [_daily("BBB", f"2024-01-{day:02d}", close) for day, close in enumerate(CLOSES, start=1)]
    missing = simulate_portfolio(signal_only + other, daily)
    assert missing["entries"] == 0
    bars, book = _history("AAA", CLOSES, "92", "90")
    bars.append(_five("BBB", "2024-01-22", 9, 15, "50", "50", "50", "50"))
    book += [_daily("BBB", f"2024-01-{day:02d}", close) for day, close in enumerate(CLOSES, start=1)]
    marked = simulate_portfolio(bars, book)
    second = marked["days"][1]
    holding = next(row for row in second["holdings"] if row["symbol"] == "AAA")
    assert holding["stale_mark"] is True
    assert marked["exits"] == 0


def test_cash_equity_and_loss_inventory_reconcile() -> None:
    bars, daily = _history("ABC", CLOSES, "92", "90", later=[("2024-01-21", 15, 25, "80", "80", "70", "80")])
    result = simulate_portfolio(bars, daily, starting_cash=Decimal("100000"))
    day = result["days"][0]
    assert day["cash_reconciled"] is True
    assert Decimal(day["equity"]) == Decimal(day["closing_cash"]) + Decimal(day["market_value"])
    assert result["exits"] == 0
    loser = day["loss_inventory"][0]
    assert Decimal(loser["market_value"]) < Decimal(loser["cost_basis"])
    assert Decimal(day["capital_in_loss"]) == Decimal(loser["cost_basis"])
    assert Decimal(day["unrealized_net_pnl"]) < 0
    assert Decimal(result["realized_net_pnl"]) == 0
    sold, sold_daily = _history("ABC", CLOSES, "92", "90", later=[("2024-01-21", 9, 25, "90", "92", "90", "91")])
    closed = simulate_portfolio(sold, sold_daily, starting_cash=Decimal("100000"))
    assert Decimal(closed["realized_net_pnl"]) < Decimal(closed["realized_gross_pnl"])
    assert Decimal(closed["days"][0]["unrealized_net_pnl"]) == 0


def test_two_losers_are_sorted_and_unresolved_positions_stay_open() -> None:
    rows = []
    daily = []
    for symbol, close in (("AAA", "80"), ("BBB", "60")):
        bars, book = _history(symbol, CLOSES, "92", "90", later=[("2024-01-21", 15, 25, close, close, close, close)])
        rows.extend(bars)
        daily.extend(book)
    result = simulate_portfolio(rows, daily)
    assert [row["symbol"] for row in result["days"][0]["loss_inventory"]] == ["BBB", "AAA"]
    assert result["exits"] == 0
    assert {row["reason"] for row in result["open_positions"]} == {"unresolved"}
    assert result["live_enabled"] is False
    assert result["audit"]["status"] == "PASS"

"""Delivery-target portfolio checks. Synthetic bars only. The frozen entry helper is not modified."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from contracts.enums import Timeframe
from contracts.schemas.market import Candle

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "quant" / "src"))

from quant_agents.research.delivery_costs import delivery_buy, delivery_sell, intraday_buy, intraday_sell
from quant_agents.research.today_drop_delivery_targets import simulate_portfolio

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


def _daily(symbol: str, day: str, close: str) -> Candle:
    return _bar(symbol, "1d", _at(day, 9, 15), close, close, close, close)


def _five(symbol: str, day: str, hour: int, minute: int, open_: str, high: str, low: str, close: str) -> Candle:
    return _bar(symbol, "5m", _at(day, hour, minute), open_, high, low, close)


def _book(symbol: str = "ABC", entry_open: str = "100", later: list[tuple] | None = None) -> tuple[list[Candle], list[Candle]]:
    daily = [_daily(symbol, "2024-06-03", "100")]
    bars = [
        _five(symbol, "2024-06-04", 9, 15, "99", "99", "99", "99"),
        _five(symbol, "2024-06-04", 9, 20, entry_open, entry_open, entry_open, entry_open),
    ]
    for row in later or []:
        bars.append(_five(symbol, *row))
    return bars, daily


def test_frozen_entry_uses_the_prior_close_and_the_next_open() -> None:
    daily = [_daily("ABC", "2024-06-03", "100"), _daily("ABC", "2024-06-04", "1")]
    bars = [
        _five("ABC", "2024-06-04", 9, 15, "99", "99", "99", "99"),
        _five("ABC", "2024-06-04", 9, 20, "97", "97", "97", "97"),
    ]
    result = simulate_portfolio(bars, daily, starting_cash=Decimal("1000000"))
    assert result["entries"] == 1
    entry = result["events"][0]
    assert entry["signal_price"] == "99"
    assert entry["previous_close"] == "100"
    assert entry["previous_session"] == "2024-06-03"
    assert entry["price"] == "97"
    assert entry["time"] > entry["signal_time"] or entry["time"] == entry["signal_time"]
    assert entry["quantity"] == 206
    assert result["audit"]["status"] == "PASS"


def test_a_drop_smaller_than_one_percent_does_not_enter() -> None:
    bars = [
        _five("ABC", "2024-06-04", 9, 15, "99.5", "99.5", "99.5", "99.5"),
        _five("ABC", "2024-06-04", 9, 20, "99.5", "99.5", "99.5", "99.5"),
    ]
    result = simulate_portfolio(bars, [_daily("ABC", "2024-06-03", "100")])
    assert result["entries"] == 0
    assert result["signals"] == 0


def test_same_day_two_percent_target_fills_and_does_not_use_the_entry_bar() -> None:
    bars, daily = _book(
        later=[
            ("2024-06-04", 9, 25, "100", "103", "100", "101"),
        ]
    )
    result = simulate_portfolio(bars, daily)
    assert result["exits"] == 1
    exit_row = result["closed"][0]
    assert exit_row["holding"] == "same_session"
    assert Decimal(exit_row["price"]) == Decimal("102.00")
    assert exit_row["reason"] == "target"
    assert result["open_positions"] == []


def test_entry_bar_high_does_not_exit() -> None:
    bars = [
        _five("ABC", "2024-06-04", 9, 15, "99", "99", "99", "99"),
        _five("ABC", "2024-06-04", 9, 20, "100", "110", "100", "100"),
        _five("ABC", "2024-06-04", 9, 25, "100", "101", "100", "100"),
    ]
    result = simulate_portfolio(bars, [_daily("ABC", "2024-06-03", "100")])
    assert result["exits"] == 0
    assert result["open_positions"]


def test_later_session_uses_five_percent_from_the_original_entry() -> None:
    bars, daily = _book(
        later=[
            ("2024-06-04", 9, 25, "100", "101", "100", "100"),
            ("2024-06-05", 9, 15, "104", "104", "104", "104"),
            ("2024-06-06", 9, 15, "104", "105", "104", "104"),
        ]
    )
    result = simulate_portfolio(bars, daily)
    assert result["exits"] == 1
    exit_row = result["closed"][0]
    assert exit_row["holding"] == "overnight"
    assert exit_row["exit_session"] == "2024-06-06"
    assert Decimal(exit_row["price"]) == Decimal("105.00")
    assert Decimal(exit_row["target_price"]) == Decimal("105.00")


def test_there_is_no_stop_and_no_end_of_day_flatten() -> None:
    bars, daily = _book(
        later=[
            ("2024-06-04", 15, 25, "90", "90", "50", "80"),
            ("2024-06-05", 9, 15, "70", "70", "40", "60"),
        ]
    )
    result = simulate_portfolio(bars, daily)
    assert result["exits"] == 0
    assert len(result["open_positions"]) == 1
    assert result["open_positions"][0]["reason"] == "unresolved"


def test_a_gap_through_the_target_fills_at_the_open() -> None:
    bars, daily = _book(later=[("2024-06-05", 9, 15, "110", "110", "110", "110")])
    result = simulate_portfolio(bars, daily)
    assert Decimal(result["closed"][0]["price"]) == Decimal("110")
    assert result["closed"][0]["holding"] == "overnight"


def test_same_session_and_overnight_charges_differ() -> None:
    same_bars, same_daily = _book(later=[("2024-06-04", 9, 25, "100", "102", "100", "102")])
    overnight_bars, overnight_daily = _book(later=[("2024-06-05", 9, 15, "105", "105", "105", "105")])
    same = simulate_portfolio(same_bars, same_daily)
    overnight = simulate_portfolio(overnight_bars, overnight_daily)
    same_exit = same["closed"][0]["exit_charges"]
    overnight_exit = overnight["closed"][0]["exit_charges"]
    assert Decimal(same_exit["brokerage"]) > 0
    assert Decimal(same_exit["dp"]) == 0
    assert Decimal(same_exit["stt"]) > 0
    assert Decimal(overnight_exit["brokerage"]) == 0
    assert Decimal(overnight_exit["dp"]) == Decimal("15.34")
    assert Decimal(overnight["closed"][0]["entry_charges"]) > 0
    zero = simulate_portfolio(same_bars, same_daily, brokerage=False)
    assert Decimal(zero["closed"][0]["exit_charges"]["brokerage"]) == 0
    assert Decimal(zero["closed"][0]["exit_charges"]["stt"]) > 0


def test_charge_components_match_the_published_schedule() -> None:
    notional = Decimal("10000")
    buy = delivery_buy(notional)
    sell = delivery_sell(notional)
    assert buy.brokerage == 0
    assert buy.stt == Decimal("10.00")
    assert buy.stamp == Decimal("1.50")
    assert buy.dp == 0
    assert sell.dp == Decimal("15.34")
    assert sell.stt == Decimal("10.00")
    intra_sell = intraday_sell(notional)
    assert intra_sell.brokerage == Decimal("3.00")
    assert intra_sell.stt == Decimal("2.50")
    assert intra_sell.dp == 0
    assert intraday_buy(notional, brokerage=False).brokerage == 0
    assert intraday_buy(notional, brokerage=False).stamp == Decimal("0.30")


def test_quantity_is_a_whole_share_count_and_an_over_cap_price_is_rejected() -> None:
    bars, daily = _book(entry_open="100")
    result = simulate_portfolio(bars, daily)
    assert result["events"][0]["quantity"] == 200
    expensive = [
        _five("ABC", "2024-06-04", 9, 15, "99", "99", "99", "99"),
        _five("ABC", "2024-06-04", 9, 20, "25000", "25000", "25000", "25000"),
    ]
    rejected = simulate_portfolio(expensive, [_daily("ABC", "2024-06-03", "100")])
    assert rejected["entries"] == 0
    assert rejected["rejected"][0]["reason"] == "over_cap"


def test_insufficient_cash_rejects_the_later_symbol_in_name_order() -> None:
    daily = [_daily("BBB", "2024-06-03", "100"), _daily("AAA", "2024-06-03", "100")]
    bars = []
    for symbol in ("BBB", "AAA"):
        bars.extend(
            [
                _five(symbol, "2024-06-04", 9, 15, "99", "99", "99", "99"),
                _five(symbol, "2024-06-04", 9, 20, "100", "100", "100", "100"),
            ]
        )
    result = simulate_portfolio(bars, daily, starting_cash=Decimal("25000"))
    assert [row["symbol"] for row in result["events"] if row["event"] == "entry"] == ["AAA"]
    assert result["rejected"][0]["symbol"] == "BBB"
    assert result["rejected"][0]["reason"] == "insufficient_cash"


def test_one_open_position_per_symbol() -> None:
    bars = [
        _five("ABC", "2024-06-04", 9, 15, "99", "99", "99", "99"),
        _five("ABC", "2024-06-04", 9, 20, "100", "100", "100", "100"),
        _five("ABC", "2024-06-04", 9, 25, "90", "90", "90", "90"),
        _five("ABC", "2024-06-04", 9, 30, "90", "90", "90", "90"),
    ]
    result = simulate_portfolio(bars, [_daily("ABC", "2024-06-03", "100")])
    assert result["entries"] == 1


def test_a_missing_next_bar_does_not_invent_an_entry_or_a_mark() -> None:
    bars = [_five("AAA", "2024-06-04", 9, 15, "99", "99", "99", "99")]
    bars.append(_five("BBB", "2024-06-05", 9, 15, "100", "100", "100", "100"))
    daily = [_daily("AAA", "2024-06-03", "100"), _daily("BBB", "2024-06-03", "100")]
    result = simulate_portfolio(bars, daily)
    assert result["entries"] == 0
    assert all(row["symbol"] != "AAA" for row in result["open_positions"])


def test_stale_marks_are_flagged_and_are_not_exits() -> None:
    bars = [
        _five("AAA", "2024-06-04", 9, 15, "99", "99", "99", "99"),
        _five("AAA", "2024-06-04", 9, 20, "100", "100", "100", "100"),
        _five("BBB", "2024-06-05", 9, 15, "50", "50", "50", "50"),
    ]
    daily = [_daily("AAA", "2024-06-03", "100"), _daily("BBB", "2024-06-03", "100")]
    result = simulate_portfolio(bars, daily)
    second = result["days"][1]
    holding = next(row for row in second["holdings"] if row["symbol"] == "AAA")
    assert holding["stale_mark"] is True
    assert result["exits"] == 0
    assert Decimal(holding["mark_price"]) == Decimal("100")


def test_daily_cash_cost_basis_and_equity_reconcile() -> None:
    bars, daily = _book(later=[("2024-06-04", 9, 25, "100", "102", "100", "102")])
    result = simulate_portfolio(bars, daily, starting_cash=Decimal("100000"))
    day = result["days"][0]
    assert day["cash_reconciled"] is True
    assert Decimal(day["opening_cash"]) == Decimal("100000")
    assert Decimal(day["equity"]) == Decimal(day["closing_cash"]) + Decimal(day["market_value"])
    assert result["open_positions"] == []
    closed = result["closed"][0]
    gross = Decimal(closed["gross_pnl"])
    net = Decimal(closed["net_pnl"])
    assert net < gross
    assert Decimal(result["realized_net_pnl"]) == net
    assert Decimal(day["unrealized_net_pnl"]) == 0


def test_loss_inventory_lists_open_losers_without_realizing_them() -> None:
    bars, daily = _book(later=[("2024-06-04", 15, 25, "90", "90", "80", "90")])
    result = simulate_portfolio(bars, daily)
    day = result["days"][0]
    assert day["positions_in_loss"] == 1
    assert result["exits"] == 0
    loser = day["loss_inventory"][0]
    assert loser["symbol"] == "ABC"
    assert Decimal(loser["unrealized_net_pnl"]) < 0
    assert Decimal(loser["market_value"]) < Decimal(loser["cost_basis"])
    assert Decimal(day["capital_in_loss"]) == Decimal(loser["cost_basis"])
    assert "unrealized" not in loser["status"]


def test_unresolved_positions_remain_open_at_the_sample_end() -> None:
    bars, daily = _book()
    result = simulate_portfolio(bars, daily)
    assert result["exits"] == 0
    assert result["open_positions"][0]["reason"] == "unresolved"
    assert result["open_positions"][0]["live_enabled"] is False
    assert result["audit"]["status"] == "PASS"


def test_two_losers_are_sorted_by_the_larger_net_loss() -> None:
    bars = []
    daily = []
    for symbol, close in (("AAA", "90"), ("BBB", "70")):
        daily.append(_daily(symbol, "2024-06-03", "100"))
        bars.extend(
            [
                _five(symbol, "2024-06-04", 9, 15, "99", "99", "99", "99"),
                _five(symbol, "2024-06-04", 9, 20, "100", "100", close, close),
            ]
        )
    result = simulate_portfolio(bars, daily)
    names = [row["symbol"] for row in result["days"][0]["loss_inventory"]]
    assert names == ["BBB", "AAA"]

"""Synthetic paths for the combined three-algo book."""

import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from contracts.enums import Timeframe
from contracts.schemas.market import Candle
from core_features.engine import _ema
from core_paper.execute import MAX_NOTIONAL

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "quant" / "src"))

from quant_agents.research.combined_three import (
    ORDER_CAP,
    SYMBOL_CAP,
    BookConfig,
    _Intent,
    _Lot,
    _dip_exit,
    attempt_fills,
    measure,
    passes,
    simulate_symbol,
)

IST = ZoneInfo("Asia/Kolkata")


def _at(day: str, hour: int, minute: int) -> datetime:
    local = datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00").replace(tzinfo=IST)
    return local.astimezone(timezone.utc)


def _bar(day: str, hour: int, minute: int, open_: str, high: str, low: str, close: str, volume: int = 1) -> Candle:
    start = _at(day, hour, minute)
    return Candle(
        symbol="ABC",
        exchange="NSE",
        timeframe=Timeframe.M5,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
        start=start,
        end=start + timedelta(minutes=5),
    )


def _daily(day: str, close: str, high: str | None = None) -> Candle:
    start = _at(day, 9, 15)
    top = close if high is None else high
    return Candle(
        symbol="ABC",
        exchange="NSE",
        timeframe=Timeframe.D1,
        open=Decimal(close),
        high=Decimal(top),
        low=Decimal(close),
        close=Decimal(close),
        volume=1,
        start=start,
        end=start + timedelta(hours=6, minutes=15),
    )


def _days(count: int, start: str = "2024-01-02") -> list[str]:
    first = date.fromisoformat(start)
    return [(first + timedelta(days=offset)).isoformat() for offset in range(count)]


def _flat_history(days: list[str], close: str = "100", high: str = "110") -> list[Candle]:
    return [_daily(day, close, high) for day in days]


def _volume_days(days: list[str], hour: int, minute: int, volume: int = 100) -> list[Candle]:
    return [_bar(day, hour, minute, "100", "100", "100", "100", volume) for day in days]


def test_paper_order_cap_is_unchanged() -> None:
    assert MAX_NOTIONAL == Decimal("20000")
    assert ORDER_CAP == Decimal("20000")
    assert SYMBOL_CAP == Decimal("40000")


def test_two_dip_tranches_stop_at_40000() -> None:
    days = _days(24)
    closes = [Decimal("100")] * 20 + [Decimal("99"), Decimal("98"), Decimal("97")]
    daily = [_daily(day, format(close, "f"), format(close, "f")) for day, close in zip(days[:23], closes, strict=True)]
    ema = Decimal(str(_ema([float(close) for close in closes], 20)[-1]))
    signal = ema * Decimal("0.91")
    assert Decimal("-12") <= (signal - ema) / ema * Decimal(100) <= Decimal("-8")
    signal_day = days[23]
    later = (date.fromisoformat(signal_day) + timedelta(days=1)).isoformat()
    daily.append(_daily(signal_day, format(signal, "f"), format(signal, "f")))
    daily.append(_daily(later, format(signal, "f"), format(signal, "f")))
    wide = signal * Decimal("1.02")
    bars = [
        _bar(signal_day, 9, 40, format(signal, "f"), format(signal, "f"), format(signal, "f"), format(signal, "f")),
        _bar(signal_day, 9, 45, "100", "100", "100", "100"),
        _bar(signal_day, 10, 55, "100", "100", "100", "100", 10),
        *_volume_days(days[13:23], 10, 55, 10),
        _bar(later, 10, 55, format(wide, "f"), format(wide, "f"), format(wide, "f"), format(wide, "f"), 100),
        _bar(later, 11, 0, "90", "90", "90", "90", 100),
    ]
    closed, marks = simulate_symbol("ABC", bars, daily)
    assert closed == []
    dips = [row for row in marks if row["algo"] == "dip"]
    assert [row["tranche"] for row in dips] == [1, 2]
    assert sum(row["entry_notional"] for row in dips) == SYMBOL_CAP
    assert not any(row["algo"] == "wide" for row in marks)
    assert all(row["exit_reason"] != "stop" for row in closed)


def test_dip_tranches_use_their_own_targets_and_do_not_stop() -> None:
    days = _days(24)
    closes = [Decimal("100")] * 20 + [Decimal("99"), Decimal("98"), Decimal("97")]
    daily = [_daily(day, format(close, "f"), format(close, "f")) for day, close in zip(days[:23], closes, strict=True)]
    ema = Decimal(str(_ema([float(close) for close in closes], 20)[-1]))
    signal = ema * Decimal("0.91")
    signal_day = days[23]
    entry = signal
    first_target = entry * Decimal("1.02")
    second_target = ema * Decimal("1.03")
    assert first_target < second_target
    crashed = entry * Decimal("0.80")
    bars = [
        _bar(signal_day, 9, 40, format(signal, "f"), format(signal, "f"), format(signal, "f"), format(signal, "f")),
        _bar(signal_day, 9, 45, format(entry, "f"), format(entry, "f"), format(entry, "f"), format(entry, "f")),
        _bar(signal_day, 10, 0, format(crashed, "f"), format(crashed, "f"), format(entry * Decimal("0.70"), "f"), format(entry * Decimal("0.75"), "f")),
        _bar(signal_day, 10, 5, format(entry, "f"), format(first_target, "f"), format(entry, "f"), format(first_target, "f")),
        _bar(signal_day, 10, 10, format(first_target, "f"), format(second_target, "f"), format(first_target, "f"), format(second_target, "f")),
    ]
    closed, marks = simulate_symbol("ABC", bars, daily)
    reasons = {(row["tranche"], row["exit_reason"], row["exit_price"]) for row in closed}
    assert (1, "target_2pct", first_target) in reasons
    assert (2, "ema_plus_3", second_target) in reasons
    assert marks == []
    assert all(row["exit_reason"] != "stop" for row in closed)


def test_wide_sells_half_at_two_percent_and_the_rest_on_a_one_percent_pullback() -> None:
    days = _days(21)
    daily = _flat_history(days[:20], "100", "100")
    signal_day = days[20]
    bars = [
        *_volume_days(days[10:20], 10, 0, 100),
        _bar(signal_day, 10, 0, "102", "102", "102", "102", 300),
        _bar(signal_day, 10, 5, "100", "100", "100", "100", 1),
        _bar(signal_day, 10, 10, "100", "103", "100", "103", 1),
        _bar(signal_day, 10, 15, "103", "103", "101.90", "102", 1),
    ]
    closed, marks = simulate_symbol("ABC", bars, daily)
    assert marks == []
    assert [row["exit_reason"] for row in closed] == ["half_2pct", "retrace_1pct"]
    assert closed[0]["quantity"] == 100
    assert closed[0]["exit_price"] == Decimal("102")
    assert closed[1]["quantity"] == 100
    assert closed[1]["exit_price"] == Decimal("103") * Decimal("0.99")
    assert all(row["exit_reason"] != "stop" for row in closed)


def test_narrow_holds_a_loser_and_sells_on_a_later_profitable_close() -> None:
    days = _days(22)
    daily = _flat_history(days[:20], "100", "110")
    signal_day = days[20]
    later = days[21]
    bars = [
        *_volume_days(days[10:20], 10, 10, 100),
        _bar(signal_day, 10, 0, "100.2", "100.4", "100.2", "100.3", 100),
        _bar(signal_day, 10, 5, "100.3", "100.5", "100.3", "100.4", 100),
        _bar(signal_day, 10, 10, "100.4", "100.7", "100.4", "100.6", 100),
        _bar(signal_day, 10, 15, "100.6", "100.6", "100.6", "100.6", 1),
        _bar(signal_day, 15, 10, "90", "90", "80", "80", 1),
    ]
    held, held_marks = simulate_symbol("ABC", bars, daily)
    assert held == []
    assert len(held_marks) == 1
    assert held_marks[0]["algo"] == "narrow"
    assert held_marks[0]["unrealized_net"] < 0
    bars.append(_bar(later, 15, 10, "110", "110", "110", "110", 1))
    closed, marks = simulate_symbol("ABC", bars, daily)
    assert marks == []
    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "eod_positive"
    assert closed[0]["exit_price"] == Decimal("110")
    assert session_date_ist(closed[0]["exit_time"]) == later
    assert closed[0]["net_pnl"] > 0


def session_date_ist(moment: datetime) -> str:
    return moment.astimezone(IST).date().isoformat()


def _lot(algo: str, tranche: int, price: str, quantity: int) -> _Lot:
    return _Lot(
        algo=algo,
        tranche=tranche,
        signal_time=_at("2024-02-01", 9, 45),
        signal_price=Decimal(price),
        entry_time=_at("2024-02-01", 9, 45),
        entry_bar_end=_at("2024-02-01", 9, 50),
        entry_session=date.fromisoformat("2024-02-01"),
        entry_price=Decimal(price),
        quantity=quantity,
        remaining=quantity,
        half_qty=quantity // 2,
    )


def test_dip_guard_keeps_a_tranche_whose_sale_does_not_clear_charges() -> None:
    lot = _lot("dip", 2, "102.90", 194)
    guarded = BookConfig(dip_cost_guard=True)
    held = _dip_exit(lot, _bar("2024-02-01", 10, 0, "103", "103", "103", "103"), Decimal("100"), guarded)
    assert held == []
    assert lot.remaining == 194
    sold = _dip_exit(lot, _bar("2024-02-01", 10, 5, "110", "110", "110", "110"), Decimal("100"), guarded)
    assert sold[0]["exit_reason"] == "ema_plus_3"
    assert sold[0]["net_pnl"] > 0
    assert sold[0]["quantity"] == 194


def test_tranche1_guard_keeps_a_target_sale_that_does_not_clear_charges() -> None:
    lot = _lot("dip", 1, "100", 4)
    guarded = BookConfig(dip_tranche1_guard=True)
    held = _dip_exit(lot, _bar("2024-02-02", 10, 0, "102", "102", "102", "102"), None, guarded)
    assert held == []
    assert lot.remaining == 4
    sold = _dip_exit(lot, _bar("2024-02-02", 10, 5, "120", "120", "120", "120"), None, guarded)
    assert sold[0]["exit_reason"] == "target_2pct"
    assert sold[0]["quantity"] == 4
    assert sold[0]["net_pnl"] > 0
    full = _lot("dip", 1, "100", 200)
    cleared = _dip_exit(full, _bar("2024-02-02", 10, 0, "102", "102", "102", "102"), None, guarded)
    assert cleared[0]["quantity"] == 200
    assert cleared[0]["net_pnl"] > 0


def _wide_entry() -> tuple[list[str], list[Candle], list[Candle]]:
    days = _days(23)
    daily = _flat_history(days[:20], "100", "100")
    bars = [
        *_volume_days(days[10:20], 10, 0, 100),
        _bar(days[20], 10, 0, "102", "102", "102", "102", 300),
        _bar(days[20], 10, 5, "100", "100", "100", "100", 1),
    ]
    return days, daily, bars


def test_time_exit_is_decided_at_1515_and_sold_on_the_next_session_open() -> None:
    days, daily, bars = _wide_entry()
    bars.append(_bar(days[21], 15, 10, "95", "95", "95", "95", 1))
    book = BookConfig(wide_retrace=False, slippage_bps=Decimal("5"), time_exit_days=1)
    held, marks = simulate_symbol("ABC", bars, daily, book)
    assert held == []
    assert marks[0]["exit_due"] == date.fromisoformat(days[21])
    bars.append(_bar(days[22], 9, 15, "96", "96", "96", "96", 1))
    closed, marks = simulate_symbol("ABC", bars, daily, book)
    assert marks == []
    assert closed[0]["exit_reason"] == "time_exit"
    assert closed[0]["exit_price"] == Decimal("96") * Decimal("0.9995")
    assert closed[0]["entry_price"] == Decimal("100") * Decimal("1.0005")
    assert closed[0]["charges"] > 0
    assert closed[0]["net_pnl"] < 0
    assert session_date_ist(closed[0]["exit_time"]) == days[22]


def test_a_disabled_strategy_does_not_enter() -> None:
    _days_list, daily, bars = _wide_entry()
    _closed, marks = simulate_symbol("ABC", bars, daily)
    assert [row["algo"] for row in marks] == ["wide"]
    _closed, marks = simulate_symbol("ABC", bars, daily, BookConfig(wide_enabled=False))
    assert marks == []


def test_same_session_announcement_blocks_entry_but_a_later_one_does_not() -> None:
    days, daily, bars = _wide_entry()
    book = BookConfig(news_block=True)
    blocked: list[dict] = []
    _closed, marks = simulate_symbol("ABC", bars, daily, book, announcements=[_at(days[20], 9, 30)], blocked=blocked)
    assert marks == []
    assert [(row["algo"], row["tranche"]) for row in blocked] == [("wide", 1)]
    blocked = []
    _closed, marks = simulate_symbol("ABC", bars, daily, book, announcements=[_at(days[20], 10, 30)], blocked=blocked)
    assert [row["algo"] for row in marks] == ["wide"]
    assert blocked == []
    _closed, marks = simulate_symbol("ABC", bars, daily, book, announcements=[_at(days[19], 16, 0)], blocked=blocked)
    assert [row["algo"] for row in marks] == ["wide"]


def test_wide_upper_cap_blocks_a_three_and_a_half_percent_day() -> None:
    days = _days(21)
    daily = _flat_history(days[:20])
    signal_day = days[20]
    bars = [
        *_volume_days(days[10:20], 10, 0, 100),
        _bar(signal_day, 10, 0, "103.5", "103.5", "103.5", "103.5", 300),
        _bar(signal_day, 10, 5, "100", "100", "100", "100", 1),
    ]
    _closed, capped = simulate_symbol("ABC", bars, daily, BookConfig(wide_gain_max=Decimal("3")))
    assert not any(row["algo"] == "wide" for row in capped)
    _closed, baseline = simulate_symbol("ABC", bars, daily)
    assert any(row["algo"] == "wide" for row in baseline)


def test_no_second_tranche_stops_averaging_down() -> None:
    days = _days(24)
    closes = [Decimal("100")] * 20 + [Decimal("99"), Decimal("98"), Decimal("97")]
    daily = [_daily(day, format(close, "f"), format(close, "f")) for day, close in zip(days[:23], closes, strict=True)]
    ema = Decimal(str(_ema([float(close) for close in closes], 20)[-1]))
    signal = ema * Decimal("0.91")
    signal_day = days[23]
    daily.append(_daily(signal_day, format(signal, "f"), format(signal, "f")))
    bars = [
        _bar(signal_day, 9, 40, format(signal, "f"), format(signal, "f"), format(signal, "f"), format(signal, "f")),
        _bar(signal_day, 9, 45, format(signal, "f"), format(signal, "f"), format(signal, "f"), format(signal, "f")),
    ]
    _closed, marks = simulate_symbol("ABC", bars, daily, BookConfig(dip_second=False))
    assert [row["tranche"] for row in marks] == [1]


def test_same_bar_priority_records_the_rejected_dip() -> None:
    bar = _bar("2024-02-01", 10, 0, "100", "100", "100", "100")
    lots = [_lot("narrow", 1, "100", 200)]
    intents = [
        _Intent("dip", 1, _at("2024-02-01", 9, 45), Decimal("100"), date.fromisoformat("2024-02-01")),
        _Intent("wide", 1, _at("2024-02-01", 9, 45), Decimal("100"), date.fromisoformat("2024-02-01")),
    ]
    rejected: list[dict] = []
    attempt_fills(intents, bar, lots, "ABC", BookConfig(), rejected)
    assert [lot.algo for lot in lots] == ["narrow", "wide"]
    assert rejected[0]["algo"] == "dip"
    assert rejected[0]["reason"] == "symbol_cap"
    assert rejected[0]["symbol"] == "ABC"


def test_report_includes_unrealized_net_drawdown_and_open_book() -> None:
    first = _at("2024-02-01", 15, 10)
    second = _at("2024-02-02", 15, 10)
    path = [[
        {"time": first, "realized": Decimal("0"), "unrealized": Decimal("100"), "open_notional": Decimal("20000"), "open_count": 1},
        {"time": second, "realized": Decimal("0"), "unrealized": Decimal("-50"), "open_notional": Decimal("20000"), "open_count": 1},
    ]]
    metrics = measure([], [], path)
    assert Decimal(str(metrics["unrealized_net"])) == 0
    assert Decimal(str(metrics["max_drawdown"])) == Decimal("150")
    assert metrics["open_positions"] == 0
    assert Decimal(str(metrics["ending_open_notional"])) == 0
    baseline = {"total_net": "10", "average_open_notional": "100", "max_drawdown": "5"}
    assert passes({"total_net": "12", "average_open_notional": "100", "max_drawdown": "5"}, baseline)
    assert not passes({"total_net": "12", "average_open_notional": "90", "max_drawdown": "6"}, baseline)

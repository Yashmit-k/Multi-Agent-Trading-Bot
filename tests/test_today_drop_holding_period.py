"""Fixed-horizon exits for the frozen today-drop entry."""

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from contracts.enums import Timeframe
from contracts.schemas.market import Candle

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "quant" / "src"))

from quant_agents.research.rebound import price_trade
from quant_agents.research.today_drop_holding_period import lookahead_audit, session_date, simulate_fixed_hold

IST = ZoneInfo("Asia/Kolkata")


def _at(day: str, hour: int, minute: int) -> datetime:
    local = datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00").replace(tzinfo=IST)
    return local.astimezone(timezone.utc)


def _bar(timeframe: str, start: datetime, open_: str, high: str, low: str, close: str) -> Candle:
    end = start + (timedelta(minutes=5) if timeframe == "5m" else timedelta(hours=6, minutes=15))
    return Candle(
        symbol="ABC",
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
    return _bar("1d", _at(day, 9, 15), close, close, close, close)


def _five(day: str, hour: int, minute: int, open_: str, close: str) -> Candle:
    return _bar("5m", _at(day, hour, minute), open_, max(open_, close), min(open_, close), close)


def _sample() -> tuple[list[Candle], list[Candle]]:
    daily = [
        _daily("2024-06-03", "100"),
        _daily("2024-06-04", "50"),
        _daily("2024-06-05", "101"),
        _daily("2024-06-06", "102"),
    ]
    bars = [
        _five("2024-06-04", 9, 15, "99", "99"),
        _five("2024-06-04", 9, 20, "97", "97"),
        _five("2024-06-05", 10, 0, "49", "49"),
        _five("2024-06-05", 10, 5, "49", "49"),
        _five("2024-06-06", 10, 0, "100", "100"),
    ]
    return bars, daily


def test_one_day_exits_at_the_next_session_close_not_the_entry_close() -> None:
    bars, daily = _sample()
    trades = simulate_fixed_hold("ABC", bars, daily, 1)
    assert len(trades) == 1
    trade = trades[0]
    assert trade["previous_close"] == Decimal("100")
    assert trade["signal_price"] == Decimal("99")
    assert trade["entry_price"] == Decimal("97")
    assert trade["quantity"] == 206
    assert trade["exit_price"] == Decimal("101")
    assert session_date(trade["exit_time"]) == session_date(_at("2024-06-05", 15, 30))
    assert trade["exit_price"] != Decimal("50")


def test_two_day_hold_blocks_a_second_signal_and_three_days_stay_unresolved() -> None:
    bars, daily = _sample()
    held = simulate_fixed_hold("ABC", bars, daily, 2)
    assert len(held) == 1
    assert held[0]["exit_price"] == Decimal("102")
    missing = simulate_fixed_hold("ABC", bars, daily, 3)
    assert len(missing) == 1
    assert missing[0]["exit_reason"] == "unresolved"
    assert missing[0]["exit_price"] is None
    priced = [price_trade(held[0], bps) for bps in (Decimal("0"), Decimal("5"))]
    assert priced[0]["exit_price"] == priced[1]["exit_price"]
    assert priced[1]["net_pnl"] < priced[0]["net_pnl"]
    sessions = {
        "ABC": [session_date(bar.end) for bar in daily],
    }
    audit = lookahead_audit(held + missing, sessions)
    assert audit["status"] == "PASS"


def test_a_drop_smaller_than_one_percent_does_not_enter() -> None:
    bars, daily = _sample()
    bars[0] = _five("2024-06-04", 9, 15, "99.5", "99.5")
    bars[2] = _five("2024-06-05", 10, 0, "50", "50")
    assert simulate_fixed_hold("ABC", bars, daily, 1) == []

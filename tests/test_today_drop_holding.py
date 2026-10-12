"""Point-in-time checks for the today-drop holding-period diagnostic."""

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from contracts.enums import Timeframe
from contracts.schemas.market import Candle

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "quant" / "src"))

from quant_agents.research.rebound import simulate_symbol
from quant_agents.research.today_drop_holding import lookahead_audit, measure_path, net_return

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


def _book() -> tuple[dict, list[Candle], list[Candle]]:
    daily = [
        _bar("1d", _at("2024-06-03", 9, 15), "100", "100", "100", "100"),
        _bar("1d", _at("2024-06-04", 9, 15), "97", "110", "90", "101"),
        _bar("1d", _at("2024-06-05", 9, 15), "101", "103", "100", "102"),
    ]
    bars = [
        _bar("5m", _at("2024-06-03", 10, 0), "100", "500", "100", "100"),
        _bar("5m", _at("2024-06-04", 9, 15), "99", "99", "98", "98"),
        _bar("5m", _at("2024-06-04", 9, 20), "97", "97", "97", "97"),
        _bar("5m", _at("2024-06-04", 9, 25), "97", "110", "90", "100"),
        _bar("5m", _at("2024-06-05", 10, 0), "101", "103", "100", "102"),
    ]
    trades = simulate_symbol("ABC", bars, daily, variants=("baseline_today_drop",), modes=("delivery",))
    assert len(trades) == 1
    return trades[0], bars, daily


def test_path_uses_the_next_open_and_only_later_bars() -> None:
    trade, bars, daily = _book()
    assert trade["previous_close"] == Decimal("100")
    assert trade["signal_price"] == Decimal("98")
    assert trade["entry_price"] == Decimal("97")
    assert trade["exit_reason"] == "stop"
    path = measure_path(trade, bars, daily)
    first, second, third = path["checkpoints"][:3]
    assert first["status"] == "resolved"
    assert first["close"] == Decimal("101")
    assert first["gross_return"] == Decimal("101") / Decimal("97") - 1
    assert first["mfe"] == Decimal("110") / Decimal("97") - 1
    assert first["mae"] == Decimal("90") / Decimal("97") - 1
    assert first["original_exit"] == "stop"
    assert second["close"] == Decimal("102")
    assert third["status"] == "unresolved"
    assert first["net_0bp"].quantize(Decimal("0.00000001")) == first["gross_return"].quantize(Decimal("0.00000001"))
    assert net_return(Decimal("97"), Decimal("101"), trade["quantity"], Decimal("5")) == first["net_5bp"]
    audit = lookahead_audit([trade], [path])
    assert audit["status"] == "PASS"


def test_a_daily_bar_that_ends_before_entry_is_not_a_horizon() -> None:
    trade, bars, daily = _book()
    path = measure_path(trade, bars, daily)
    assert path["checkpoints"][0]["close_time"] > trade["entry_time"]
    assert path["checkpoints"][0]["close"] != Decimal("100")

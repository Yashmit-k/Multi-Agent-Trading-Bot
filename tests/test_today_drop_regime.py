"""Point-in-time checks for today-drop regime labels."""

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from contracts.enums import Timeframe
from contracts.schemas.market import Candle

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "quant" / "src"))

from quant_agents.research.today_drop_regime import IndexView

IST = ZoneInfo("Asia/Kolkata")


def _at(day: str, hour: int, minute: int) -> datetime:
    local = datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00").replace(tzinfo=IST)
    return local.astimezone(timezone.utc)


def _bar(symbol: str, timeframe: str, start: datetime, close: str, *, minutes: int = 5) -> Candle:
    return Candle(
        symbol=symbol,
        exchange="NSE",
        timeframe=Timeframe(timeframe),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=1,
        start=start,
        end=start + timedelta(minutes=minutes),
    )


def test_regime_ignores_the_signal_bar_same_day_close_and_future_vix() -> None:
    daily = []
    day = datetime(2024, 5, 1, tzinfo=timezone.utc).date()
    while len(daily) < 25:
        if day.weekday() < 5:
            daily.append(_bar("NIFTY50", "1d", _at(day.isoformat(), 9, 15), "100", minutes=375))
        day = day + timedelta(days=1)
    signal_day = daily[-1].end.astimezone(IST).date() + timedelta(days=1)
    while signal_day.weekday() >= 5:
        signal_day = signal_day + timedelta(days=1)
    signal = _at(signal_day.isoformat(), 10, 0)
    same_day = _bar("NIFTY50", "1d", _at(signal_day.isoformat(), 9, 15), "90", minutes=45)
    before = _bar("NIFTY50", "5m", _at(signal_day.isoformat(), 9, 50), "99.5")
    same_stamp = _bar("NIFTY50", "5m", _at(signal_day.isoformat(), 9, 55), "80")
    assert same_stamp.end == signal
    later = _bar("NIFTY50", "5m", _at(signal_day.isoformat(), 10, 0), "70")
    vix_daily = []
    for index, bar in enumerate(daily[:20]):
        close = "10" if index < 10 else "20"
        vix_daily.append(_bar("INDIAVIX", "1d", bar.start, close, minutes=375))
    future_day = signal_day + timedelta(days=1)
    vix_daily.append(_bar("INDIAVIX", "1d", _at(future_day.isoformat(), 9, 15), "100", minutes=375))
    vix_now = _bar("INDIAVIX", "5m", _at(signal_day.isoformat(), 9, 55), "16")
    vix_later = _bar("INDIAVIX", "5m", _at(signal_day.isoformat(), 10, 0), "5")
    view = IndexView.build([before, same_stamp, later], [*daily, same_day], [vix_now, vix_later], vix_daily)
    label = view.classify(signal)
    assert label["nifty_return_bucket"] == "-0.5% to 0%"
    assert label["nifty_return_pct"] == Decimal("-0.5")
    assert label["nifty_trend"] == "below"
    assert label["vix_level"] == Decimal("16")
    assert label["vix_bucket"] == "above_median"

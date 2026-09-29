"""Session-aligned candles. The same function serves every trading mode.

Ticks outside 09:15–15:30 IST are ignored. Bar end is the time the bar becomes
knowable. Bars whose end is after as_of are omitted.
"""

from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from contracts.enums import Exchange, Timeframe
from contracts.schemas.market import Candle


class TickLike(Protocol):
    symbol: str
    exchange: str
    timestamp: datetime
    price: Decimal
    volume: int

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)
_MINUTES = {
    Timeframe.M1: 1,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.M30: 30,
    Timeframe.H1: 60,
    Timeframe.D1: None,
}


def build_candles(ticks: list[TickLike], timeframe: Timeframe | str, as_of: datetime) -> list[Candle]:
    parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
    moment = _aware(as_of)
    grouped: dict[tuple[datetime, datetime], list[TickLike]] = defaultdict(list)
    for tick in ticks:
        stamp = _aware(tick.timestamp)
        if stamp > moment:
            continue
        window = _window(stamp, parsed)
        if window is None:
            continue
        start, end = window
        if end > moment:
            continue
        grouped[(start, end)].append(tick)
    candles: list[Candle] = []
    for (start, end), bucket in sorted(grouped.items()):
        ordered = sorted(bucket, key=lambda item: _aware(item.timestamp))
        prices = [item.price for item in ordered]
        candles.append(
            Candle(
                symbol=ordered[0].symbol,
                exchange=Exchange(ordered[0].exchange),
                timeframe=parsed,
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=sum(item.volume for item in ordered),
                start=start,
                end=end,
            )
        )
    return candles


def _window(stamp: datetime, timeframe: Timeframe) -> tuple[datetime, datetime] | None:
    local = stamp.astimezone(IST)
    if local.time() < SESSION_OPEN or local.time() >= SESSION_CLOSE:
        return None
    open_local = datetime.combine(local.date(), SESSION_OPEN, tzinfo=IST)
    close_local = datetime.combine(local.date(), SESSION_CLOSE, tzinfo=IST)
    if timeframe == Timeframe.D1:
        return open_local.astimezone(timezone.utc), close_local.astimezone(timezone.utc)
    minutes = _MINUTES[timeframe]
    assert minutes is not None
    elapsed = int((local - open_local).total_seconds() // 60)
    bucket = elapsed // minutes
    start_local = open_local + timedelta(minutes=bucket * minutes)
    end_local = start_local + timedelta(minutes=minutes)
    if end_local > close_local:
        return None
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def price(value: str) -> Decimal:
    return Decimal(value)

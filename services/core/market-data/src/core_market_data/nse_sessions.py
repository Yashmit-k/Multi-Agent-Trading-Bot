"""NSE cash session grid for 2024-01-01 through 2026-12-31.

Holiday dates match quant_agents.calendar.static_nse. A chunk is complete only
when every expected bar on that grid is already stored.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from contracts.enums import Timeframe
from contracts.schemas.market import Candle

IST = ZoneInfo("Asia/Kolkata")
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)

HOLIDAYS: frozenset[date] = frozenset(
    {
        date(2024, 1, 22),
        date(2024, 1, 26),
        date(2024, 3, 8),
        date(2024, 3, 25),
        date(2024, 3, 29),
        date(2024, 4, 11),
        date(2024, 4, 17),
        date(2024, 5, 1),
        date(2024, 5, 20),
        date(2024, 6, 17),
        date(2024, 7, 17),
        date(2024, 8, 15),
        date(2024, 10, 2),
        date(2024, 11, 1),
        date(2024, 11, 15),
        date(2024, 12, 25),
        date(2025, 2, 26),
        date(2025, 3, 14),
        date(2025, 3, 31),
        date(2025, 4, 10),
        date(2025, 4, 14),
        date(2025, 4, 18),
        date(2025, 5, 1),
        date(2025, 8, 15),
        date(2025, 8, 27),
        date(2025, 10, 2),
        date(2025, 10, 21),
        date(2025, 10, 22),
        date(2025, 11, 5),
        date(2025, 12, 25),
        date(2026, 1, 26),
        date(2026, 3, 3),
        date(2026, 3, 26),
        date(2026, 3, 31),
        date(2026, 4, 1),
        date(2026, 4, 3),
        date(2026, 4, 14),
        date(2026, 5, 1),
        date(2026, 5, 27),
        date(2026, 6, 26),
        date(2026, 8, 15),
        date(2026, 9, 14),
        date(2026, 10, 2),
        date(2026, 10, 20),
        date(2026, 11, 10),
        date(2026, 11, 24),
        date(2026, 12, 25),
    }
)


def is_trading_day(day: date) -> bool:
    if day.weekday() >= 5:
        return False
    return day not in HOLIDAYS


def expected_starts(chunk_start: datetime, chunk_end: datetime, timeframe: Timeframe) -> set[datetime]:
    """Bar starts that must exist for this chunk. Empty when the chunk holds no session."""
    start = chunk_start.astimezone(timezone.utc)
    end = chunk_end.astimezone(timezone.utc)
    if end <= start:
        return set()
    expected: set[datetime] = set()
    day = start.astimezone(IST).date()
    last = end.astimezone(IST).date()
    while day <= last:
        if is_trading_day(day):
            opened = datetime.combine(day, SESSION_OPEN, tzinfo=IST).astimezone(timezone.utc)
            closed = datetime.combine(day, SESSION_CLOSE, tzinfo=IST).astimezone(timezone.utc)
            if timeframe == Timeframe.D1:
                if opened >= start and closed <= end:
                    expected.add(opened)
            else:
                cursor = opened
                step = timedelta(minutes=5)
                while cursor + step <= closed:
                    bar_end = cursor + step
                    if cursor >= start and bar_end <= end:
                        expected.add(cursor)
                    cursor = bar_end
        day += timedelta(days=1)
    return expected


def chunk_is_complete(
    stored: list[Candle],
    chunk_start: datetime,
    chunk_end: datetime,
    timeframe: Timeframe,
) -> bool:
    expected = expected_starts(chunk_start, chunk_end, timeframe)
    if not expected:
        return True
    have = {bar.start.astimezone(timezone.utc) for bar in stored if _same_timeframe(bar, timeframe)}
    return expected <= have


def _same_timeframe(bar: Candle, timeframe: Timeframe) -> bool:
    return bar.timeframe == timeframe or str(bar.timeframe) == timeframe.value

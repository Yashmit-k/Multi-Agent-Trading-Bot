"""Completed-bar windows for NSE cash candles.

Incremental polling asks only for the gap after the last stored bar.
The 100-day seed remains a separate recovery path.
A daily bar is complete 30 minutes after the 15:30 IST close (see DAILY_OFFICIAL_DELAY). Five-minute freshness accepts the
last 15 minutes of the session as unpublished when the provider omits them.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from contracts.enums import Timeframe
from core_market_data.nse_sessions import IST, SESSION_CLOSE, SESSION_OPEN, is_trading_day

PUBLICATION_DELAY = timedelta(seconds=90)
# NSE's official closing price (the weighted average of the last 30 minutes) is published a few minutes after
# 15:30. A daily bar fetched 90 s after the close could carry the last traded price instead (JSWSTEEL, 19 Oct
# 2026: 1231.00 stored, 1241.30 official), and swing entries are priced from it. Wait until the official close.
DAILY_OFFICIAL_DELAY = timedelta(minutes=30)
CLOSE_GRACE = timedelta(minutes=15)
_FIVE = timedelta(minutes=5)


def candle_is_fresh(stored_end: datetime | None, timeframe: Timeframe, now: datetime) -> bool:
    """True when the stored bar reaches the last completed bar for this clock."""
    if stored_end is None:
        return False
    expected = expected_completed_end(timeframe, now)
    return _aware(stored_end) >= expected


def expected_completed_end(timeframe: Timeframe, now: datetime, delay: timedelta = PUBLICATION_DELAY) -> datetime:
    if timeframe == Timeframe.D1:
        return _completed_daily_end(now, max(delay, DAILY_OFFICIAL_DELAY))
    return _completed_intraday_end(now, delay)


def incremental_range(
    last_end: datetime | None,
    timeframe: Timeframe,
    now: datetime,
    delay: timedelta = PUBLICATION_DELAY,
) -> tuple[datetime, datetime] | None:
    """Return a narrow [start, end] when stored data is behind. None when caught up or unsown."""
    if last_end is None:
        return None
    expected = expected_completed_end(timeframe, now, delay)
    stored = _aware(last_end)
    if stored >= expected:
        return None
    moment = _aware(now)
    start = stored - (_FIVE if timeframe != Timeframe.D1 else timedelta(days=1))
    if start >= moment:
        return None
    return start, moment


def _completed_daily_end(now: datetime, delay: timedelta) -> datetime:
    local = _aware(now).astimezone(IST)
    day = local.date()
    if is_trading_day(day) and local >= _close(day) + delay:
        return _close(day).astimezone(timezone.utc)
    return _close(_previous_trading_day(day)).astimezone(timezone.utc)


def _completed_intraday_end(now: datetime, delay: timedelta) -> datetime:
    local = _aware(now).astimezone(IST)
    day = local.date()
    if not is_trading_day(day):
        return (_close(_last_trading_day(day)) - CLOSE_GRACE).astimezone(timezone.utc)
    opened = _open(day)
    closed = _close(day)
    ready = local - delay
    if ready < opened + _FIVE:
        return (_close(_previous_trading_day(day)) - CLOSE_GRACE).astimezone(timezone.utc)
    if ready >= closed:
        return (closed - CLOSE_GRACE).astimezone(timezone.utc)
    elapsed = ready - opened
    steps = int(elapsed.total_seconds() // _FIVE.total_seconds())
    end = opened + (steps * _FIVE)
    return end.astimezone(timezone.utc)


def _previous_trading_day(day: date) -> date:
    cursor = day - timedelta(days=1)
    while not is_trading_day(cursor):
        cursor -= timedelta(days=1)
    return cursor


def _last_trading_day(day: date) -> date:
    cursor = day
    while not is_trading_day(cursor):
        cursor -= timedelta(days=1)
    return cursor


def _open(day: date) -> datetime:
    return datetime.combine(day, SESSION_OPEN, tzinfo=IST)


def _close(day: date) -> datetime:
    return datetime.combine(day, SESSION_CLOSE, tzinfo=IST)


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)

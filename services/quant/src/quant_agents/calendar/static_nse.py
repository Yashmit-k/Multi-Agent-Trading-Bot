"""Temporary NSE cash-market calendar.

Coverage: 2024-01-01 through 2026-12-31 inclusive.
Session: [09:15:00, 15:30:00) Asia/Kolkata. 15:30:00 IST is closed.
Not covered: Muhurat and other special sessions, dates before 2024, dates after 2026.

Holiday merge gate (verify against NSE circulars before merge):
- 2024 source: https://nsearchives.nseindia.com/content/circulars/CMTR60497.pdf
  retrieval_date: 2026-09-30
- 2025 source: https://nsearchives.nseindia.com/content/circulars/CMTR64351.pdf
  retrieval_date: 2026-09-30
- 2026 source: https://nsearchives.nseindia.com/content/circulars/CMTR70431.pdf
  retrieval_date: 2026-09-30

Lists below are the cash-market holidays published in those circulars
(excluding weekends, which this calendar already treats as non-trading).
Muhurat trading sessions are treated as closed holidays here (not special open sessions).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone, tzinfo

from quant_agents.errors import CalendarCoverageError

IST = timezone(timedelta(hours=5, minutes=30))
SESSION_OPEN = time(9, 15)
SESSION_CLOSE = time(15, 30)
FIRST_COVERED = date(2024, 1, 1)
LAST_COVERED = date(2026, 12, 31)
CALENDAR_VERSION = "static-nse-2024-2026.1"

# Verified against the circulars named in the module docstring (retrieval 2026-09-30).
HOLIDAYS_2024: frozenset[date] = frozenset(
    {
        date(2024, 1, 22),  # Special: Ram Lalla Pran Pratishtha (exchange circular)
        date(2024, 1, 26),
        date(2024, 3, 8),
        date(2024, 3, 25),
        date(2024, 3, 29),
        date(2024, 4, 11),
        date(2024, 4, 17),
        date(2024, 5, 1),
        date(2024, 5, 20),  # Parliamentary elections (Maharashtra / exchange circular)
        date(2024, 6, 17),
        date(2024, 7, 17),
        date(2024, 8, 15),
        date(2024, 10, 2),
        date(2024, 11, 1),
        date(2024, 11, 15),
        date(2024, 12, 25),
    }
)

HOLIDAYS_2025: frozenset[date] = frozenset(
    {
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
    }
)

HOLIDAYS_2026: frozenset[date] = frozenset(
    {
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

HOLIDAYS = HOLIDAYS_2024 | HOLIDAYS_2025 | HOLIDAYS_2026


def _as_ist(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise CalendarCoverageError("calendar requires timezone-aware datetimes")
    return moment.astimezone(IST)


def _to_date(moment: datetime | date) -> date:
    if isinstance(moment, datetime):
        return _as_ist(moment).date()
    return moment


class StaticNseCalendar:
    """Fail-loud static NSE calendar. Temporary until Core owns a market calendar."""

    version = CALENDAR_VERSION

    def last_covered_date(self) -> date:
        return LAST_COVERED

    def covers(self, moment: datetime | date) -> bool:
        day = _to_date(moment)
        return FIRST_COVERED <= day <= LAST_COVERED

    def _require_cover(self, moment: datetime | date, name: str) -> date:
        day = _to_date(moment)
        if not self.covers(day):
            raise CalendarCoverageError(f"{name} {day.isoformat()} is outside StaticNseCalendar coverage")
        return day

    def is_trading_day(self, day: date) -> bool:
        self._require_cover(day, "date")
        if day.weekday() >= 5:
            return False
        return day not in HOLIDAYS

    def is_session_open(self, moment: datetime) -> bool:
        if not self.covers(moment):
            return False
        local = _as_ist(moment)
        if not self.is_trading_day(local.date()):
            return False
        clock = local.timetz().replace(tzinfo=None)
        return SESSION_OPEN <= clock < SESSION_CLOSE

    def session_close(self, moment: datetime) -> datetime:
        day = self._require_cover(moment, "session_close")
        if not self.is_trading_day(day):
            raise CalendarCoverageError(f"{day.isoformat()} is not a trading day")
        close_local = datetime.combine(day, SESSION_CLOSE, tzinfo=IST)
        return close_local.astimezone(timezone.utc)

    def next_trading_day(self, day: date) -> date:
        self._require_cover(day, "next_trading_day")
        cursor = day + timedelta(days=1)
        while self.covers(cursor):
            if cursor.weekday() < 5 and cursor not in HOLIDAYS:
                return cursor
            cursor = cursor + timedelta(days=1)
        raise CalendarCoverageError("next_trading_day would leave coverage")

    def sessions_between(self, start: datetime, end: datetime) -> int:
        self._require_cover(start, "sessions_between.start")
        self._require_cover(end, "sessions_between.end")
        start_utc = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc)
        if end_utc < start_utc:
            return 0
        count = 0
        cursor = _as_ist(start).date()
        last = _as_ist(end).date()
        while cursor <= last:
            if self.covers(cursor) and cursor.weekday() < 5 and cursor not in HOLIDAYS:
                close_local = datetime.combine(cursor, SESSION_CLOSE, tzinfo=IST)
                close_utc = close_local.astimezone(timezone.utc)
                if close_utc > start_utc and close_utc <= end_utc:
                    count += 1
            cursor = cursor + timedelta(days=1)
        return count

    def add_sessions(self, moment: datetime, count: int) -> datetime:
        if count < 1:
            raise CalendarCoverageError("add_sessions count must be >= 1")
        self._require_cover(moment, "add_sessions")
        moment_utc = moment.astimezone(timezone.utc)
        found = 0
        cursor = _as_ist(moment).date()
        while self.covers(cursor):
            if cursor.weekday() < 5 and cursor not in HOLIDAYS:
                close_local = datetime.combine(cursor, SESSION_CLOSE, tzinfo=IST)
                close_utc = close_local.astimezone(timezone.utc)
                if close_utc > moment_utc:
                    found += 1
                    if found == count:
                        return close_utc
            cursor = cursor + timedelta(days=1)
        raise CalendarCoverageError("add_sessions would leave coverage")

"""NSE cash sessions used by paper entry windows.

Ordinary weekdays use the holiday list already shipped with the collector.
Saturday 18 May 2024 is a documented special live session. Mock drills and the
2026 Muhurat date are not entry sessions: Muhurat timings were not published
when this schedule was read on 2026-10-12. Dates outside the covered range
fail closed.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from core_market_data.nse_sessions import HOLIDAYS

IST = ZoneInfo("Asia/Kolkata")
CALENDAR_VERSION = "nse-cash-entry-v1"
COVERAGE_START = date(2024, 1, 1)
COVERAGE_END = date(2026, 12, 31)
ORDINARY_OPEN = time(9, 15)
ORDINARY_CLOSE = time(15, 30)
ENTRY_START = time(9, 20)
ENTRY_END = time(10, 30)
TEST_EXTENSION_DATE = date(2026, 10, 13)
TEST_EXTENSION_END = time(11, 0)
TEST_EXTENSION_SOURCE = "ordinary-cash-session+paper-test-20261013-1100"

# NSE capital-market special live session, primary site.
# Normal market 09:15–10:00 IST. The later DR segment is a different session
# and is not an automatic extension of an expired primary entry window.
# Source accessed 2026-10-12:
# https://fileserver.enrichmoney.in/Content/UploadedFiles/d5iUWAst01M8tx2hzeGjmrp2_20240516100248100.pdf
MAY18_2024 = date(2024, 5, 18)

# Mock or drill Saturdays. They are not cash sessions for paper orders.
MOCK_SATURDAYS = frozenset({date(2026, 7, 25), date(2026, 8, 29), date(2026, 10, 10)})

# NSE holiday page, accessed 2026-10-12: Muhurat trading on this date, timings
# to be notified later. Do not invent a window.
MUHURAT_UNPUBLISHED = frozenset({date(2026, 11, 8)})


class CalendarUnverified(LookupError):
    """The next session is outside the versioned schedule."""


@dataclass(frozen=True, slots=True)
class EntryWindow:
    session_date: date
    timezone: str
    market_open: time
    market_close: time
    entry_start: time
    entry_end: time
    calendar_version: str
    source: str

    @property
    def expiry_at(self) -> datetime:
        return datetime.combine(self.session_date, self.entry_end, tzinfo=IST)

    @property
    def entry_start_at(self) -> datetime:
        return datetime.combine(self.session_date, self.entry_start, tzinfo=IST)


def paper_test_entry_window(now: datetime) -> EntryWindow | None:
    """11:00 IST end on 13 October 2026 only, and only while that date is an ordinary session.

    Returns None before 09:20, at 11:00, and on every other date. The caller must
    also require PAPER mode. The ordinary 10:30 end is left unchanged.
    """
    local = now.astimezone(IST)
    if local.date() != TEST_EXTENSION_DATE or not (ENTRY_START <= local.time() < TEST_EXTENSION_END):
        return None
    base = session_for(local.date())
    if base is None or (base.entry_start, base.entry_end) != (ENTRY_START, ENTRY_END):
        return None
    return replace(base, entry_end=TEST_EXTENSION_END, source=TEST_EXTENSION_SOURCE)


def cash_session_open(now: datetime) -> bool:
    """True from the cash open inclusive to the cash close exclusive."""
    local = now.astimezone(IST)
    window = session_for(local.date())
    if window is None:
        return False
    opened = datetime.combine(window.session_date, window.market_open, tzinfo=IST)
    closed = datetime.combine(window.session_date, window.market_close, tzinfo=IST)
    return opened <= local < closed


def session_block_reason(day: date) -> str | None:
    if day in MOCK_SATURDAYS:
        return "mock_or_drill_not_a_cash_session"
    if day in MUHURAT_UNPUBLISHED:
        return "muhurat_timings_not_published"
    return None


def session_for(day: date) -> EntryWindow | None:
    if session_block_reason(day) is not None:
        return None
    if day == MAY18_2024:
        return EntryWindow(
            session_date=day,
            timezone="Asia/Kolkata",
            market_open=time(9, 15),
            market_close=time(10, 0),
            entry_start=time(9, 20),
            entry_end=time(10, 0),
            calendar_version=CALENDAR_VERSION,
            source="nse-cm-special-live-2024-05-18-primary",
        )
    if day < COVERAGE_START or day > COVERAGE_END or day.weekday() >= 5 or day in HOLIDAYS:
        return None
    return EntryWindow(
        session_date=day,
        timezone="Asia/Kolkata",
        market_open=ORDINARY_OPEN,
        market_close=ORDINARY_CLOSE,
        entry_start=ENTRY_START,
        entry_end=ENTRY_END,
        calendar_version=CALENDAR_VERSION,
        source="ordinary-cash-session",
    )


def next_session_day(after: date) -> date:
    day = after + timedelta(days=1)
    while day <= COVERAGE_END:
        if session_for(day) is not None:
            return day
        day += timedelta(days=1)
    raise CalendarUnverified(f"no verified session after {after.isoformat()}")


def assign_entry_window(created_at: datetime) -> EntryWindow:
    """Assign the first session that still has a bar start strictly after activation.

    An order created with no remaining bar in the current window, including an
    order created exactly at the entry-window end, is assigned to the next
    verified session. It does not stay in the expired window.
    """
    local = created_at.astimezone(IST)
    current = session_for(local.date())
    if current is not None and _remaining_starts(local, current):
        return current
    nxt = next_session_day(local.date())
    window = session_for(nxt)
    if window is None:
        raise CalendarUnverified(nxt.isoformat())
    return window


def expected_bar_starts(window: EntryWindow, activation: datetime) -> list[datetime]:
    local_activation = activation.astimezone(IST)
    starts: list[datetime] = []
    cursor = window.entry_start_at
    while cursor.astimezone(IST).time() < window.entry_end:
        if cursor > local_activation:
            starts.append(cursor.astimezone(timezone.utc))
        cursor += timedelta(minutes=5)
    return starts


def _remaining_starts(activation: datetime, window: EntryWindow) -> bool:
    return bool(expected_bar_starts(window, activation))

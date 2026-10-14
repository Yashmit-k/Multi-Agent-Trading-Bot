"""Snapshot-derived research calendar and rule B. Bars are supplied by the caller."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal

from quant_agents.research.h001.events import (
    EXCLUDED_SYMBOL,
    IST,
    DuplicateBarError,
    Exclusion,
    ExclusionReason,
    require_aware,
)

OPEN_CLOCK = time(9, 15)
ENTRY_END_CLOCK = time(9, 20)
CLOSE_CLOCK = time(15, 30)


@dataclass(frozen=True, slots=True)
class DailyBar:
    symbol: str
    end: datetime
    close: Decimal


@dataclass(frozen=True, slots=True)
class FiveMinuteBar:
    symbol: str
    start: datetime
    end: datetime
    open: Decimal


@dataclass(frozen=True, slots=True)
class EntrySelection:
    seq_id: str
    symbol: str
    decision: date
    decision_at: datetime
    p0: Decimal


def official_session_date(end: datetime) -> date | None:
    """Date of a daily bar whose end is exactly 15:30 IST. Other ends do not qualify."""
    moment = require_aware(end)
    if moment.timetz().replace(tzinfo=None) != CLOSE_CLOCK:
        return None
    return moment.date()


def research_calendar(daily_bars: tuple[DailyBar, ...] | list[DailyBar]) -> tuple[date, ...]:
    """Union of 15:30 IST dates across symbols other than TATAMOTORS.

    A date missing for every included symbol is absent. This is not the official
    NSE calendar and it does not consult static_nse.
    """
    found: set[date] = set()
    for bar in daily_bars:
        if bar.symbol == EXCLUDED_SYMBOL:
            continue
        session = official_session_date(bar.end)
        if session is not None:
            found.add(session)
    return tuple(sorted(found))


def decision_session(available_at: datetime, calendar: tuple[date, ...] | list[date]) -> date | None:
    """Earliest calendar date whose 09:15 IST is strictly after available_at."""
    moment = require_aware(available_at)
    for session in calendar:
        if datetime.combine(session, OPEN_CLOCK, tzinfo=IST) > moment:
            return session
    return None


def _entry_slot(bar: FiveMinuteBar, session: date) -> bool:
    start = require_aware(bar.start)
    end = require_aware(bar.end)
    return (
        start.date() == session
        and end.date() == session
        and start.timetz().replace(tzinfo=None) == OPEN_CLOCK
        and end.timetz().replace(tzinfo=None) == ENTRY_END_CLOCK
    )


def select_entry(
    seq_id: str,
    symbol: str,
    available_at: datetime,
    calendar: tuple[date, ...] | list[date],
    intraday_bars: tuple[FiveMinuteBar, ...] | list[FiveMinuteBar],
) -> EntrySelection | Exclusion:
    """P0 is that symbol's 09:15–09:20 open. A later bar is not a substitute."""
    session = decision_session(available_at, calendar)
    if session is None:
        return Exclusion(seq_id, symbol, ExclusionReason.MISSING_ENTRY_BAR)
    matches = [bar for bar in intraday_bars if bar.symbol == symbol and _entry_slot(bar, session)]
    if len(matches) > 1:
        raise DuplicateBarError(f"{symbol} {session.isoformat()} has more than one 09:15 bar")
    if not matches:
        return Exclusion(seq_id, symbol, ExclusionReason.MISSING_ENTRY_BAR)
    price = matches[0].open
    if not isinstance(price, Decimal) or price <= 0:
        return Exclusion(seq_id, symbol, ExclusionReason.NONPOSITIVE_PRICE)
    return EntrySelection(
        seq_id,
        symbol,
        session,
        datetime.combine(session, OPEN_CLOCK, tzinfo=IST),
        price,
    )

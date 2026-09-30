"""Trading calendar protocol. Arithmetic for session counting lives here, not in agents."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class TradingCalendar(Protocol):
    def last_covered_date(self) -> date:
        """Inclusive last calendar date this implementation covers."""

    def covers(self, moment: datetime | date) -> bool:
        """True when the date of moment is inside the covered range."""

    def is_trading_day(self, day: date) -> bool:
        """True for a weekday that is not a listed holiday, inside coverage."""

    def is_session_open(self, moment: datetime) -> bool:
        """True for [09:15, 15:30) IST on a trading day."""

    def session_close(self, moment: datetime) -> datetime:
        """15:30 IST on the trading day of moment, as UTC."""

    def next_trading_day(self, day: date) -> date:
        """The following trading day after day."""

    def sessions_between(self, start: datetime, end: datetime) -> int:
        """Count of trading sessions whose close is after start and at or before end."""

    def add_sessions(self, moment: datetime, count: int) -> datetime:
        """Session close of the Nth trading session after moment."""

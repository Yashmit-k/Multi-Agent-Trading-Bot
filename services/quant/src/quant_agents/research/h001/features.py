"""Four predictors. A hole in the 21-session window is an exclusion, not a longer lookback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from quant_agents.research.h001.calendar import DailyBar, official_session_date
from quant_agents.research.h001.events import (
    DuplicateBarError,
    Exclusion,
    ExclusionReason,
    require_aware,
)

FEATURE_COLUMNS = ("minute_of_day", "return_1", "return_5", "return_20")
REQUIRED_PRIOR_SESSIONS = 21
FORBIDDEN_COLUMNS = frozenset(
    {
        "hasXbrl",
        "desc",
        "attchmntText",
        "period_end",
        "crawl_time",
        "volume_imbalance",
        "oil_gas",
        "holdout",
    }
)


@dataclass(frozen=True, slots=True)
class FeatureRow:
    minute_of_day: int
    return_1: Decimal
    return_5: Decimal
    return_20: Decimal

    def as_tuple(self) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        return (Decimal(self.minute_of_day), self.return_1, self.return_5, self.return_20)


def minutes_from_midnight(available_at: datetime) -> int:
    moment = require_aware(available_at)
    return moment.hour * 60 + moment.minute


def _closes_by_session(
    symbol: str,
    daily_bars: tuple[DailyBar, ...] | list[DailyBar],
) -> dict[date, Decimal]:
    found: dict[date, Decimal] = {}
    for bar in daily_bars:
        if bar.symbol != symbol:
            continue
        session = official_session_date(bar.end)
        if session is None:
            continue
        if session in found:
            raise DuplicateBarError(f"{symbol} {session.isoformat()} has more than one daily close")
        found[session] = bar.close
    return found


def _session_return(closes: dict[date, Decimal], window: tuple[date, ...], steps: int) -> Decimal:
    last = closes[window[-1]]
    earlier = closes[window[-1 - steps]]
    return last / earlier - Decimal(1)


def build_features(
    seq_id: str,
    symbol: str,
    decision: date,
    available_at: datetime,
    calendar: tuple[date, ...] | list[date],
    daily_bars: tuple[DailyBar, ...] | list[DailyBar],
) -> FeatureRow | Exclusion:
    """Returns use the symbol's own closes on the research calendar before D."""
    prior = tuple(session for session in calendar if session < decision)
    if len(prior) < REQUIRED_PRIOR_SESSIONS:
        return Exclusion(seq_id, symbol, ExclusionReason.SHORT_HISTORY)
    window = prior[-REQUIRED_PRIOR_SESSIONS:]
    closes = _closes_by_session(symbol, daily_bars)
    if any(session not in closes for session in window):
        return Exclusion(seq_id, symbol, ExclusionReason.MISSING_DAILY_HISTORY)
    if any(closes[session] <= 0 for session in window):
        return Exclusion(seq_id, symbol, ExclusionReason.NONPOSITIVE_PRICE)
    # decision-day and later closes are not in `prior`, so they are not read
    return FeatureRow(
        minutes_from_midnight(available_at),
        _session_return(closes, window, 1),
        _session_return(closes, window, 5),
        _session_return(closes, window, 20),
    )

"""H1 label. P1 is the next session's 15:30 IST close. H5 is not a primary label."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from quant_agents.research.h001.calendar import DailyBar, official_session_date
from quant_agents.research.h001.events import DuplicateBarError, Exclusion, ExclusionReason

PRIMARY_HORIZON = "H1"


@dataclass(frozen=True, slots=True)
class Label:
    horizon: str
    p0: Decimal
    p1: Decimal
    return_gross: Decimal
    y: int


def require_primary_horizon(name: str) -> str:
    if name != PRIMARY_HORIZON:
        raise ValueError("H5 is not a primary label")
    return PRIMARY_HORIZON


def next_session(decision: date, calendar: tuple[date, ...] | list[date]) -> date | None:
    for session in calendar:
        if session > decision:
            return session
    return None


def horizon_close(
    seq_id: str,
    symbol: str,
    decision: date,
    calendar: tuple[date, ...] | list[date],
    daily_bars: tuple[DailyBar, ...] | list[DailyBar],
) -> tuple[date, Decimal] | Exclusion:
    session = next_session(decision, calendar)
    if session is None:
        return Exclusion(seq_id, symbol, ExclusionReason.MISSING_HORIZON_CLOSE)
    closes: list[Decimal] = []
    for bar in daily_bars:
        if bar.symbol != symbol:
            continue
        if official_session_date(bar.end) == session:
            closes.append(bar.close)
    if len(closes) > 1:
        raise DuplicateBarError(f"{symbol} {session.isoformat()} has more than one daily close")
    if not closes:
        return Exclusion(seq_id, symbol, ExclusionReason.MISSING_HORIZON_CLOSE)
    return session, closes[0]


def make_label(
    seq_id: str,
    symbol: str,
    p0: Decimal | None,
    p1: Decimal | None,
) -> Label | Exclusion:
    """y is 1 only when (P1-P0)/P0 is strictly positive. Missing prices are not filled."""
    require_primary_horizon(PRIMARY_HORIZON)
    if p0 is None:
        return Exclusion(seq_id, symbol, ExclusionReason.MISSING_ENTRY_BAR)
    if p1 is None:
        return Exclusion(seq_id, symbol, ExclusionReason.MISSING_HORIZON_CLOSE)
    if not isinstance(p0, Decimal) or not isinstance(p1, Decimal):
        return Exclusion(seq_id, symbol, ExclusionReason.NONPOSITIVE_PRICE)
    if p0 <= 0 or p1 <= 0:
        return Exclusion(seq_id, symbol, ExclusionReason.NONPOSITIVE_PRICE)
    gross = (p1 - p0) / p0
    label = 1 if gross > 0 else 0
    return Label(PRIMARY_HORIZON, p0, p1, gross, label)

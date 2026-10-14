"""Research-only `momentum_20` basket plan from completed daily bars.

This module does not write to paper tables, queue orders, or run a cycle. It
names what the approved rule would select and the dates the existing
five-session convention implies. It does not choose which names to enter when
the basket exceeds the daily entry limit: no entry priority has been approved.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from contracts.enums import Timeframe
from contracts.schemas.market import Candle

from quant_agents.research.daily_rules.rules import MOMENTUM_LOOKBACK, momentum_20
from quant_agents.research.timesfm3.scores import EXCLUDED_SYMBOL, official_session_date

HOLD_SESSIONS = 5
PAPER_NOTIONAL = Decimal("20000")
PAPER_DAILY_ENTRY_LIMIT = 6


@dataclass(frozen=True, slots=True)
class PaperPlan:
    decision_date: date | None
    entry_date: date | None
    exit_date: date | None
    selected: tuple[str, ...]
    not_selected: tuple[str, ...]
    excluded: dict[str, str]
    history_gaps: dict[str, int]
    notional_per_symbol: Decimal = PAPER_NOTIONAL
    daily_entry_limit: int = PAPER_DAILY_ENTRY_LIMIT
    issues: tuple[str, ...] = field(default_factory=tuple)

    @property
    def proposed_notional(self) -> Decimal:
        return self.notional_per_symbol * len(self.selected)

    @property
    def fits_daily_entry_limit(self) -> bool:
        return len(self.selected) <= self.daily_entry_limit


def plan_momentum_20(
    bars: Iterable[Candle],
    as_of: datetime,
    calendar: Sequence[date],
) -> PaperPlan:
    """Plan from daily bars that ended at 15:30 IST on or before `as_of`.

    `calendar` is the list of trading sessions to place entry and exit on. Dates
    are never generated here. Entry is the first calendar session after the
    decision. Exit is the fifth calendar session after the decision, the same
    close the research scored. Selected symbols are listed alphabetically; that
    order is not an entry priority.
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    closes: dict[str, dict[date, Decimal]] = {}
    excluded: dict[str, str] = {}
    for bar in bars:
        if bar.timeframe != Timeframe.D1 or bar.symbol == EXCLUDED_SYMBOL:
            continue
        if bar.end > as_of:
            continue
        session = official_session_date(bar.end)
        if session is None:
            excluded.setdefault(bar.symbol, "incomplete_daily_bar")
            continue
        rows = closes.setdefault(bar.symbol, {})
        if session in rows:
            excluded[bar.symbol] = "duplicate_session"
            continue
        rows[session] = bar.close

    issues: list[str] = []
    sessions = sorted({session for rows in closes.values() for session in rows})
    if not sessions:
        return PaperPlan(None, None, None, (), (), dict(sorted(excluded.items())), {}, issues=("no_completed_daily_bars",))
    decision = sessions[-1]
    recent = sessions[-(MOMENTUM_LOOKBACK + 1) :]

    selected: list[str] = []
    not_selected: list[str] = []
    gaps: dict[str, int] = {}
    for symbol in sorted(closes):
        if symbol in excluded:
            continue
        rows = closes[symbol]
        if decision not in rows:
            excluded[symbol] = "missing_decision_bar"
            continue
        history = tuple(rows[session] for session in sorted(rows))
        signal = momentum_20(history)
        if signal is None:
            excluded[symbol] = "insufficient_history"
            continue
        missing = sum(1 for session in recent if session not in rows)
        if missing:
            gaps[symbol] = missing
        (selected if signal else not_selected).append(symbol)

    after = sorted(day for day in set(calendar) if day > decision)
    entry = after[0] if after else None
    exit_day = after[HOLD_SESSIONS - 1] if len(after) >= HOLD_SESSIONS else None
    if entry is None:
        issues.append("calendar_has_no_entry_session")
    if exit_day is None:
        issues.append("calendar_too_short_for_exit")
    if len(selected) > PAPER_DAILY_ENTRY_LIMIT:
        issues.append(
            f"basket_exceeds_daily_entry_limit: {len(selected)} selected, limit {PAPER_DAILY_ENTRY_LIMIT}, no approved priority"
        )
    return PaperPlan(
        decision_date=decision,
        entry_date=entry,
        exit_date=exit_day,
        selected=tuple(selected),
        not_selected=tuple(not_selected),
        excluded=dict(sorted(excluded.items())),
        history_gaps=gaps,
        issues=tuple(issues),
    )

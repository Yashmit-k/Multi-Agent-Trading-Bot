"""End-of-day paper book (docs/dev3-snapshot-writer-design.md).

One row per active session and IST trading day, written once the cash close
plus the 90-second publication delay has passed. Holdings are marked at the
last 5-minute close at or before 15:30 IST (daily close as fallback). Cash and
realized P&L come from the fill ledger, so closed trades and every charge are
included. A day with no fills and no holdings is not written.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from contracts.enums import Side, Timeframe
from core_db.repository import CoreRepository
from core_paper.trading_calendar import IST, session_for

PUBLICATION_DELAY = timedelta(seconds=90)


def close_instant(day: date) -> datetime | None:
    window = session_for(day)
    if window is None:
        return None
    return datetime.combine(day, window.market_close, tzinfo=IST).astimezone(timezone.utc)


def book_for_day(repository: CoreRepository, starting_cash: Decimal, day: date, *, as_of: datetime | None = None) -> dict | None:
    """The book at the day's close (or at as_of if earlier, for a provisional row). None if nothing to report."""
    close = close_instant(day)
    if close is None:
        return None
    moment = min(close, as_of) if as_of is not None else close
    open_at = datetime.combine(day, time(0, 0), tzinfo=IST).astimezone(timezone.utc)
    orders = {order.order_id: order for order in repository.list_orders()}
    cash = starting_cash
    fees_today = Decimal("0")
    fills_today = 0
    sells_today = 0
    holdings: dict[str, tuple[int, Decimal]] = {}
    for execution in sorted(repository.list_executions(), key=lambda item: item.executed_at):
        if execution.executed_at > moment:
            continue
        order = orders.get(execution.order_id)
        if order is None:
            continue
        notional = execution.price * execution.quantity
        quantity, cost = holdings.get(execution.symbol, (0, Decimal("0")))
        if order.side == Side.BUY:
            cash -= notional + execution.fees
            holdings[execution.symbol] = (quantity + execution.quantity, cost + notional)
        else:
            cash += notional - execution.fees
            remaining = quantity - execution.quantity
            average = cost / quantity if quantity else Decimal("0")
            holdings[execution.symbol] = (remaining, average * remaining)
        if execution.executed_at >= open_at:
            fees_today += execution.fees
            fills_today += 1
            sells_today += 1 if order.side == Side.SELL else 0
    market_value = Decimal("0")
    unrealized = Decimal("0")
    marks: dict[str, str] = {}
    for symbol, (quantity, cost) in holdings.items():
        if quantity <= 0:
            continue
        bars = repository.candles_until(symbol, Timeframe.M5, moment, last=1) or repository.candles_until(symbol, Timeframe.D1, moment, last=1)
        if not bars:
            continue
        price = bars[-1].close
        marks[symbol] = str(price)
        market_value += price * quantity
        unrealized += price * quantity - cost
    if fills_today == 0 and not marks:
        return None
    equity = cash + market_value
    total = equity - starting_cash
    return {
        "trading_day": day.isoformat(),
        "as_of": moment.isoformat(),
        "complete": as_of is None or as_of >= close,
        "cash": str(cash),
        "market_value": str(market_value),
        "equity": str(equity),
        "total_pnl": str(total),
        "unrealized_pnl": str(unrealized),
        "realized_pnl": str(total - unrealized),
        "fees_today": str(fees_today),
        "fills_today": fills_today,
        "closed_trades_today": sells_today,
        "open_positions": len(marks),
        "marks": marks,
    }


def write_daily_if_due(repository: CoreRepository, now: datetime) -> bool:
    """Write today's end-of-day row once, after the close plus the publication delay."""
    book = repository.active_paper_session()
    if book is None or book.starting_cash is None:
        return False
    day = now.astimezone(IST).date()
    close = close_instant(day)
    if close is None or now < close + PUBLICATION_DELAY:
        return False
    if repository.daily_equity_exists(book.session_id, day.isoformat()):
        return False
    row = book_for_day(repository, book.starting_cash, day)
    if row is None:
        return False
    previous = repository.list_daily_equity(book.session_id)
    start_equity = Decimal(previous[-1]["equity"]) if previous else book.starting_cash
    row["start_of_day_equity"] = str(start_equity)
    row["day_pnl"] = str(Decimal(row["equity"]) - start_equity)
    return repository.insert_daily_equity(book.session_id, day.isoformat(), now, row)

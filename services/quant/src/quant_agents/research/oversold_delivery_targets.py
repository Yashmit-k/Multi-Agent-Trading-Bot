"""Delivery-only oversold mean-reversion book.

Entry is the frozen full rule: prior EMA20, a -12% to -5% band, three completed
down days, and a 1% intraday drop. Same-session exits use +2%. Later sessions
use +5% from the original fill. This module does not place orders and does not
read the holdout.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from statistics import median
from typing import Iterable

from contracts.enums import Side
from contracts.schemas.market import Candle
from core_paper.costs import slipped_price
from quant_agents.research.delivery_costs import (
    SCHEDULE_ID,
    ChargeBreakdown,
    delivery_buy,
    delivery_sell,
    intraday_buy,
    intraday_sell,
    money,
)
from quant_agents.research.rebound import (
    CENT,
    IST,
    PER_TRADE_CAP,
    _context_before,
    _match,
    _state_for,
    daily_context,
    session_date,
    signal_window,
)

SAME_DAY_TARGET = Decimal("1.02")
LATER_TARGET = Decimal("1.05")
HOLD_CHECKPOINTS = (1, 5, 10, 20, 60)


@dataclass(slots=True)
class _Open:
    symbol: str
    signal_time: datetime
    signal_price: Decimal
    previous_close: Decimal
    previous_session: date | None
    entry_time: datetime
    entry_bar_end: datetime
    entry_session: date
    raw_entry: Decimal
    entry_price: Decimal
    quantity: int
    entry_charges: ChargeBreakdown
    entry_notional: Decimal

    @property
    def cost_basis(self) -> Decimal:
        return self.entry_notional + self.entry_charges.total


def _target_price(position: _Open, day: date) -> Decimal:
    factor = SAME_DAY_TARGET if day == position.entry_session else LATER_TARGET
    return money(position.entry_price * factor)


def _fill_price(position: _Open, bar: Candle) -> Decimal | None:
    """Price before slippage. The entry bar is never an exit bar."""
    if bar.end <= position.entry_bar_end:
        return None
    target = _target_price(position, session_date(bar.end))
    if bar.open >= target:
        return bar.open
    if bar.high >= target:
        return target
    return None


def _charges_dict(charges: ChargeBreakdown) -> dict[str, str]:
    return charges.as_dict()


def _add_charges(total: dict[str, Decimal], charges: ChargeBreakdown) -> None:
    for key in ("brokerage", "stt", "transaction", "sebi", "gst", "stamp", "dp"):
        total[key] += getattr(charges, key)


def simulate_portfolio(
    bars_5m: Iterable[Candle],
    bars_1d: Iterable[Candle],
    *,
    starting_cash: Decimal = Decimal("1000000"),
    per_trade_cap: Decimal = PER_TRADE_CAP,
    slippage_bps: Decimal = Decimal("0"),
    brokerage: bool = True,
) -> dict:
    """One portfolio pass. Same-timestamp entries are filled before exits, in symbol order."""
    daily_by_symbol: dict[str, tuple] = defaultdict(lambda: ([], [], [], []))
    grouped: dict[str, list[Candle]] = defaultdict(list)
    for bar in bars_1d:
        grouped[bar.symbol].append(bar)
    prepared: dict[str, tuple] = {}
    for symbol, rows in grouped.items():
        prepared[symbol] = daily_context(rows)
    contexts: dict[tuple[str, date], object] = {}

    def context_for(symbol: str, day: date):
        key = (symbol, day)
        found = contexts.get(key)
        if found is None:
            dates, closes, ema_at, streaks = prepared.get(symbol, ([], [], [], []))
            found = _context_before(day, dates, closes, ema_at, streaks)
            contexts[key] = found
        return found

    by_end: dict[datetime, list[Candle]] = defaultdict(list)
    for bar in bars_5m:
        if bar.close <= 0 and bar.open <= 0:
            continue
        by_end[bar.end].append(bar)

    cash = money(starting_cash)
    positions: dict[str, _Open] = {}
    pending: dict[str, object] = {}
    last_mark: dict[str, tuple[Decimal, datetime, date]] = {}
    book_sessions: list[date] = []
    rejected: list[dict] = []
    events: list[dict] = []
    closed: list[dict] = []
    days: list[dict] = []
    realized_gross = Decimal("0")
    realized_net = Decimal("0")
    purchase_turnover = Decimal("0")
    sale_proceeds_total = Decimal("0")
    charges_total = defaultdict(lambda: Decimal("0"))
    signals = 0
    current_day: date | None = None
    day_state: dict | None = None

    def session_index(day: date) -> int:
        try:
            return book_sessions.index(day)
        except ValueError:
            return len(book_sessions)

    def holding_sessions(entry_day: date, as_of: date) -> int:
        if entry_day not in book_sessions or as_of not in book_sessions:
            return 0
        return book_sessions.index(as_of) - book_sessions.index(entry_day)

    def begin_day(day: date) -> dict:
        book_sessions.append(day)
        return {
            "date": day.isoformat(),
            "opening_cash": cash,
            "buy_notional": Decimal("0"),
            "sale_proceeds": Decimal("0"),
            "charges": Decimal("0"),
            "entries": [],
            "exits": [],
            "rejected": [],
        }

    def finish_day(state: dict, day: date) -> None:
        holdings = []
        losses = []
        market_value = Decimal("0")
        cost_basis = Decimal("0")
        unrealized_gross = Decimal("0")
        unrealized_net = Decimal("0")
        in_loss = 0
        in_profit = 0
        breakeven = 0
        capital_in_loss = Decimal("0")
        for symbol in sorted(positions):
            position = positions[symbol]
            mark = last_mark.get(symbol)
            if mark is None:
                continue
            mark_price, mark_time, mark_session = mark
            stale = mark_session != day
            valuation = datetime(day.year, day.month, day.day, 15, 30, tzinfo=IST)
            age_seconds = int((valuation - mark_time.astimezone(IST)).total_seconds())
            market = money(mark_price * position.quantity)
            gross = money((mark_price - position.entry_price) * position.quantity)
            exit_quote = delivery_sell(market)
            net = money(market - position.cost_basis - exit_quote.total)
            price_only_pct = (mark_price / position.entry_price - 1) * Decimal(100) if position.entry_price else Decimal("0")
            target = money(position.entry_price * LATER_TARGET)
            distance = ((target - mark_price) / mark_price * Decimal(100)) if mark_price else None
            basis = position.cost_basis
            status = "breakeven"
            if market < basis:
                status = "loss"
                in_loss += 1
                capital_in_loss += basis
            elif market > basis:
                status = "profit"
                in_profit += 1
            else:
                breakeven += 1
            row = {
                "date": day.isoformat(),
                "symbol": symbol,
                "entry_date": position.entry_session.isoformat(),
                "entry_time": position.entry_time.isoformat(),
                "entry_price": format(position.entry_price, "f"),
                "quantity": position.quantity,
                "entry_notional": format(position.entry_notional, "f"),
                "entry_charges": format(position.entry_charges.total, "f"),
                "cost_basis": format(basis, "f"),
                "mark_price": format(mark_price, "f"),
                "mark_time": mark_time.isoformat(),
                "mark_age_seconds": age_seconds,
                "stale_mark": stale,
                "market_value": format(market, "f"),
                "unrealized_gross_pnl": format(gross, "f"),
                "estimated_exit_charges": format(exit_quote.total, "f"),
                "unrealized_net_pnl": format(net, "f"),
                "price_return_pct": format(money(price_only_pct), "f"),
                "target_price": format(target, "f"),
                "target_pct": "5",
                "distance_to_target_pct": None if distance is None else format(money(distance), "f"),
                "sessions_held": holding_sessions(position.entry_session, day),
                "status": status,
                "unresolved": True,
            }
            holdings.append(row)
            market_value += market
            cost_basis += basis
            unrealized_gross += gross
            unrealized_net += net
            if status == "loss":
                losses.append(row)
        losses.sort(key=lambda item: Decimal(item["unrealized_net_pnl"]))
        closing_cash = cash
        equity = money(closing_cash + market_value)
        opening = state["opening_cash"]
        expected = money(opening + state["sale_proceeds"] - state["buy_notional"] - state["charges"])
        days.append(
            {
                **state,
                "date": day.isoformat(),
                "opening_cash": format(opening, "f"),
                "closing_cash": format(closing_cash, "f"),
                "buy_notional": format(state["buy_notional"], "f"),
                "sale_proceeds": format(state["sale_proceeds"], "f"),
                "charges": format(state["charges"], "f"),
                "cash_reconciled": closing_cash == expected,
                "cost_basis": format(cost_basis, "f"),
                "market_value": format(market_value, "f"),
                "capital_deployed": format(cost_basis, "f"),
                "purchase_turnover": format(purchase_turnover, "f"),
                "cumulative_sale_proceeds": format(sale_proceeds_total, "f"),
                "cumulative_charges": format(sum(charges_total.values()), "f"),
                "realized_gross_pnl": format(realized_gross, "f"),
                "realized_net_pnl": format(realized_net, "f"),
                "unrealized_gross_pnl": format(unrealized_gross, "f"),
                "unrealized_net_pnl": format(unrealized_net, "f"),
                "equity": format(equity, "f"),
                "return_pct": format(money((equity / starting_cash - 1) * Decimal(100)), "f") if starting_cash else "0",
                "open_positions": len(holdings),
                "positions_in_loss": in_loss,
                "positions_in_profit": in_profit,
                "positions_breakeven": breakeven,
                "entries_today": len(state["entries"]),
                "exits_today": len(state["exits"]),
                "capital_in_loss": format(capital_in_loss, "f"),
                "holdings": holdings,
                "loss_inventory": losses,
                "pending_orders": "0",
            }
        )

    for end in sorted(by_end):
        group = sorted(by_end[end], key=lambda bar: bar.symbol)
        day = session_date(end)
        if current_day is None:
            current_day = day
            day_state = begin_day(day)
        elif day != current_day:
            finish_day(day_state, current_day)
            current_day = day
            day_state = begin_day(day)
        assert day_state is not None

        planned: list[tuple[Candle, object]] = []
        exits: list[tuple[Candle, _Open]] = []
        for bar in group:
            if bar.close > 0:
                last_mark[bar.symbol] = (bar.close, bar.end, day)
            waiting = pending.get(bar.symbol)
            if waiting is not None:
                planned.append((bar, waiting))
                del pending[bar.symbol]
            position = positions.get(bar.symbol)
            if position is not None and bar.end > position.entry_bar_end:
                exits.append((bar, position))

        for bar, signal in planned:
            if session_date(bar.end) != signal.session_date or bar.open <= 0:
                continue
            if bar.symbol in positions:
                continue
            raw_entry = bar.open
            filled = slipped_price(Side.BUY, raw_entry, slippage_bps)
            quantity = int(per_trade_cap // filled) if filled > 0 else 0
            notional = money(filled * quantity) if quantity >= 1 else Decimal("0")
            if quantity < 1 or notional > per_trade_cap:
                row = {"symbol": bar.symbol, "time": bar.start.isoformat(), "reason": "over_cap", "price": format(filled, "f")}
                rejected.append(row)
                day_state["rejected"].append(row)
                continue
            charges = delivery_buy(notional)
            required = notional + charges.total
            if cash < required:
                row = {
                    "symbol": bar.symbol,
                    "time": bar.start.isoformat(),
                    "reason": "insufficient_cash",
                    "price": format(filled, "f"),
                    "quantity": quantity,
                    "required_cash": format(required, "f"),
                    "available_cash": format(cash, "f"),
                }
                rejected.append(row)
                day_state["rejected"].append(row)
                continue
            cash = money(cash - required)
            day_state["buy_notional"] += notional
            day_state["charges"] += charges.total
            purchase_turnover += notional
            _add_charges(charges_total, charges)
            position = _Open(
                symbol=bar.symbol,
                signal_time=signal.signal_time,
                signal_price=signal.signal_price,
                previous_close=signal.previous_close,
                previous_session=signal.ema_through,
                entry_time=bar.start,
                entry_bar_end=bar.end,
                entry_session=signal.session_date,
                raw_entry=raw_entry,
                entry_price=filled,
                quantity=quantity,
                entry_charges=charges,
                entry_notional=notional,
            )
            positions[bar.symbol] = position
            entry_event = {
                "event": "entry",
                "symbol": bar.symbol,
                "time": bar.start.isoformat(),
                "price": format(filled, "f"),
                "raw_price": format(raw_entry, "f"),
                "quantity": quantity,
                "charges": _charges_dict(charges),
                "signal_time": signal.signal_time.isoformat(),
                "signal_price": format(signal.signal_price, "f"),
                "previous_close": format(signal.previous_close, "f"),
                "previous_session": None if signal.ema_through is None else signal.ema_through.isoformat(),
                "ema20": None if signal.ema20 is None else format(signal.ema20, "f"),
                "distance_pct": None if signal.distance_pct is None else format(signal.distance_pct, "f"),
                "down_days": signal.down_days,
                "today_drop_pct": None if signal.today_drop_pct is None else format(signal.today_drop_pct, "f"),
                "session_date": signal.session_date.isoformat(),
                "variant": "full",
                "live_enabled": False,
            }
            events.append(entry_event)
            day_state["entries"].append(entry_event)

        for bar, position in exits:
            raw_exit = _fill_price(position, bar)
            if raw_exit is None:
                continue
            same_session = session_date(bar.end) == position.entry_session
            filled = slipped_price(Side.SELL, raw_exit, slippage_bps)
            proceeds = money(filled * position.quantity)
            if same_session:
                revised_entry = intraday_buy(position.entry_notional, brokerage=brokerage)
                exit_charges = intraday_sell(proceeds, brokerage=brokerage)
                refund = position.entry_charges.total - revised_entry.total
                cash = money(cash + proceeds - exit_charges.total + refund)
                day_state["charges"] += exit_charges.total - refund
                _add_charges(charges_total, exit_charges)
                _add_charges(charges_total, revised_entry)
                for key in ("brokerage", "stt", "transaction", "sebi", "gst", "stamp", "dp"):
                    charges_total[key] -= getattr(position.entry_charges, key)
                position.entry_charges = revised_entry
                holding = "same_session"
            else:
                exit_charges = delivery_sell(proceeds)
                cash = money(cash + proceeds - exit_charges.total)
                day_state["charges"] += exit_charges.total
                _add_charges(charges_total, exit_charges)
                holding = "overnight"
            day_state["sale_proceeds"] += proceeds
            sale_proceeds_total += proceeds
            gross = money((filled - position.entry_price) * position.quantity)
            net = money(gross - position.entry_charges.total - exit_charges.total)
            realized_gross += gross
            realized_net += net
            trade = {
                "event": "exit",
                "symbol": position.symbol,
                "time": bar.end.isoformat(),
                "price": format(filled, "f"),
                "raw_price": format(raw_exit, "f"),
                "quantity": position.quantity,
                "entry_time": position.entry_time.isoformat(),
                "entry_price": format(position.entry_price, "f"),
                "entry_session": position.entry_session.isoformat(),
                "exit_session": session_date(bar.end).isoformat(),
                "holding": holding,
                "target_price": format(_target_price(position, session_date(bar.end)), "f"),
                "gross_pnl": format(gross, "f"),
                "entry_charges": format(position.entry_charges.total, "f"),
                "exit_charges": _charges_dict(exit_charges),
                "net_pnl": format(net, "f"),
                "sessions_held": holding_sessions(position.entry_session, session_date(bar.end)),
                "reason": "target",
                "live_enabled": False,
            }
            events.append(trade)
            closed.append(trade)
            day_state["exits"].append(trade)
            del positions[position.symbol]

        for bar in group:
            if not signal_window(bar.end) or bar.close <= 0:
                continue
            state = _state_for(bar, context_for(bar.symbol, day))
            if not _match("full", state):
                continue
            signals += 1
            if bar.symbol in positions or bar.symbol in pending:
                continue
            pending[bar.symbol] = state

    if current_day is not None and day_state is not None:
        finish_day(day_state, current_day)

    open_rows = []
    for symbol in sorted(positions):
        position = positions[symbol]
        mark = last_mark.get(symbol)
        mark_price = None if mark is None else mark[0]
        open_rows.append(
            {
                "event": "unresolved",
                "symbol": symbol,
                "entry_time": position.entry_time.isoformat(),
                "entry_price": format(position.entry_price, "f"),
                "entry_session": position.entry_session.isoformat(),
                "quantity": position.quantity,
                "cost_basis": format(position.cost_basis, "f"),
                "mark_price": None if mark_price is None else format(mark_price, "f"),
                "sessions_held": 0 if current_day is None else holding_sessions(position.entry_session, current_day),
                "reason": "unresolved",
                "live_enabled": False,
            }
        )
        events.append(open_rows[-1])

    result = {
        "schedule_id": SCHEDULE_ID,
        "schedule_note": "Zerodha equity table as published on 2026-10-09, applied uniformly. Not a year-by-year reconstruction.",
        "starting_cash": format(money(starting_cash), "f"),
        "per_trade_cap": format(per_trade_cap, "f"),
        "slippage_bps": format(slippage_bps, "f"),
        "brokerage": brokerage,
        "live_enabled": False,
        "signals": signals,
        "entries": sum(len(day["entries"]) for day in days),
        "exits": len(closed),
        "rejected": rejected,
        "events": events,
        "closed": closed,
        "open_positions": open_rows,
        "days": days,
        "ending_cash": format(cash, "f"),
        "realized_gross_pnl": format(realized_gross, "f"),
        "realized_net_pnl": format(realized_net, "f"),
        "charges": {key: format(value, "f") for key, value in charges_total.items()},
    }
    result["audit"] = lookahead_audit(result)
    return result


def lookahead_audit(result: dict) -> dict:
    failures: list[str] = []
    if result["live_enabled"] is not False:
        failures.append("live trading is enabled")
    for event in result["events"]:
        if event["event"] != "entry":
            continue
        if datetime.fromisoformat(event["time"]) < datetime.fromisoformat(event["signal_time"]):
            failures.append(f"{event['symbol']} entry precedes the completed signal")
        previous = event.get("previous_session")
        if previous is None or previous >= event["session_date"]:
            failures.append(f"{event['symbol']} previous close is not from a prior session")
        if Decimal(event["signal_price"]) > Decimal(event["previous_close"]) * Decimal("0.99"):
            failures.append(f"{event['symbol']} entry signal is not a 1 percent drop")
        if event.get("ema20") is None:
            failures.append(f"{event['symbol']} entry has no prior EMA20")
        distance = Decimal(event["distance_pct"])
        if distance < Decimal("-12") or distance > Decimal("-5"):
            failures.append(f"{event['symbol']} EMA distance is outside -12 to -5")
        if int(event["down_days"]) < 3:
            failures.append(f"{event['symbol']} down-day streak is below 3")
        if Decimal(event["price"]) * event["quantity"] > Decimal(result["per_trade_cap"]) + CENT:
            failures.append(f"{event['symbol']} notional exceeds the cap")
    for trade in result["closed"]:
        if datetime.fromisoformat(trade["time"]) <= datetime.fromisoformat(trade["entry_time"]):
            failures.append(f"{trade['symbol']} exit is not after entry")
        raw = Decimal(trade["raw_price"])
        entry = Decimal(trade["entry_price"])
        same = trade["holding"] == "same_session"
        target = entry * (SAME_DAY_TARGET if same else LATER_TARGET)
        if raw + CENT < target:
            failures.append(f"{trade['symbol']} exit is below the applicable target")
        if same and trade["exit_session"] != trade["entry_session"]:
            failures.append(f"{trade['symbol']} same-session label is wrong")
        if not same and trade["exit_session"] <= trade["entry_session"]:
            failures.append(f"{trade['symbol']} overnight exit is not a later session")
        if same and Decimal(trade["exit_charges"]["brokerage"]) == 0 and result["brokerage"]:
            failures.append(f"{trade['symbol']} same-session brokerage is zero")
        if not same and Decimal(trade["exit_charges"]["dp"]) == 0:
            failures.append(f"{trade['symbol']} overnight sale has no DP charge")
        if trade["reason"] != "target":
            failures.append(f"{trade['symbol']} closed for {trade['reason']}")
    for day in result["days"]:
        if not day["cash_reconciled"]:
            failures.append(f"{day['date']} cash ledger does not reconcile")
        equity = Decimal(day["equity"])
        cash_plus_marks = Decimal(day["closing_cash"]) + Decimal(day["market_value"])
        if money(equity) != money(cash_plus_marks):
            failures.append(f"{day['date']} equity is not cash plus market value")
        if day["date"] != result["days"][0]["date"]:
            pass
    for earlier, later in zip(result["days"], result["days"][1:]):
        if earlier["closing_cash"] != later["opening_cash"]:
            failures.append(f"{later['date']} does not open from the previous close")
    return {"status": "PASS" if not failures else "FAIL", "failures": failures}


def summarize(result: dict) -> dict:
    """Closed-trade and daily-equity figures. Open positions stay out of the win rate."""
    closed = result["closed"]
    nets = [Decimal(row["net_pnl"]) for row in closed]
    wins = [value for value in nets if value > 0]
    losses = [value for value in nets if value < 0]
    holds = [int(row["sessions_held"]) for row in closed]
    days = result["days"]
    equities = [Decimal(day["equity"]) for day in days]
    deployed = [Decimal(day["capital_deployed"]) for day in days]
    cash_rows = [Decimal(day["closing_cash"]) for day in days]
    peak = equities[0] if equities else Decimal(result["starting_cash"])
    max_dd = Decimal("0")
    for equity in equities:
        if equity > peak:
            peak = equity
        drawdown = peak - equity
        if drawdown > max_dd:
            max_dd = drawdown
    by_symbol: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_month: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in closed:
        by_symbol[row["symbol"]] += Decimal(row["net_pnl"])
        by_month[row["exit_session"][:7]] += Decimal(row["net_pnl"])
    ordered = sorted(nets, reverse=True)
    top_cut = max(1, len(ordered) // 20) if ordered else 0
    top_share = (sum(ordered[:top_cut]) / sum(nets)) if nets and sum(nets) != 0 else None
    final = days[-1] if days else None
    unrealized = Decimal(final["unrealized_net_pnl"]) if final else Decimal("0")
    realized = Decimal(result["realized_net_pnl"])
    total_pnl = realized + unrealized
    open_after = {}
    for checkpoint in HOLD_CHECKPOINTS:
        reached = [row for row in closed if int(row["sessions_held"]) >= checkpoint]
        still = [row for row in result["open_positions"] if int(row["sessions_held"]) >= checkpoint]
        open_after[str(checkpoint)] = len(reached) + len(still)
    years = {}
    previous_equity = Decimal(result["starting_cash"])
    for year in ("2024", "2025", "2026"):
        chosen = [day for day in days if day["date"].startswith(year)]
        if not chosen:
            years[year] = {"days": 0, "partial": year == "2026"}
            continue
        ending = Decimal(chosen[-1]["equity"])
        years[year] = {
            "days": len(chosen),
            "partial": year == "2026",
            "starting_equity": format(previous_equity, "f"),
            "ending_equity": chosen[-1]["equity"],
            "ending_cash": chosen[-1]["closing_cash"],
            "market_value": chosen[-1]["market_value"],
            "realized_net_pnl": chosen[-1]["realized_net_pnl"],
            "unrealized_net_pnl": chosen[-1]["unrealized_net_pnl"],
            "year_equity_change": format(money(ending - previous_equity), "f"),
            "max_equity": format(max(Decimal(day["equity"]) for day in chosen), "f"),
            "min_equity": format(min(Decimal(day["equity"]) for day in chosen), "f"),
        }
        previous_equity = ending
    ending_losses = []
    if final:
        ending_losses = list(final["loss_inventory"])
    classification = "AUDIT_FAILED" if result["audit"]["status"] != "PASS" else "NOT A ROBUST EDGE"
    return {
        "classification": classification,
        "classification_note": "A positive mark-to-market return is not a robust edge. Open losers stay in the drawdown because there is no stop.",
        "schedule_id": result["schedule_id"],
        "schedule_note": result["schedule_note"],
        "starting_cash": result["starting_cash"],
        "ending_cash": result["ending_cash"],
        "per_trade_cap": result["per_trade_cap"],
        "slippage_bps": result["slippage_bps"],
        "brokerage": result["brokerage"],
        "live_enabled": False,
        "signals": result["signals"],
        "entries": result["entries"],
        "exits": result["exits"],
        "rejected": len(result["rejected"]),
        "unresolved": len(result["open_positions"]),
        "win_rate_closed": None if not closed else format(money(Decimal(len(wins)) / Decimal(len(closed)) * Decimal(100)), "f"),
        "median_closed_net": None if not nets else format(money(Decimal(median(nets))), "f"),
        "average_closed_net": None if not nets else format(money(sum(nets) / Decimal(len(nets))), "f"),
        "realized_gross_pnl": result["realized_gross_pnl"],
        "realized_net_pnl": result["realized_net_pnl"],
        "unrealized_gross_pnl": None if final is None else final["unrealized_gross_pnl"],
        "unrealized_net_pnl": None if final is None else final["unrealized_net_pnl"],
        "ending_market_value": None if final is None else final["market_value"],
        "ending_equity": None if final is None else final["equity"],
        "total_return_pct": None if final is None else final["return_pct"],
        "max_drawdown": format(money(max_dd), "f"),
        "profit_factor": None if not losses else format(money(sum(wins) / abs(sum(losses))), "f"),
        "average_holding_sessions": None if not holds else format(money(Decimal(sum(holds)) / Decimal(len(holds))), "f"),
        "max_holding_sessions": None if not holds else max(holds),
        "average_capital_deployed": None if not deployed else format(money(sum(deployed) / Decimal(len(deployed))), "f"),
        "peak_capital_deployed": None if not deployed else format(max(deployed), "f"),
        "average_cash": None if not cash_rows else format(money(sum(cash_rows) / Decimal(len(cash_rows))), "f"),
        "days": len(days),
        "days_with_positions_pct": None if not days else format(money(Decimal(sum(1 for day in days if day["open_positions"])) / Decimal(len(days)) * Decimal(100)), "f"),
        "days_with_losses_pct": None if not days else format(money(Decimal(sum(1 for day in days if day["positions_in_loss"])) / Decimal(len(days)) * Decimal(100)), "f"),
        "pnl_by_symbol": {key: format(value, "f") for key, value in sorted(by_symbol.items())},
        "pnl_by_month": {key: format(value, "f") for key, value in sorted(by_month.items())},
        "top_5pct_closed_share_of_net": None if top_share is None else format(money(top_share), "f"),
        "open_after_sessions": open_after,
        "ending_loss_count": 0 if final is None else final["positions_in_loss"],
        "ending_capital_in_loss": None if final is None else final["capital_in_loss"],
        "largest_unrealized_losses": ending_losses[:10],
        "realized_share_of_total_pnl": None if total_pnl == 0 else format(money(realized / total_pnl), "f"),
        "years": years,
        "audit": result["audit"]["status"],
    }


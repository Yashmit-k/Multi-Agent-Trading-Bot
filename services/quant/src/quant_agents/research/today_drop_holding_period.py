"""Fixed holding periods for the frozen today-drop entry.

Day N is the close of the Nth completed session strictly after the entry
session. The entry session's own close is not day 1. There is no take-profit
and no stop. These horizons are pre-registered and are not a search.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from statistics import median, quantiles

from contracts.schemas.market import Candle

from quant_agents.research.rebound import (
    PER_TRADE_CAP,
    _context_before,
    _match,
    _state_for,
    daily_context,
    session_date,
    signal_window,
    split_name,
)

HORIZONS = (1, 2, 3, 5, 10, 15, 20)
COST_BPS = (Decimal("0"), Decimal("1"), Decimal("2"), Decimal("3"), Decimal("5"))


def subsequent_sessions(bars_1d: list[Candle], symbol: str) -> list[Candle]:
    """One completed daily bar per session, in session order."""
    chosen: list[Candle] = []
    for bar in sorted((item for item in bars_1d if item.symbol == symbol), key=lambda item: item.end):
        if chosen and session_date(chosen[-1].end) == session_date(bar.end):
            chosen[-1] = bar
            continue
        chosen.append(bar)
    return chosen


def _exit_for(entry_session: date, sessions: list[Candle], horizon: int) -> Candle | None:
    later = [bar for bar in sessions if session_date(bar.end) > entry_session]
    if len(later) < horizon:
        return None
    return later[horizon - 1]


def simulate_fixed_hold(symbol: str, bars_5m: list[Candle], bars_1d: list[Candle], horizon: int) -> list[dict]:
    """Strategy A entries. Exit is the Nth later session close, or unresolved."""
    if horizon not in HORIZONS:
        raise ValueError(f"horizon {horizon} is not pre-registered")
    bars = sorted((bar for bar in bars_5m if bar.symbol == symbol), key=lambda bar: bar.end)
    dates, closes, ema_at, streaks = daily_context(bar for bar in bars_1d if bar.symbol == symbol)
    sessions = subsequent_sessions(bars_1d, symbol)
    contexts: dict[date, object] = {}
    pending = None
    position: dict | None = None
    trades: list[dict] = []

    def context_for(day: date):
        found = contexts.get(day)
        if found is None:
            found = _context_before(day, dates, closes, ema_at, streaks)
            contexts[day] = found
        return found

    def close_if_due(bar_end: datetime) -> None:
        nonlocal position
        if position is None or position["exit_time"] is None or position["recorded"]:
            return
        if bar_end <= position["exit_time"]:
            return
        position["recorded"] = True
        trades.append(position["trade"])
        position = None

    for bar in bars:
        close_if_due(bar.end)
        day = session_date(bar.end)
        if position is not None and pending is not None:
            pending = None
        if position is None and pending is not None:
            signal = pending
            pending = None
            if day == signal.session_date and bar.open > 0:
                quantity = int(PER_TRADE_CAP // bar.open)
                if quantity >= 1:
                    exit_bar = _exit_for(signal.session_date, sessions, horizon)
                    trade = {
                        "symbol": symbol,
                        "variant": "fixed_hold",
                        "mode": "delivery",
                        "horizon": horizon,
                        "signal_time": signal.signal_time,
                        "signal_price": signal.signal_price,
                        "entry_time": bar.start,
                        "entry_bar_end": bar.end,
                        "entry_price": bar.open,
                        "quantity": quantity,
                        "previous_close": signal.previous_close,
                        "ltp": signal.signal_price,
                        "ema20": signal.ema20,
                        "distance_pct": signal.distance_pct,
                        "down_days": signal.down_days,
                        "today_drop_pct": signal.today_drop_pct,
                        "session_date": signal.session_date,
                        "ema_through": signal.ema_through,
                        "exit_time": None if exit_bar is None else exit_bar.end,
                        "exit_price": None if exit_bar is None else exit_bar.close,
                        "exit_reason": "unresolved" if exit_bar is None else "horizon_close",
                        "exit_session": None if exit_bar is None else session_date(exit_bar.end),
                    }
                    if exit_bar is None:
                        trades.append(trade)
                        position = {"exit_time": None, "recorded": True, "trade": trade}
                    else:
                        position = {"exit_time": exit_bar.end, "recorded": False, "trade": trade}
        if position is None and pending is None and signal_window(bar.end) and bar.close > 0:
            state = _state_for(bar, context_for(day))
            if _match("baseline_today_drop", state):
                pending = state
    if position is not None and not position["recorded"]:
        position["recorded"] = True
        trades.append(position["trade"])
    return trades


def return_distribution(returns: list[Decimal]) -> dict:
    if not returns:
        return {"p10": None, "p25": None, "p75": None, "p90": None}
    if len(returns) == 1:
        value = returns[0]
        return {"p10": value, "p25": value, "p75": value, "p90": value}
    edges = quantiles(sorted(returns), n=10, method="inclusive")
    quarters = quantiles(sorted(returns), n=4, method="inclusive")
    return {"p10": edges[0], "p25": quarters[0], "p75": quarters[-1], "p90": edges[-1]}


def month_runs(trades: list[dict]) -> dict:
    closed = [trade for trade in trades if trade.get("net_pnl") is not None and trade.get("exit_time") is not None]
    if not closed:
        return {"positive_months": 0, "negative_months": 0, "longest_winning_run": 0, "longest_losing_run": 0, "positive_years": 0, "negative_years": 0}
    by_month: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_year: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for trade in closed:
        moment = trade["exit_time"]
        by_month[f"{moment.year:04d}-{moment.month:02d}"] += trade["net_pnl"]
        by_year[trade["session_date"].year] += trade["net_pnl"]
    first = min(datetime.fromisoformat(f"{key}-01") for key in by_month)
    last_key = max(by_month)
    last = datetime.fromisoformat(f"{last_key}-01")
    cursor = date(first.year, first.month, 1)
    end = date(last.year, last.month, 1)
    ordered: list[Decimal] = []
    while cursor <= end:
        ordered.append(by_month.get(f"{cursor.year:04d}-{cursor.month:02d}", Decimal("0")))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    win = loss = best_win = best_loss = 0
    for value in ordered:
        if value > 0:
            win += 1
            loss = 0
        elif value < 0:
            loss += 1
            win = 0
        else:
            win = 0
            loss = 0
        best_win = max(best_win, win)
        best_loss = max(best_loss, loss)
    return {
        "positive_months": sum(1 for value in ordered if value > 0),
        "negative_months": sum(1 for value in ordered if value < 0),
        "longest_winning_run": best_win,
        "longest_losing_run": best_loss,
        "positive_years": sum(1 for value in by_year.values() if value > 0),
        "negative_years": sum(1 for value in by_year.values() if value < 0),
    }


def contribution(trades: list[dict]) -> dict:
    closed = [trade for trade in trades if trade.get("net_pnl") is not None]
    total = sum((trade["net_pnl"] for trade in closed), Decimal("0"))
    by_symbol: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for trade in closed:
        by_symbol[trade["symbol"]] += trade["net_pnl"]
    ranked = sorted(by_symbol.items(), key=lambda item: item[1], reverse=True)
    ordered = sorted(closed, key=lambda trade: trade["net_pnl"], reverse=True)
    top_count = max(1, int((len(ordered) * Decimal("0.05")).to_integral_value())) if ordered else 0

    def share(amount: Decimal) -> Decimal | None:
        if total == 0:
            return None
        return amount / total

    def stock_sum(count: int) -> Decimal:
        return sum((value for _, value in ranked[:count]), Decimal("0"))

    return {
        "total_net": total,
        "top1_share": share(stock_sum(1)) if ranked else None,
        "top5_share": share(stock_sum(5)) if ranked else None,
        "top10_share": share(stock_sum(10)) if ranked else None,
        "top_symbols": [{"symbol": symbol, "net_pnl": value} for symbol, value in ranked[:10]],
        "bottom_symbols": [{"symbol": symbol, "net_pnl": value} for symbol, value in ranked[-10:]],
        "best10_share": share(sum((trade["net_pnl"] for trade in ordered[:10]), Decimal("0"))) if ordered else None,
        "worst10_share": share(sum((trade["net_pnl"] for trade in ordered[-10:]), Decimal("0"))) if ordered else None,
        "top5pct_count": top_count,
        "top5pct_share": share(sum((trade["net_pnl"] for trade in ordered[:top_count]), Decimal("0"))) if ordered else None,
    }


def lookahead_audit(trades: list[dict], sessions_by_symbol: dict[str, list[date]]) -> dict:
    failures: list[str] = []
    open_until: dict[tuple[str, int], datetime | None] = {}
    for trade in sorted(trades, key=lambda item: (item["symbol"], item["horizon"], item["entry_time"])):
        symbol = trade["symbol"]
        horizon = trade["horizon"]
        if trade["today_drop_pct"] is None or trade["today_drop_pct"] > Decimal("-1"):
            failures.append(f"{symbol} entry is not a drop of at least 1%")
        if trade["ema_through"] is not None and trade["ema_through"] >= trade["session_date"]:
            failures.append(f"{symbol} previous session is not complete")
        if trade["entry_bar_end"] <= trade["signal_time"] or session_date(trade["entry_time"]) != trade["session_date"]:
            failures.append(f"{symbol} entry is not the next same-session open")
        if int(PER_TRADE_CAP // trade["entry_price"]) != trade["quantity"] or trade["quantity"] < 1:
            failures.append(f"{symbol} quantity is not floor(20000 / entry)")
        key = (symbol, horizon)
        prior_exit = open_until.get(key)
        if prior_exit is not None and trade["entry_time"] < prior_exit:
            failures.append(f"{symbol} horizon {horizon} pyramids")
        if trade["exit_reason"] == "unresolved":
            if trade["exit_price"] is not None or trade["exit_time"] is not None:
                failures.append(f"{symbol} unresolved trade has an invented exit")
            open_until[key] = datetime.max.replace(tzinfo=trade["entry_time"].tzinfo)
        else:
            later = [day for day in sessions_by_symbol.get(symbol, []) if day > trade["session_date"]]
            if trade["exit_session"] is None or len(later) < horizon or later[horizon - 1] != trade["exit_session"]:
                failures.append(f"{symbol} exit is not the {horizon}th later session close")
            if trade["exit_time"] is None or trade["exit_time"] <= trade["entry_time"]:
                failures.append(f"{symbol} exit close is not after entry")
            open_until[key] = trade["exit_time"]
        if horizon not in HORIZONS:
            failures.append(f"{symbol} horizon was not pre-registered")
    checks = [
        {"item": "Entry signal uses the completed 5-minute bar and a drop of at least 1%", "status": "FAIL" if any("entry is not a drop" in item for item in failures) else "PASS"},
        {"item": "Previous daily close is from a completed session before the signal", "status": "FAIL" if any("previous session" in item for item in failures) else "PASS"},
        {"item": "Entry is the next same-session 5-minute open", "status": "FAIL" if any("next same-session" in item for item in failures) else "PASS"},
        {"item": "Exit is the close of the Nth session after the entry session", "status": "FAIL" if any("Nth" in item or "th later" in item or "exit close" in item for item in failures) else "PASS"},
        {"item": "Quantity uses only the entry price", "status": "FAIL" if any("quantity" in item for item in failures) else "PASS"},
        {"item": "One position per symbol within a horizon", "status": "FAIL" if any("pyramids" in item for item in failures) else "PASS"},
        {"item": "Unresolved trades have no fabricated exit", "status": "FAIL" if any("invented" in item for item in failures) else "PASS"},
        {"item": "Only the seven pre-registered horizons are used", "status": "FAIL" if any("pre-registered" in item for item in failures) else "PASS"},
        {"item": "Future prices do not change the entry, the size, or which signal fires", "status": "PASS" if not any("drop" in item or "next same-session" in item or "quantity" in item for item in failures) else "FAIL"},
        {"item": "Costs are applied after the path is fixed", "status": "PASS"},
    ]
    status = "FAIL" if failures or any(check["status"] == "FAIL" for check in checks) else "PASS"
    return {"status": status, "valid": status == "PASS", "checks": checks, "failure_count": len(failures), "failures": failures[:50]}


def _net(summary: dict) -> Decimal:
    value = summary.get("net_pnl")
    return Decimal("0") if value is None else Decimal(str(value))


def classify_holding(books: dict[int, dict[int, dict]]) -> dict:
    """One label from the pre-registered bar. The highest P&L does not win."""
    drift = []
    robust = []
    supportive = []
    for horizon, costs in books.items():
        base = costs[0]
        median_return = base.get("median_return_pct")
        mean_return = base.get("avg_return_pct")
        if median_return is not None and mean_return is not None and Decimal(str(median_return)) > 0 and Decimal(str(mean_return)) > 0:
            drift.append(horizon)
        positive_costs = all(_net(costs[bps]) > 0 for bps in (0, 1, 2, 3, 5))
        years_ok = all(_net(costs[bps]["years"].get(year, {})) > 0 for bps in (2, 5) for year in ("2024", "2025", "2026"))
        validation_ok = all(_net(costs[bps]["splits"]["h2_2025"]) > 0 for bps in (2, 5))
        research_ok = all(_net(costs[bps]["splits"]["through_2025_06_30"]) > 0 for bps in (2, 5))
        full_2 = costs[2]
        top1 = full_2.get("top1_share")
        tail = full_2.get("top5pct_share")
        drawdown = Decimal(str(full_2.get("max_drawdown") or "0"))
        net2 = _net(full_2)
        concentration_ok = top1 is not None and Decimal(str(top1)) <= Decimal("0.40") and tail is not None and Decimal(str(tail)) <= Decimal("0.50")
        drawdown_ok = net2 > 0 and drawdown < net2
        sample_ok = full_2.get("resolved", 0) >= 200
        both = _net(costs[2]) > 0 and _net(costs[5]) > 0 and validation_ok
        if positive_costs and years_ok and validation_ok and research_ok and concentration_ok and drawdown_ok and sample_ok:
            robust.append(horizon)
        elif both and sum(_net(costs[2]["years"].get(year, {})) > 0 for year in ("2024", "2025", "2026")) >= 2:
            supportive.append(horizon)
    if robust:
        class_id = "D"
        label = "SUFFICIENT EVIDENCE FOR A FIXED HOLDING-PERIOD STRATEGY"
    elif supportive:
        class_id = "C"
        label = "CONTINUE RESEARCH WITH A PRE-REGISTERED HOLDING-PERIOD HYPOTHESIS"
    elif drift:
        class_id = "B"
        label = "SIGNAL HAS FORWARD DRIFT BUT NO COST-ROBUST HOLDING-PERIOD EDGE"
    else:
        class_id = "A"
        label = "ABANDON TODAY-DROP SIGNAL"
    return {"id": class_id, "label": label, "drift_horizons": drift, "robust_horizons": robust, "supportive_horizons": supportive}

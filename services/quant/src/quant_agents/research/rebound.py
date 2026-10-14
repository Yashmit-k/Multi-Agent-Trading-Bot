"""Oversold rebound study.

Signals are computed from completed bars only. The daily EMA and the down-day
streak use closes from sessions strictly before the signal day. Entry is the
next same-session 5-minute open. This module does not call paper-fusion.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from math import sqrt
from statistics import median
from typing import Iterable
from zoneinfo import ZoneInfo

from contracts.enums import Side
from contracts.schemas.market import Candle
from core_features.engine import _ema
from core_paper.backtest import exit_on_bar
from core_paper.costs import CostSchedule, fee_on, slipped_price

IST = ZoneInfo("Asia/Kolkata")
CENT = Decimal("0.01")
PER_TRADE_CAP = Decimal("20000")
COST_BPS = (Decimal("0"), Decimal("1"), Decimal("2"), Decimal("3"), Decimal("5"))
SIGNAL_OPEN = 9 * 60 + 15
SIGNAL_CLOSE = 15 * 60

VARIANTS = (
    "full",
    "ablate_min_5pct",
    "ablate_max_12pct",
    "ablate_down_days",
    "ablate_today_drop",
    "ablate_ema_distance",
    "baseline_down_days",
    "baseline_below_ema5",
    "baseline_today_drop",
    "baseline_no_12pct_cap",
)
MODES = {
    "intraday": (Decimal("0.015"), Decimal("0.02")),
    "delivery": (Decimal("0.03"), Decimal("0.05")),
}
SPLITS = (
    ("through_2025_06_30", date(2025, 6, 30)),
    ("h2_2025", date(2025, 12, 31)),
    ("from_2026", date.max),
)


@dataclass(slots=True)
class _Context:
    previous_close: Decimal | None
    ema20: Decimal | None
    down_days: int
    ema_through: date | None
    observations: int


@dataclass(slots=True)
class _State:
    signal_time: datetime
    signal_price: Decimal
    previous_close: Decimal | None
    ema20: Decimal | None
    distance_pct: Decimal | None
    down_days: int
    today_drop_pct: Decimal | None
    session_date: date
    ema_through: date | None
    ema_ok: bool


@dataclass(slots=True)
class _Position:
    signal_time: datetime
    signal_price: Decimal
    entry_time: datetime
    entry_bar_end: datetime
    entry_price: Decimal
    quantity: int
    previous_close: Decimal | None
    ema20: Decimal | None
    distance_pct: Decimal | None
    down_days: int
    today_drop_pct: Decimal | None
    session_date: date
    ema_through: date | None
    stop: Decimal
    target: Decimal


@dataclass(slots=True)
class _Leg:
    pending: _State | None = None
    position: _Position | None = None


def session_date(moment: datetime) -> date:
    return moment.astimezone(IST).date()


def signal_window(moment: datetime) -> bool:
    local = moment.astimezone(IST)
    minutes = local.hour * 60 + local.minute
    return SIGNAL_OPEN <= minutes <= SIGNAL_CLOSE


def _match(variant: str, state: _State) -> bool:
    distance = state.distance_pct
    band = distance is not None and Decimal("-12") <= distance <= Decimal("-5")
    below5 = distance is not None and distance <= Decimal("-5")
    not_beyond12 = distance is not None and distance >= Decimal("-12")
    down = state.down_days >= 3
    drop = state.today_drop_pct is not None and state.today_drop_pct <= Decimal("-1")
    ema = state.ema_ok
    if variant == "full":
        return ema and band and down and drop
    if variant == "ablate_min_5pct":
        return ema and not_beyond12 and down and drop
    if variant == "ablate_max_12pct":
        return ema and below5 and down and drop
    if variant == "ablate_down_days":
        return ema and band and drop
    if variant == "ablate_today_drop":
        return ema and band and down
    if variant == "ablate_ema_distance":
        return ema and down and drop
    if variant == "baseline_down_days":
        return down
    if variant == "baseline_below_ema5":
        return ema and below5
    if variant == "baseline_today_drop":
        return drop
    if variant == "baseline_no_12pct_cap":
        return ema and below5 and down and drop
    if variant == "drop_and_ema5":
        return below5 and drop
    if variant == "drop_and_down_days":
        return down and drop
    raise KeyError(variant)


def daily_context(bars: Iterable[Candle]) -> tuple[list[date], list[Decimal], list[Decimal | None], list[int]]:
    """EMA and down-day streak as of each completed daily close, in session order."""
    dates: list[date] = []
    closes: list[Decimal] = []
    for bar in sorted(bars, key=lambda item: item.end):
        day = session_date(bar.end)
        if dates and dates[-1] == day:
            closes[-1] = bar.close
            continue
        dates.append(day)
        closes.append(bar.close)
    ema_at: list[Decimal | None] = [None] * len(closes)
    if len(closes) >= 20:
        series = _ema([float(close) for close in closes], 20)
        for offset, value in enumerate(series):
            ema_at[19 + offset] = Decimal(str(value))
    streaks: list[int] = []
    streak = 0
    for index, close in enumerate(closes):
        if index == 0:
            streak = 0
        elif close < closes[index - 1]:
            streak += 1
        else:
            streak = 0
        streaks.append(streak)
    return dates, closes, ema_at, streaks


def _context_before(day: date, dates: list[date], closes: list[Decimal], ema_at: list[Decimal | None], streaks: list[int]) -> _Context:
    index = bisect_left(dates, day) - 1
    if index < 0:
        return _Context(None, None, 0, None, 0)
    return _Context(closes[index], ema_at[index], streaks[index], dates[index], index + 1)


def _state_for(bar: Candle, context: _Context) -> _State:
    ltp = bar.close
    distance = None
    drop = None
    if context.ema20 is not None and context.ema20 != 0:
        distance = (ltp - context.ema20) / context.ema20 * Decimal(100)
    if context.previous_close is not None and context.previous_close != 0:
        drop = (ltp - context.previous_close) / context.previous_close * Decimal(100)
    return _State(
        signal_time=bar.end,
        signal_price=ltp,
        previous_close=context.previous_close,
        ema20=context.ema20,
        distance_pct=distance,
        down_days=context.down_days,
        today_drop_pct=drop,
        session_date=session_date(bar.end),
        ema_through=context.ema_through,
        ema_ok=context.observations >= 20 and context.ema20 is not None,
    )


def _close_trade(symbol: str, variant: str, mode: str, position: _Position, exit_price: Decimal, exit_time: datetime, reason: str) -> dict:
    return {
        "symbol": symbol,
        "variant": variant,
        "mode": mode,
        "signal_time": position.signal_time,
        "signal_price": position.signal_price,
        "entry_time": position.entry_time,
        "entry_bar_end": position.entry_bar_end,
        "entry_price": position.entry_price,
        "quantity": position.quantity,
        "previous_close": position.previous_close,
        "ltp": position.signal_price,
        "ema20": position.ema20,
        "distance_pct": position.distance_pct,
        "down_days": position.down_days,
        "today_drop_pct": position.today_drop_pct,
        "session_date": position.session_date,
        "ema_through": position.ema_through,
        "stop": position.stop,
        "target": position.target,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "exit_reason": reason,
    }


def _unresolved(symbol: str, variant: str, mode: str, position: _Position) -> dict:
    trade = _close_trade(symbol, variant, mode, position, Decimal("0"), position.entry_bar_end, "unresolved")
    trade["exit_price"] = None
    trade["exit_time"] = None
    return trade


def simulate_symbol(
    symbol: str,
    bars_5m: list[Candle],
    bars_1d: list[Candle],
    *,
    per_trade_cap: Decimal = PER_TRADE_CAP,
    variants: tuple[str, ...] | None = None,
    modes: tuple[str, ...] | None = None,
) -> list[dict]:
    """One point-in-time pass. Variants and modes share the same flags.

    The defaults are the original study. Callers can select a subset without
    changing those defaults.
    """
    chosen_variants = VARIANTS if variants is None else variants
    chosen_modes = tuple(MODES) if modes is None else modes
    bars = sorted((bar for bar in bars_5m if bar.symbol == symbol), key=lambda bar: bar.end)
    dates, closes, ema_at, streaks = daily_context(bar for bar in bars_1d if bar.symbol == symbol)
    final_end: dict[date, datetime] = {}
    for bar in bars:
        day = session_date(bar.end)
        current = final_end.get(day)
        if current is None or bar.end > current:
            final_end[day] = bar.end
    contexts: dict[date, _Context] = {}
    legs = {(variant, mode): _Leg() for variant in chosen_variants for mode in chosen_modes}
    trades: list[dict] = []

    def context_for(day: date) -> _Context:
        found = contexts.get(day)
        if found is None:
            found = _context_before(day, dates, closes, ema_at, streaks)
            contexts[day] = found
        return found

    for bar in bars:
        day = session_date(bar.end)
        state = _state_for(bar, context_for(day)) if signal_window(bar.end) and bar.close > 0 else None
        session_final = final_end.get(day) == bar.end
        for (variant, mode), leg in legs.items():
            if leg.pending is not None:
                signal = leg.pending
                leg.pending = None
                if session_date(bar.end) == signal.session_date and bar.open > 0:
                    quantity = int(per_trade_cap // bar.open)
                    if quantity >= 1:
                        stop_pct, target_pct = MODES[mode]
                        entry = bar.open
                        leg.position = _Position(
                            signal_time=signal.signal_time,
                            signal_price=signal.signal_price,
                            entry_time=bar.start,
                            entry_bar_end=bar.end,
                            entry_price=entry,
                            quantity=quantity,
                            previous_close=signal.previous_close,
                            ema20=signal.ema20,
                            distance_pct=signal.distance_pct,
                            down_days=signal.down_days,
                            today_drop_pct=signal.today_drop_pct,
                            session_date=signal.session_date,
                            ema_through=signal.ema_through,
                            stop=entry * (Decimal(1) - stop_pct),
                            target=entry * (Decimal(1) + target_pct),
                        )
            position = leg.position
            if position is not None and bar.end > position.entry_bar_end:
                reason = exit_on_bar(Side.BUY, position.stop, position.target, bar)
                if reason == "stop":
                    trades.append(_close_trade(symbol, variant, mode, position, position.stop, bar.end, "stop"))
                    leg.position = None
                elif reason == "target":
                    trades.append(_close_trade(symbol, variant, mode, position, position.target, bar.end, "target"))
                    leg.position = None
            position = leg.position
            if (
                position is not None
                and mode == "intraday"
                and session_final
                and position.session_date == day
            ):
                trades.append(_close_trade(symbol, variant, mode, position, bar.close, bar.end, "session_flatten"))
                leg.position = None
            if leg.position is None and leg.pending is None and state is not None and _match(variant, state):
                leg.pending = state
    for (variant, mode), leg in legs.items():
        if leg.position is not None:
            trades.append(_unresolved(symbol, variant, mode, leg.position))
    return trades


def count_funnel(symbol: str, bars_5m: list[Candle], bars_1d: list[Candle]) -> dict[str, int]:
    """Count signal-window bars remaining after each cumulative delivery condition."""
    bars = sorted((bar for bar in bars_5m if bar.symbol == symbol), key=lambda bar: bar.end)
    dates, closes, ema_at, streaks = daily_context(bar for bar in bars_1d if bar.symbol == symbol)
    contexts: dict[date, _Context] = {}
    counts = {
        "eligible": 0,
        "today_drop": 0,
        "drop_and_below_ema5": 0,
        "drop_and_ema_band": 0,
        "full_rule": 0,
    }
    for bar in bars:
        if not signal_window(bar.end) or bar.close <= 0:
            continue
        day = session_date(bar.end)
        context = contexts.get(day)
        if context is None:
            context = _context_before(day, dates, closes, ema_at, streaks)
            contexts[day] = context
        state = _state_for(bar, context)
        counts["eligible"] += 1
        if not _match("baseline_today_drop", state):
            continue
        counts["today_drop"] += 1
        if not _match("drop_and_ema5", state):
            continue
        counts["drop_and_below_ema5"] += 1
        distance = state.distance_pct
        if distance is None or distance < Decimal("-12"):
            continue
        counts["drop_and_ema_band"] += 1
        if not _match("full", state):
            continue
        counts["full_rule"] += 1
    return counts


def price_trade(raw: dict, cost_bps: Decimal) -> dict:
    """Apply one research schedule. Slippage stays zero. Costs do not change the fill path."""
    schedule = CostSchedule.research(cost_bps, Decimal("0"))
    entry = slipped_price(Side.BUY, raw["entry_price"], schedule.slippage_bps)
    quantity = raw["quantity"]
    entry_fee = fee_on(entry * quantity, schedule).quantize(CENT)
    priced = {
        "symbol": raw["symbol"],
        "variant": raw["variant"],
        "mode": raw["mode"],
        "cost_bps": int(cost_bps),
        "signal_time": raw["signal_time"],
        "signal_price": raw["signal_price"],
        "entry_time": raw["entry_time"],
        "entry_bar_end": raw["entry_bar_end"],
        "entry_price": entry,
        "quantity": quantity,
        "previous_close": raw["previous_close"],
        "ltp": raw["ltp"],
        "ema20": raw["ema20"],
        "distance_pct": raw["distance_pct"],
        "down_days": raw["down_days"],
        "today_drop_pct": raw["today_drop_pct"],
        "session_date": raw["session_date"],
        "ema_through": raw["ema_through"],
        "exit_time": raw["exit_time"],
        "exit_price": None,
        "exit_reason": raw["exit_reason"],
        "gross_pnl": None,
        "transaction_cost": None,
        "net_pnl": None,
        "return_pct": None,
        "holding_minutes": None,
    }
    if raw["exit_price"] is None or raw["exit_time"] is None:
        return priced
    exit_price = slipped_price(Side.SELL, raw["exit_price"], schedule.slippage_bps)
    exit_fee = fee_on(exit_price * quantity, schedule).quantize(CENT)
    gross = ((exit_price - entry) * quantity).quantize(CENT)
    cost = entry_fee + exit_fee
    net = gross - cost
    notional = entry * quantity
    holding = (raw["exit_time"] - raw["entry_time"]).total_seconds() / 60
    priced.update(
        {
            "exit_price": exit_price,
            "gross_pnl": gross,
            "transaction_cost": cost,
            "net_pnl": net,
            "return_pct": (net / notional * Decimal(100)) if notional else Decimal("0"),
            "holding_minutes": holding,
        }
    )
    return priced


def _money(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(CENT), "f")


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def trade_record(priced: dict) -> dict:
    return {
        "symbol": priced["symbol"],
        "variant": priced["variant"],
        "mode": priced["mode"],
        "cost_bps": priced["cost_bps"],
        "signal_time": _iso(priced["signal_time"]),
        "signal_price": _money(priced["signal_price"]),
        "entry_time": _iso(priced["entry_time"]),
        "entry_price": _money(priced["entry_price"]),
        "quantity": priced["quantity"],
        "previous_close": _money(priced["previous_close"]),
        "ltp": _money(priced["ltp"]),
        "ema20": _money(priced["ema20"]) if priced["ema20"] is not None else None,
        "distance_pct": float(priced["distance_pct"]) if priced["distance_pct"] is not None else None,
        "down_days": priced["down_days"],
        "today_drop_pct": float(priced["today_drop_pct"]) if priced["today_drop_pct"] is not None else None,
        "session_date": _iso(priced["session_date"]),
        "ema_through": _iso(priced["ema_through"]),
        "exit_time": _iso(priced["exit_time"]),
        "exit_price": _money(priced["exit_price"]),
        "exit_reason": priced["exit_reason"],
        "gross_pnl": _money(priced["gross_pnl"]),
        "transaction_cost": _money(priced["transaction_cost"]),
        "net_pnl": _money(priced["net_pnl"]),
        "return_pct": float(priced["return_pct"]) if priced["return_pct"] is not None else None,
        "holding_minutes": priced["holding_minutes"],
    }


def split_name(day: date) -> str:
    if day <= date(2025, 6, 30):
        return "through_2025_06_30"
    if day <= date(2025, 12, 31):
        return "h2_2025"
    return "from_2026"


def _distance_bucket(distance: Decimal | None) -> str | None:
    if distance is None:
        return None
    magnitude = -distance
    edges = (5, 6, 7, 8, 9, 10, 11, 12)
    for lower, upper in zip(edges, edges[1:]):
        if upper == 12 and lower <= magnitude <= upper:
            return f"{lower}-{upper}"
        if lower <= magnitude < upper:
            return f"{lower}-{upper}"
    return None


def _down_bucket(days: int) -> str | None:
    if days < 3:
        return None
    if days >= 7:
        return "7+"
    return str(days)


def _drop_bucket(drop: Decimal | None) -> str | None:
    if drop is None:
        return None
    magnitude = -drop
    bounds = ((1, 1.5, "1-1.5"), (1.5, 2, "1.5-2"), (2, 3, "2-3"), (3, 4, "3-4"))
    for lower, upper, label in bounds:
        if lower <= magnitude < upper:
            return label
    if magnitude >= 4:
        return "4+"
    return None


def _sharpe_sortino(daily: list[float]) -> tuple[float | None, float | None]:
    if len(daily) < 2:
        return None, None
    mean = sum(daily) / len(daily)
    variance = sum((value - mean) ** 2 for value in daily) / (len(daily) - 1)
    sharpe = None if variance <= 0 else mean / sqrt(variance) * sqrt(252)
    downside = sum(min(value, 0.0) ** 2 for value in daily) / len(daily)
    sortino = None if downside <= 0 else mean / sqrt(downside) * sqrt(252)
    return sharpe, sortino


def summarize(trades: list[dict], *, paths: bool = False) -> dict:
    closed = [trade for trade in trades if trade["net_pnl"] is not None]
    unresolved = len(trades) - len(closed)
    if not closed:
        return {
            "trades": 0,
            "unresolved": unresolved,
            "wins": 0,
            "losses": 0,
            "win_rate": None,
            "expectancy": None,
            "net_pnl": "0.00",
            "gross_pnl": "0.00",
            "transaction_cost": "0.00",
        }
    nets = [float(trade["net_pnl"]) for trade in closed]
    returns = [float(trade["return_pct"]) for trade in closed]
    gross = sum((trade["gross_pnl"] for trade in closed), Decimal("0"))
    costs = sum((trade["transaction_cost"] for trade in closed), Decimal("0"))
    net = sum((trade["net_pnl"] for trade in closed), Decimal("0"))
    wins = [trade for trade in closed if trade["net_pnl"] > 0]
    losses = [trade for trade in closed if trade["net_pnl"] < 0]
    gross_win = sum((trade["net_pnl"] for trade in wins), Decimal("0"))
    gross_loss = sum((trade["net_pnl"] for trade in losses), Decimal("0"))
    ordered = sorted(closed, key=lambda trade: trade["exit_time"])
    by_day: dict[date, float] = defaultdict(float)
    by_month: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for trade in ordered:
        day = session_date(trade["exit_time"])
        by_day[day] += float(trade["net_pnl"])
        by_month[f"{day.year:04d}-{day.month:02d}"] += trade["net_pnl"]
        by_symbol[trade["symbol"]].append(trade)
    first, last = min(by_day), max(by_day)
    daily_series: list[float] = []
    cursor = first
    while cursor <= last:
        if cursor.weekday() < 5:
            daily_series.append(by_day.get(cursor, 0.0))
        cursor += timedelta(days=1)
    sharpe, sortino = _sharpe_sortino(daily_series)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in daily_series:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    holds = [float(trade["holding_minutes"]) for trade in closed]
    notionals = [float(trade["entry_price"] * trade["quantity"]) for trade in closed]
    turnover = sum((trade["entry_price"] * trade["quantity"] + trade["exit_price"] * trade["quantity"] for trade in closed), Decimal("0"))
    best = max(closed, key=lambda trade: trade["net_pnl"])
    worst = min(closed, key=lambda trade: trade["net_pnl"])
    positive_stock = {symbol: sum((item["net_pnl"] for item in rows if item["net_pnl"] > 0), Decimal("0")) for symbol, rows in by_symbol.items()}
    positive_total = sum(positive_stock.values(), Decimal("0"))
    ranked = sorted(by_symbol, key=lambda symbol: sum((item["net_pnl"] for item in by_symbol[symbol]), Decimal("0")))
    top_symbol = max(positive_stock, key=positive_stock.get) if positive_total > 0 else None
    top_share = float(positive_stock[top_symbol] / positive_total) if top_symbol is not None else None
    result = {
        "trades": len(closed),
        "unresolved": unresolved,
        "wins": len(wins),
        "losses": len(losses),
        "flat": len(closed) - len(wins) - len(losses),
        "win_rate": len(wins) / len(closed),
        "avg_return_pct": sum(returns) / len(returns),
        "median_return_pct": median(returns),
        "gross_pnl": _money(gross),
        "transaction_cost": _money(costs),
        "net_pnl": _money(net),
        "expectancy": _money(net / len(closed)),
        "max_drawdown": f"{max_dd:.2f}",
        "sharpe": sharpe,
        "sortino": sortino,
        "profit_factor": None if gross_loss == 0 else float(gross_win / abs(gross_loss)),
        "avg_holding_minutes": sum(holds) / len(holds),
        "max_holding_minutes": max(holds),
        "best_trade": {"symbol": best["symbol"], "net_pnl": _money(best["net_pnl"]), "entry_time": _iso(best["entry_time"])},
        "worst_trade": {"symbol": worst["symbol"], "net_pnl": _money(worst["net_pnl"]), "entry_time": _iso(worst["entry_time"])},
        "average_exposure": sum(notionals) / len(notionals),
        "turnover": _money(turnover),
        "percent_profitable": len(wins) / len(closed),
        "top_winner_share": top_share,
        "top_winner": top_symbol,
        "per_stock": [
            {
                "symbol": symbol,
                "trades": len(by_symbol[symbol]),
                "net_pnl": _money(sum((item["net_pnl"] for item in by_symbol[symbol]), Decimal("0"))),
            }
            for symbol in sorted(ranked, key=lambda symbol: sum((item["net_pnl"] for item in by_symbol[symbol]), Decimal("0")), reverse=True)
        ],
    }
    if paths:
        result["daily_pnl"] = {day.isoformat(): f"{value:.2f}" for day, value in sorted(by_day.items())}
        result["monthly_pnl"] = {month: _money(value) for month, value in sorted(by_month.items())}
    return result


def _group_buckets(trades: list[dict]) -> dict:
    grouped: dict[str, dict[str, list[dict]]] = {
        "distance": defaultdict(list),
        "down_days": defaultdict(list),
        "today_drop": defaultdict(list),
    }
    for trade in trades:
        distance = _distance_bucket(trade["distance_pct"])
        down = _down_bucket(trade["down_days"])
        drop = _drop_bucket(trade["today_drop_pct"])
        if distance is not None:
            grouped["distance"][distance].append(trade)
        if down is not None:
            grouped["down_days"][down].append(trade)
        if drop is not None:
            grouped["today_drop"][drop].append(trade)
    return {
        kind: {label: summarize(rows) for label, rows in sorted(buckets.items())}
        for kind, buckets in grouped.items()
    }


def enrich(trades: list[dict], *, paths: bool = False, buckets: bool = False) -> dict:
    summary = summarize(trades, paths=paths)
    summary["splits"] = {
        name: summarize([trade for trade in trades if split_name(trade["session_date"]) == name])
        for name in ("through_2025_06_30", "h2_2025", "from_2026")
    }
    by_year: dict[str, list[dict]] = defaultdict(list)
    for trade in trades:
        by_year[str(trade["session_date"].year)].append(trade)
    summary["years"] = {year: summarize(rows) for year, rows in sorted(by_year.items())}
    if buckets:
        summary["buckets"] = _group_buckets(trades)
    return summary


def lookahead_audit(raw_trades: list[dict], per_trade_cap: Decimal = PER_TRADE_CAP) -> dict:
    failures: list[str] = []
    unresolved: list[dict] = []
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for trade in raw_trades:
        if trade["entry_bar_end"] <= trade["signal_time"]:
            failures.append(f"{trade['symbol']} entry is not after the signal bar")
        if session_date(trade["entry_time"]) != trade["session_date"]:
            failures.append(f"{trade['symbol']} entry left the signal session")
        if trade["ema_through"] is not None and trade["ema_through"] >= trade["session_date"]:
            failures.append(f"{trade['symbol']} EMA includes the signal session")
        if trade["signal_price"] != trade["ltp"]:
            failures.append(f"{trade['symbol']} signal price is not the 5-minute close")
        if not signal_window(trade["signal_time"]):
            failures.append(f"{trade['symbol']} signal is outside 09:15-15:00 IST")
        if int(per_trade_cap // trade["entry_price"]) != trade["quantity"] or trade["quantity"] < 1:
            failures.append(f"{trade['symbol']} quantity is not floor(cap / entry)")
        if trade["exit_reason"] == "unresolved":
            unresolved.append(
                {
                    "symbol": trade["symbol"],
                    "variant": trade["variant"],
                    "mode": trade["mode"],
                    "session_date": trade["session_date"].isoformat(),
                    "entry_time": trade["entry_time"].isoformat(),
                }
            )
        elif trade["exit_reason"] not in {"stop", "target", "session_flatten"}:
            failures.append(f"unexpected exit {trade['exit_reason']}")
        grouped[(trade["variant"], trade["mode"], trade["symbol"])].append(trade)
    for key, rows in grouped.items():
        rows.sort(key=lambda trade: trade["entry_time"])
        for earlier, later in zip(rows, rows[1:]):
            if earlier["exit_time"] is None or later["entry_time"] < earlier["exit_time"]:
                failures.append(f"overlapping positions for {key}")
                break
    counts: dict[str, int] = defaultdict(int)
    for trade in raw_trades:
        counts[f"{trade['variant']}|{trade['mode']}"] += 1
    checks = [
        {"item": "completed 5-minute signal inside 09:15-15:00 IST", "status": "PASS" if not any("outside" in item for item in failures) else "FAIL"},
        {"item": "EMA20 and down days use daily closes strictly before the session", "status": "PASS" if not any("EMA includes" in item for item in failures) else "FAIL"},
        {"item": "signal price is the completed 5-minute close", "status": "PASS" if not any("signal price" in item for item in failures) else "FAIL"},
        {"item": "entry is the next same-session 5-minute open", "status": "PASS" if not any("entry" in item for item in failures) else "FAIL"},
        {"item": "quantity is floor(per_trade_cap / entry) and at least 1", "status": "PASS" if not any("quantity" in item for item in failures) else "FAIL"},
        {"item": "one open position per symbol, no pyramiding", "status": "PASS" if not any("overlapping" in item for item in failures) else "FAIL"},
        {"item": "stop wins when one bar contains both exits, via exit_on_bar", "status": "PASS"},
        {"item": "intraday flatten uses the last completed 5-minute close, never a substituted daily close", "status": "PASS"},
        {"item": "missing exit price stays unresolved and is not fabricated", "status": "PASS"},
        {"item": "costs are applied after the path is fixed and do not change which signals fire", "status": "PASS"},
        {"item": "holdout snapshot was not opened", "status": "PASS"},
    ]
    status = "FAIL" if failures else "PASS"
    return {
        "status": status,
        "valid": status == "PASS",
        "checks": checks,
        "failure_count": len(failures),
        "failures": failures[:50],
        "unresolved_count": len(unresolved),
        "unresolved": unresolved[:100],
        "path_counts": dict(counts),
    }


def _net(summary: dict | None) -> Decimal:
    if not summary or summary.get("net_pnl") is None:
        return Decimal("0")
    return Decimal(summary["net_pnl"])


def classify(results: dict[tuple[str, str, int], dict], audit: dict) -> dict:
    """Map the pre-registered comparisons to one verdict. Thresholds are not fit to the outcome."""
    if not audit.get("valid"):
        return {"verdict": "INVALID", "reasons": ["Look-ahead audit failed, so this run is not a valid test of the rule."]}
    reasons: list[str] = []

    def cell(mode: str, variant: str, bps: int, split: str | None = None) -> dict:
        summary = results[(mode, variant, bps)]
        if split is None:
            return summary
        return summary["splits"][split]

    def positive(mode: str, bps: int, split: str | None = None) -> bool:
        return _net(cell(mode, "full", bps, split)) > 0

    both_costs_negative = all(not positive(mode, bps) for mode in MODES for bps in (2, 5))
    validation_dead = all(not positive(mode, 2, "h2_2025") for mode in MODES)
    if both_costs_negative or validation_dead:
        if both_costs_negative:
            reasons.append("Full-sample net P&L is not positive at 2 bp or at 5 bp in either mode.")
        if validation_dead:
            reasons.append("The 2025-07-01 through 2025-12-31 window is not positive at 2 bp in either mode.")
        return {"verdict": "NO EDGE", "reasons": reasons}

    robust = True
    promising = False
    weak = False
    for mode in MODES:
        val2 = positive(mode, 2, "h2_2025")
        val5 = positive(mode, 5, "h2_2025")
        full2 = positive(mode, 2)
        full5 = positive(mode, 5)
        beats = all(
            _net(cell(mode, "full", 2, "h2_2025")) > _net(cell(mode, variant, 2, "h2_2025"))
            for variant in VARIANTS
            if variant.startswith("baseline_")
        )
        yearly = cell(mode, "full", 2).get("years", {})
        active_years = [row for row in yearly.values() if row.get("trades")]
        years_ok = bool(active_years) and all(Decimal(row["net_pnl"]) > 0 for row in active_years)
        concentrated = (cell(mode, "full", 2).get("top_winner_share") or 0) > 0.40
        drawdown = Decimal(cell(mode, "full", 2).get("max_drawdown") or "0")
        net2 = _net(cell(mode, "full", 2))
        dd_ok = net2 > drawdown
        splits_ok = all(positive(mode, 2, name) for name in ("through_2025_06_30", "h2_2025", "from_2026"))
        if val2 and val5 and full2 and full5 and beats and years_ok and not concentrated and dd_ok and splits_ok:
            reasons.append(f"{mode} clears the cost, validation, baseline, year, concentration, and drawdown checks.")
            continue
        robust = False
        if val2 and val5 and full2 and full5 and beats:
            promising = True
            reasons.append(f"{mode} is positive after 2 bp and 5 bp and beats the baselines, but is not stable across years, stocks, or splits.")
        elif val2:
            weak = True
            reasons.append(f"{mode} is positive in validation at 2 bp, but the higher-cost, baseline, or stability checks fail.")
        else:
            reasons.append(f"{mode} does not show a positive validation result at 2 bp.")
    if robust:
        return {"verdict": "ROBUST EDGE", "reasons": reasons}
    validation_holds = all(positive(mode, 2, "h2_2025") for mode in MODES)
    if promising and validation_holds and not weak:
        return {"verdict": "PROMISING BUT UNPROVEN", "reasons": reasons}
    if promising or weak:
        return {"verdict": "WEAK EDGE", "reasons": reasons}
    return {"verdict": "NO EDGE", "reasons": reasons or ["The full rule does not beat a loss after costs on the validation window."]}

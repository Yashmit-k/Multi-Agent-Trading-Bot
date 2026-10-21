"""Strategy lab backtester: user-built rule strategies on stored NSE candles.

Definitions, indicators and rule evaluation live in core_paper.strategy_engine, so a strategy
backtested here is evaluated exactly the same way when applied to live paper trading.

Simulation rules:
- no look-ahead: rules are evaluated at a bar's close; entries use the live paper fill rule: a limit at
  the signal close + 0.25% (or the strategy's own lower level), filled at the open if the bar opens
  through it, else at the limit, during the 09:20-15:15 IST entry window;
- one position per symbol; exits are checked bar by bar: the stop first (on the fill bar too, as the
  path inside a bar is unknown), then targets (from the bar after the fill), then the trailing stop
  (from the best price of earlier bars), the time limit, the 15:15 square-off and the exit rule
  (which exits at the next bar's open);
- after the first target the stop can move to breakeven; if that same bar also trades back to entry,
  the rest exits at breakeven;
- Zerodha charges on every leg: delivery (CNC), or intraday (MIS) for square-off strategies; plus
  slippage on every exit (live paper fills have none: it is kept as a cushion);
- portfolio pass: trades are taken in entry order while a position slot and the cash are free.
Results are in-sample: a rule tuned on this data will look better here than it will trade.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import numpy as np
from pydantic import BaseModel, model_validator

from core_paper.strategy_engine import (  # noqa: F401 - re-exported for the API and watchlist
    CATALOG,
    INTRADAY,
    IST,
    Bars,
    Condition,
    Context,
    Group,
    Operand,
    StrategyDefinition,
    catalog,
    context_for,
    evaluate,
    operand_values,
    raw_indicator,
    resample,
    add_on_target,
    stop_price,
    target_prices,
)

SQUARE_OFF = time(15, 15)
ENTRY_START = time(9, 20)
ENTRY_END = time(15, 15)
LIVE_LIMIT_PREMIUM = 0.0025
MAX_INTRADAY_SYMBOLS = 10
MAX_INTRADAY_DAYS = 400
MAX_TRADES_LISTED = 1500
# Kept for older callers.
MAX_5M_SYMBOLS, MAX_5M_DAYS = MAX_INTRADAY_SYMBOLS, MAX_INTRADAY_DAYS


class BacktestRequest(BaseModel):
    start: date
    end: date

    @model_validator(mode="after")
    def _order(self) -> "BacktestRequest":
        if self.end < self.start:
            raise ValueError("end is before start")
        return self


# --- charges --------------------------------------------------------------------------------------


def leg_charges(buy_notional: float, sell_notional: float, product: str) -> float:
    """Zerodha equity charges for buying `buy_notional` and selling `sell_notional` (one round trip or part of one)."""
    from core_paper.charges import ZERODHA_EQUITY_RI as book
    from core_paper.charges import delivery_buy, delivery_sell

    if product == "CNC":
        total = 0.0
        if buy_notional > 0:
            total += float(delivery_buy(Decimal(str(round(buy_notional, 2))), book).total)
        if sell_notional > 0:
            total += float(delivery_sell(Decimal(str(round(sell_notional, 2))), book, include_dp=True).total)
        return total
    rate = float(book.intraday_brokerage_rate)
    cap = float(book.intraday_brokerage_cap)
    brokerage = (min(buy_notional * rate, cap) if buy_notional else 0.0) + (min(sell_notional * rate, cap) if sell_notional else 0.0)
    stt = sell_notional * float(book.intraday_stt_rate)
    exchange = (buy_notional + sell_notional) * float(book.transaction_rate)
    sebi = (buy_notional + sell_notional) * float(book.sebi_inr_per_crore) / 1e7
    stamp = buy_notional * float(book.intraday_stamp_rate)
    # The paper engine re-prices same-day CNC round trips at intraday rates and, by its documented conservative
    # choice (docs/paper-execution-policy.md), still charges one DP fee on the sell. Match it here.
    dp = float(book.dp_inr_per_scrip) if sell_notional > 0 else 0.0
    return brokerage + stt + exchange + sebi + stamp + float(book.gst_rate) * (brokerage + exchange + sebi) + dp


# --- simulation -----------------------------------------------------------------------------------


@dataclass
class Leg:
    quantity: int
    price: float
    reason: str
    at: datetime


@dataclass
class Trade:
    symbol: str
    direction: str
    entry_at: datetime
    exit_at: datetime
    entry_price: float
    quantity: int
    stop: float | None
    legs: list[Leg] = field(default_factory=list)
    charges: float = 0.0
    net_pnl: float = 0.0
    bars_held: int = 0
    adds: list[Leg] = field(default_factory=list)  # shares added after the entry (add-on)

    @property
    def total_quantity(self) -> int:
        return self.quantity + sum(leg.quantity for leg in self.adds)

    @property
    def cost(self) -> float:
        return self.entry_price * self.quantity + sum(leg.quantity * leg.price for leg in self.adds)

    def open_quantity(self, day: date) -> int:
        """Shares held at the close of `day` (IST): bought by then minus sold by then."""
        bought = (self.quantity if self.entry_at.astimezone(IST).date() <= day else 0) + sum(
            leg.quantity for leg in self.adds if leg.at.astimezone(IST).date() <= day
        )
        sold = sum(leg.quantity for leg in self.legs if leg.at.astimezone(IST).date() <= day)
        return bought - sold

    @property
    def exit_price(self) -> float:
        shares = sum(leg.quantity for leg in self.legs)
        return sum(leg.quantity * leg.price for leg in self.legs) / shares if shares else self.entry_price

    @property
    def reason(self) -> str:
        return self.legs[-1].reason if self.legs else "open"

    @property
    def average_cost(self) -> float:
        shares = self.total_quantity
        return self.cost / shares if shares else self.entry_price

    @property
    def risk_money(self) -> float | None:
        return None if self.stop is None else abs(self.entry_price - self.stop) * self.quantity


def _quantity(strategy: StrategyDefinition, entry: float, stop: float | None) -> int:
    if strategy.sizing.kind == "risk_percent":
        risk_per_share = abs(entry - stop) if stop is not None else 0.0
        if risk_per_share <= 0:
            return 0
        shares = int(strategy.initial_cash * strategy.sizing.value / 100 // risk_per_share)
        return min(shares, int(strategy.sizing.max_notional // entry))
    return int(strategy.sizing.value // entry)


def _last_entry(strategy: StrategyDefinition) -> time | None:
    if strategy.last_entry_time:
        hours, minutes = (int(part) for part in strategy.last_entry_time.split(":"))
        return time(hours, minutes)
    return time(15, 0) if strategy.square_off_intraday else None


def simulate_symbol(symbol: str, context: Context, strategy: StrategyDefinition, first_index: int) -> list[Trade]:
    bars = context.bars
    n = len(bars)
    entries = evaluate(context, strategy.entry)
    exits = evaluate(context, strategy.exit)
    add_when = evaluate(context, strategy.add_on.when) if strategy.add_on is not None else None
    long = strategy.direction == "long"
    sign = 1.0 if long else -1.0
    clocks = [moment.astimezone(IST) for moment in bars.end]
    starts = [moment.astimezone(IST) for moment in bars.start]
    days = bars.sessions()
    limit_series = operand_values(context, strategy.entry_order.price) if strategy.entry_order.type == "limit" else None
    latest_entry = _last_entry(strategy)
    intraday = strategy.timeframe in INTRADAY
    trades: list[Trade] = []
    i = max(first_index, 0)
    while i < n - 1:
        if not entries[i]:
            i += 1
            continue
        signal = i
        fill, raw = None, math.nan
        # Live paper fill rule (core_paper.execute.queue_entry): a limit at the signal close +/- 0.25%, or at the
        # strategy's own level when that is better; it fills at the open if the bar opens through it, else at the
        # limit; it works during the entry window (09:20-15:15 IST, same session for intraday bars that close before
        # 15:15, otherwise the next session) and, for limit-type entries, at most valid_bars bars.
        reference = float(bars.close[signal])
        standard = reference * (1 + sign * LIVE_LIMIT_PREMIUM)
        level = float(limit_series[signal]) if limit_series is not None else math.nan
        if strategy.entry_order.type == "limit":
            if math.isnan(level):
                i = signal + 1
                continue
            limit = min(standard, level) if long else max(standard, level)
            reference = level
        else:
            limit = standard
        if intraday:
            window_day = days[signal] if clocks[signal].time() < ENTRY_END else None
        else:
            window_day = None
        horizon_end = n if strategy.entry_order.type == "market" else min(n, signal + 1 + strategy.entry_order.valid_bars)
        for k in range(signal + 1, horizon_end):
            if intraday:
                if window_day is None:
                    window_day = days[k]  # signal after 15:15: the next session's window
                if days[k] != window_day or clocks[k].time() > ENTRY_END:
                    break
                if starts[k].time() < ENTRY_START or (latest_entry is not None and starts[k].time() >= latest_entry):
                    continue
            elif k > signal + 1:
                break  # daily bars: the next session only
            touched = bars.low[k] <= limit if long else bars.high[k] >= limit
            if touched:
                fill, raw = k, (min(float(bars.open[k]), limit) if long else max(float(bars.open[k]), limit))
                break
        if fill is None:
            i = signal + 1
            continue
        entry = raw  # no slippage on a limit fill, as live; exits keep the slippage setting
        # The order is sized before it fills, from the signal price. Once filled, the stop and the targets are
        # measured from the price actually paid, so a 10% stop is 10% of the money spent on the stock.
        planned_stop = stop_price(strategy, context, signal, reference)
        if planned_stop is not None and math.isnan(planned_stop):
            i = signal + 1
            continue
        quantity = _quantity(strategy, reference, planned_stop)
        if quantity < 1:
            i = signal + 1
            continue
        stop = stop_price(strategy, context, signal, entry)
        if stop is not None and (math.isnan(stop) or (stop >= entry if long else stop <= entry)):
            i = signal + 1  # stop undefined or on the wrong side of the fill: no trade
            continue
        targets = target_prices(strategy, context, signal, entry, stop)
        extra = add_on_target(strategy, context, signal, entry, stop)
        trade = _manage(symbol, bars, strategy, fill, entry, stop, targets, quantity, exits, clocks, days, add_when=add_when, add_target=extra)
        trades.append(trade)
        exit_index = next(k for k in range(fill, n) if bars.end[k] == trade.exit_at)
        i = exit_index + 1
    return trades


def _manage(symbol, bars: Bars, strategy: StrategyDefinition, fill: int, entry: float, stop: float | None, targets, quantity: int, exits, clocks, days, *, add_when=None, add_target: float | None = None) -> Trade:  # type: ignore[no-untyped-def]
    n = len(bars)
    long = strategy.direction == "long"
    sign = 1.0 if long else -1.0
    slip = strategy.slippage_bps / 10_000
    trade = Trade(symbol, strategy.direction, bars.end[fill], bars.end[fill], entry, quantity, stop)
    remaining = quantity
    current_stop = stop
    best = entry
    risk = abs(entry - stop) if stop is not None else None
    pending_targets = []
    allocated = 0
    for price, fraction in targets:
        shares = int(math.floor(quantity * fraction + 1e-9))
        shares = min(shares, quantity - allocated)
        if shares > 0:
            pending_targets.append([price, shares])
            allocated += shares
    hit_first = False
    added = 0  # shares from the add-on still held
    add_pending: float | None = None  # limit price of an add-on order waiting for the next bar
    add_done = False
    trail = strategy.trailing
    trail_atr = None
    if trail is not None and trail.kind == "atr":
        trail_atr = raw_indicator(bars, "atr", trail.period, None, None, strategy.timeframe in INTRADAY, {})

    def close(shares: int, raw_price: float, reason: str, k: int) -> None:
        nonlocal remaining
        if shares <= 0:
            return
        trade.legs.append(Leg(shares, raw_price * (1 - sign * slip), reason, bars.end[k]))
        remaining -= shares

    last = n - 1
    for j in range(fill, n):
        if strategy.square_off_intraday and (days[j] != days[fill] or clocks[j].time() > SQUARE_OFF):
            k = j - 1 if days[j] != days[fill] or clocks[j].time() > SQUARE_OFF else j
            close(remaining, float(bars.close[max(k, fill)]), "square_off", max(k, fill))
            last = max(k, fill)
            break
        low, high, open_ = float(bars.low[j]), float(bars.high[j]), float(bars.open[j])
        # 0. an add-on order from the previous bar fills here (live rule: limit at that close + 0.25%)
        if add_pending is not None:
            limit, add_pending = add_pending, None
            if (low <= limit) if long else (high >= limit):
                price = min(open_, limit) if long else max(open_, limit)
                shares = int(strategy.add_on.notional // price)  # type: ignore[union-attr]
                if shares >= 1:
                    trade.adds.append(Leg(shares, price, "add_on", bars.end[j]))
                    remaining += shares
                    added += shares
                    if strategy.add_on.restop_from_average and strategy.stop.kind == "percent" and not hit_first:  # type: ignore[union-attr]
                        current_stop = trade.average_cost * (1 - strategy.stop.value / 100)
        # 1. stop (including a trailing or breakeven stop)
        if current_stop is not None and (low <= current_stop if long else high >= current_stop):
            price = current_stop if j == fill else (min(open_, current_stop) if long else max(open_, current_stop))
            if current_stop == entry and hit_first:
                label = "breakeven"
            elif trail is not None and current_stop != stop and not (trade.adds and strategy.add_on and strategy.add_on.restop_from_average):
                label = "trailing_stop"
            else:
                label = "stop"  # the original stop, or one re-measured from the average cost after an add-on
            close(remaining, price, label, j)
            last = j
            break
        # 2. targets, from the bar after the fill. Initial targets sell the initial entry; added shares sell at
        #    their own target, or with the last initial target when they have none.
        if j > fill:
            for target in list(pending_targets):
                price, shares = target
                if (high >= price if long else low <= price):
                    last_initial = len(pending_targets) == 1
                    extra_shares = added if (last_initial and add_target is None) else 0
                    sell = min(shares + extra_shares, remaining)
                    close(sell, (max(open_, price) if long else min(open_, price)), "target", j)
                    if extra_shares:
                        added = 0
                    pending_targets.remove(target)
                    if not hit_first:
                        hit_first = True
                        if strategy.breakeven_after_first_target:
                            current_stop = entry if current_stop is None else (max(current_stop, entry) if long else min(current_stop, entry))
                            if remaining > 0 and (low <= entry if long else high >= entry):
                                close(remaining, entry, "breakeven", j)  # same bar came back: order unknown, assume breakeven
            if added and add_target is not None and (high >= add_target if long else low <= add_target) and trade.adds and trade.adds[-1].at < bars.end[j]:
                close(min(added, remaining), max(open_, add_target) if long else min(open_, add_target), "add_on_target", j)
                added = 0
            if remaining <= 0:
                last = j
                break
        # 2b. add-on signal on this close, before any target (once)
        if add_when is not None and not add_done and not hit_first and remaining > 0 and add_when[j] and j + 1 < n and j > fill:
            add_done = True
            add_pending = float(bars.close[j]) * (1 + sign * LIVE_LIMIT_PREMIUM)
        # 3. trailing stop update, from bars up to this one (applies from the next bar)
        if trail is not None:
            best = max(best, high) if long else min(best, low)
            moved_r = abs(best - entry) / risk if risk else math.inf
            if moved_r >= trail.activate_after_r:
                if trail.kind == "percent":
                    distance = best * trail.value / 100
                else:
                    atr = trail_atr[j] if trail_atr is not None else math.nan
                    distance = trail.value * atr if not math.isnan(atr) else math.nan
                if not math.isnan(distance):
                    level = best - distance if long else best + distance
                    if current_stop is None or (level > current_stop if long else level < current_stop):
                        current_stop = level
        # 4. time limit
        if strategy.max_hold_bars and j - fill + 1 >= strategy.max_hold_bars:
            close(remaining, float(bars.close[j]), "max_hold", j)
            last = j
            break
        # 5. exit rule: evaluated at this close, filled at the next open
        if exits[j] and j + 1 < n and not (strategy.square_off_intraday and days[j + 1] != days[fill]):
            close(remaining, float(bars.open[j + 1]), "exit_rule", j + 1)
            last = j + 1
            break
    else:
        last = n - 1
    if remaining > 0:
        close(remaining, float(bars.close[last]), "end_of_data", last)
    trade.exit_at = bars.end[last]
    trade.bars_held = last - fill + 1
    trade.charges = _trade_charges(trade, strategy)
    entry_notional = trade.cost
    exit_notional = sum(leg.quantity * leg.price for leg in trade.legs)
    trade.net_pnl = (exit_notional - entry_notional if long else entry_notional - exit_notional) - trade.charges
    return trade


def _trade_charges(trade: Trade, strategy: StrategyDefinition) -> float:
    """Charges per sell leg against the shares it closes (oldest first). A CNC leg sold in the session it was
    bought is priced as intraday, as the paper engine reclassifies a same-day delivery round trip."""
    lots = [[trade.quantity, trade.entry_price, trade.entry_at.astimezone(IST).date()]] + [
        [leg.quantity, leg.price, leg.at.astimezone(IST).date()] for leg in trade.adds
    ]
    total = 0.0
    for leg in trade.legs:
        left, sold_day = leg.quantity, leg.at.astimezone(IST).date()
        while left > 0 and lots:
            lot = lots[0]
            take = min(left, lot[0])
            bought, sold = take * lot[1], take * leg.price
            product = "MIS" if strategy.product == "MIS" or lot[2] == sold_day else "CNC"
            total += leg_charges(bought, sold, product) if trade.direction == "long" else leg_charges(sold, bought, product)
            lot[0] -= take
            left -= take
            if lot[0] == 0:
                lots.pop(0)
    return total


def portfolio(trades: list[Trade], strategy: StrategyDefinition) -> tuple[list[Trade], list[Trade]]:
    """Take trades in entry order while a slot and the cash (cost plus buy charges) are free."""
    taken: list[Trade] = []
    skipped: list[Trade] = []
    open_trades: list[Trade] = []
    cash = strategy.initial_cash
    for trade in sorted(trades, key=lambda item: (item.entry_at, item.symbol)):
        for item in [t for t in open_trades if t.exit_at <= trade.entry_at]:
            open_trades.remove(item)
            cash += item.cost + item.net_pnl
        cost = trade.entry_price * trade.quantity
        if len(open_trades) >= strategy.max_open_positions or cost > cash:
            skipped.append(trade)
            continue
        cash -= cost
        open_trades.append(trade)
        taken.append(trade)
    return taken, skipped


def equity_curve(taken: list[Trade], closes: dict[str, dict[date, float]], days: list[date], initial: float) -> list[dict[str, object]]:
    """End-of-day equity: starting cash + realized P&L + open positions marked at that day's close."""
    curve = []
    for day in days:
        realized = sum(t.net_pnl for t in taken if t.exit_at.astimezone(IST).date() <= day)
        unrealized = 0.0
        for t in taken:
            if t.entry_at.astimezone(IST).date() <= day < t.exit_at.astimezone(IST).date():
                mark = closes.get(t.symbol, {}).get(day)
                held = t.open_quantity(day)
                direction = 1 if t.direction == "long" else -1
                if mark is not None and held > 0:
                    unrealized += (mark - t.average_cost) * held * direction
                # shares already sold (e.g. at target 1) count as realised before the trade's final exit
                unrealized += sum((leg.price - t.average_cost) * leg.quantity * direction for leg in t.legs if leg.at.astimezone(IST).date() <= day)
        curve.append({"date": day.isoformat(), "equity": round(initial + realized + unrealized, 2)})
    return curve


def metrics(taken: list[Trade], curve: list[dict[str, object]], initial: float) -> dict[str, object]:
    nets = [t.net_pnl for t in taken]
    wins, losses = [v for v in nets if v > 0], [-v for v in nets if v < 0]
    equity = np.array([float(point["equity"]) for point in curve]) if curve else np.array([initial])
    returns = np.diff(equity) / equity[:-1] if len(equity) > 1 else np.array([])
    peak = np.maximum.accumulate(equity)
    years = max(len(equity) / 250, 1 / 250)
    final = float(equity[-1])
    reasons: dict[str, int] = {}
    for t in taken:
        for leg in t.legs:
            reasons[leg.reason] = reasons.get(leg.reason, 0) + 1
    r_values = [t.net_pnl / t.risk_money for t in taken if t.risk_money]
    return {
        "trades": len(taken),
        "win_rate": len(wins) / len(nets) if nets else None,
        "net_pnl": round(sum(nets), 2),
        "charges": round(sum(t.charges for t in taken), 2),
        "total_return": final / initial - 1,
        "cagr": (final / initial) ** (1 / years) - 1 if final > 0 else None,
        "sharpe": float(returns.mean() / returns.std(ddof=1) * math.sqrt(250)) if len(returns) > 2 and returns.std(ddof=1) > 0 else None,
        "max_drawdown": float(np.max(1 - equity / peak)) if len(equity) else 0.0,
        "profit_factor": (sum(wins) / sum(losses)) if losses else None,
        "average_win": float(np.mean(wins)) if wins else None,
        "average_loss": float(-np.mean(losses)) if losses else None,
        "expectancy_r": float(np.mean(r_values)) if r_values else None,
        "average_bars_held": float(np.mean([t.bars_held for t in taken])) if taken else None,
        "exit_reasons": reasons,
    }


def run_strategy(strategy: StrategyDefinition, request: BacktestRequest, load_bars, universe: list[str], benchmark: Bars | None = None) -> dict[str, object]:
    """load_bars(symbol, timeframe in {"5m", "1d"}, start, end) -> Bars | None; 15m and 1h are resampled from 5m."""
    symbols = universe if strategy.symbols == ["ALL"] else [s for s in strategy.symbols if s in set(universe)]
    if not symbols:
        raise ValueError("no known symbols selected")
    intraday = strategy.timeframe in INTRADAY
    if intraday:
        if len(symbols) > MAX_INTRADAY_SYMBOLS:
            raise ValueError(f"intraday backtests are limited to {MAX_INTRADAY_SYMBOLS} symbols on this server")
        if (request.end - request.start).days > MAX_INTRADAY_DAYS:
            raise ValueError(f"intraday backtests are limited to {MAX_INTRADAY_DAYS} days on this server")
    start = datetime.combine(request.start, time(0), IST).astimezone(timezone.utc)
    end = datetime.combine(request.end, time(23, 59), IST).astimezone(timezone.utc)
    warmup = timedelta(days=400) if not intraday else timedelta(days=30)
    all_trades: list[Trade] = []
    index_cache: dict[str, Bars | None] = {}
    closes: dict[str, dict[date, float]] = {}
    days: set[date] = set()
    for symbol in symbols:
        base = load_bars(symbol, "5m" if intraday else "1d", start - warmup, end)
        if base is None or len(base) < 2:
            continue
        bars = base if strategy.timeframe in ("5m", "1d") else resample(base, {"15m": 15, "1h": 60}[strategy.timeframe])
        if len(bars) < 2:
            continue

        def higher(timeframe: str, _base=base, _symbol=symbol):  # type: ignore[no-untyped-def]
            if timeframe == "1d":
                return load_bars(_symbol, "1d", start - timedelta(days=400), end)
            return resample(_base, {"15m": 15, "1h": 60}[timeframe])

        def index(_intraday=intraday):  # type: ignore[no-untyped-def]
            if "bars" not in index_cache:  # NIFTY 50 is loaded once per backtest
                loaded = load_bars("NIFTY50", "5m" if _intraday else "1d", start - warmup, end)
                if loaded is not None and strategy.timeframe not in ("5m", "1d"):
                    loaded = resample(loaded, {"15m": 15, "1h": 60}[strategy.timeframe])
                index_cache["bars"] = loaded
            return index_cache["bars"]

        context = context_for(strategy, bars, higher, index)
        first = next((k for k, moment in enumerate(bars.end) if moment >= start), len(bars))
        all_trades += simulate_symbol(symbol, context, strategy, first)
        daily: dict[date, float] = {}
        for moment, close in zip(bars.end, bars.close):
            if moment >= start:
                day = moment.astimezone(IST).date()
                daily[day] = float(close)
                days.add(day)
        closes[symbol] = daily
    taken, skipped = portfolio(all_trades, strategy)
    ordered_days = sorted(days)
    curve = equity_curve(taken, closes, ordered_days, strategy.initial_cash)
    result = metrics(taken, curve, strategy.initial_cash)
    halves = {}
    if ordered_days:
        half = ordered_days[len(ordered_days) // 2]
        first_half = [t for t in taken if t.entry_at.astimezone(IST).date() < half]
        second_half = [t for t in taken if t.entry_at.astimezone(IST).date() >= half]
        halves = {
            "split_date": half.isoformat(),
            "first_half": {"trades": len(first_half), "net_pnl": round(sum(t.net_pnl for t in first_half), 2)},
            "second_half": {"trades": len(second_half), "net_pnl": round(sum(t.net_pnl for t in second_half), 2)},
        }
    bench = None
    if benchmark is not None and len(benchmark):
        points = [(m.astimezone(IST).date(), float(c)) for m, c in zip(benchmark.end, benchmark.close) if start <= m <= end]
        if len(points) > 1:
            base_close = points[0][1]
            bench = {
                "symbol": "NIFTY50",
                "from": points[0][0].isoformat(),
                "to": points[-1][0].isoformat(),
                "total_return": points[-1][1] / base_close - 1,
                "curve": [{"date": d.isoformat(), "equity": round(strategy.initial_cash * c / base_close, 2)} for d, c in points],
            }
    notes = [
        "In-sample: this is the data the rule was written against. Expect live results to be worse.",
        "Rules use each bar's close; entries fill on later bars, and higher-timeframe values come from completed bars only.",
        f"Charges: Zerodha {'intraday rates (same-day square-off), plus one DP fee per sell as the paper engine charges' if strategy.product == 'MIS' else 'delivery (CNC); a leg sold in the session it was bought is priced as intraday, as the paper engine does'} on every leg, plus {strategy.slippage_bps:g} bp slippage on each exit.",
        "Entries use the paper engine's rule: a limit at the signal close + 0.25%, next session only for daily bars, so a stock that gaps up past it is not bought.",
        "Stops and targets are measured from the price actually paid (fixed levels such as a swing low stay where they are); the quantity is sized from the signal price, before the fill.",
    ]
    if strategy.direction == "short":
        notes.append("Short side is a research backtest: the paper engine trades long only.")
    return {
        "kind": "strategy_lab",
        "strategy": strategy.model_dump(mode="json"),
        "rules": {"entry": strategy.entry.label(), "exit": strategy.exit.label() if strategy.exit else None},
        "start": request.start.isoformat(),
        "end": request.end.isoformat(),
        "symbols_tested": len(closes),
        "signals_considered": len(all_trades),
        "trades_skipped_by_portfolio": len(skipped),
        "metrics": result,
        "halves": halves,
        "benchmark": bench,
        "equity_curve": curve,
        "trades": [
            {
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_at": t.entry_at.isoformat(),
                "exit_at": t.exit_at.isoformat(),
                "entry_price": round(t.entry_price, 2),
                "exit_price": round(t.exit_price, 2),
                "quantity": t.quantity,
                "reason": t.reason,
                "legs": [{"quantity": leg.quantity, "price": round(leg.price, 2), "reason": leg.reason, "at": leg.at.isoformat()} for leg in t.legs],
                "charges": round(t.charges, 2),
                "net_pnl": round(t.net_pnl, 2),
                "bars_held": t.bars_held,
            }
            for t in sorted(taken, key=lambda item: item.entry_at)[-MAX_TRADES_LISTED:]
        ],
        "trades_listed_limit": MAX_TRADES_LISTED,
        "live_enabled": False,
        "notes": notes,
    }


def _c(left: dict, op: str, right: dict, **extra) -> dict:  # type: ignore[no-untyped-def]
    return {"left": left, "op": op, "right": right, **extra}


def _all(*items: dict) -> dict:
    return {"logic": "all", "items": list(items)}


def _any(*items: dict) -> dict:
    return {"logic": "any", "items": list(items)}


TEMPLATES: list[dict[str, object]] = [
    {
        "name": "EMA 20/50 crossover",
        "description": "Buy when the 20-day EMA crosses above the 50-day EMA; sell when it crosses back below.",
        "timeframe": "1d",
        "entry": _all(_c({"indicator": "ema", "period": 20}, "crosses_above", {"indicator": "ema", "period": 50})),
        "exit": _any(_c({"indicator": "ema", "period": 20}, "crosses_below", {"indicator": "ema", "period": 50})),
        "stop": {"kind": "percent", "value": 5},
        "targets": [{"kind": "percent", "value": 15, "fraction": 1}],
    },
    {
        "name": "RSI oversold bounce in an uptrend",
        "description": "Buy when RSI(14) crosses back above 30 while the stock is above its 200-day SMA; exit when RSI passes 60.",
        "timeframe": "1d",
        "entry": _all(
            _c({"indicator": "rsi", "period": 14}, "crosses_above", {"value": 30}),
            _c({"indicator": "close"}, ">", {"indicator": "sma", "period": 200}),
        ),
        "exit": _any(_c({"indicator": "rsi", "period": 14}, ">", {"value": 60})),
        "stop": {"kind": "atr", "value": 2, "period": 14},
        "targets": [{"kind": "r_multiple", "value": 2, "fraction": 1}],
        "max_hold_bars": 15,
    },
    {
        "name": "20-day breakout on volume, ATR trailing stop",
        "description": "Buy a close above the previous 20-day high on 1.5x average volume; trail the stop 3 ATR below the best price.",
        "timeframe": "1d",
        "entry": _all(
            _c({"indicator": "close"}, ">", {"indicator": "highest", "period": 20}),
            _c({"indicator": "volume_ratio", "period": 20}, ">", {"value": 1.5}),
        ),
        "stop": {"kind": "atr", "value": 2, "period": 14},
        "targets": [],
        "trailing": {"kind": "atr", "value": 3, "period": 14},
    },
    {
        "name": "SuperTrend + ADX trend",
        "description": "Buy when SuperTrend(10, 3) turns up while ADX(14) is above 20; exit when it turns down.",
        "timeframe": "1d",
        "entry": _all(
            _c({"indicator": "supertrend_dir", "period": 10, "param": 3}, "crosses_above", {"value": 0}),
            _c({"indicator": "adx", "period": 14}, ">", {"value": 20}),
        ),
        "exit": _any(_c({"indicator": "supertrend_dir", "period": 10, "param": 3}, "crosses_below", {"value": 0})),
        "stop": {"kind": "level", "level": {"indicator": "supertrend", "period": 10, "param": 3}},
        "targets": [],
    },
    {
        "name": "15-minute opening-range breakout",
        "description": "Buy a 5-minute close above the first 15 minutes' high, above VWAP, before 11:00. Half off at 1R, stop to breakeven, rest at 2R; out by 15:15.",
        "timeframe": "5m",
        "symbols": ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"],
        "entry": _all(
            _c({"indicator": "close"}, "crosses_above", {"indicator": "opening_range_high", "period": 15}),
            _c({"indicator": "close"}, ">", {"indicator": "vwap"}),
            _c({"indicator": "time_hhmm"}, "<=", {"value": 1100}),
        ),
        "stop": {"kind": "level", "level": {"indicator": "opening_range_low", "period": 15}},
        "targets": [{"kind": "r_multiple", "value": 1, "fraction": 0.5}, {"kind": "r_multiple", "value": 2, "fraction": 0.5}],
        "breakeven_after_first_target": True,
        "square_off_intraday": True,
    },
    {
        "name": "Break of structure, retest entry, two targets",
        "description": "15-minute break of structure while the daily trend is up (daily close above its 50-day EMA). Buy the retest of the broken swing high; stop below the swing low; half at 1R, rest at 1.5R.",
        "timeframe": "15m",
        "symbols": ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"],
        "entry": _all(
            _c({"indicator": "bos_up", "period": 2}, "==", {"value": 1}),
            _c({"indicator": "close", "timeframe": "1d"}, ">", {"indicator": "ema", "period": 50, "timeframe": "1d"}),
        ),
        "entry_order": {"type": "limit", "price": {"indicator": "swing_high", "period": 2, "offset": 1}, "valid_bars": 8},
        "stop": {"kind": "level", "level": {"indicator": "swing_low", "period": 2}},
        "targets": [{"kind": "r_multiple", "value": 1, "fraction": 0.5}, {"kind": "r_multiple", "value": 1.5, "fraction": 0.5}],
        "breakeven_after_first_target": True,
        "square_off_intraday": True,
    },
    {
        "name": "Stochastic pullback in an uptrend",
        "description": "Buy when Stochastic %K crosses above %D below 20 while the close is above the 50-day EMA; exit when %K passes 80.",
        "timeframe": "1d",
        "entry": _all(
            _c({"indicator": "stoch_k", "period": 14, "period2": 3}, "crosses_above", {"indicator": "stoch_d", "period": 14, "period2": 3}),
            _c({"indicator": "stoch_k", "period": 14, "period2": 3}, "<", {"value": 20}),
            _c({"indicator": "close"}, ">", {"indicator": "ema", "period": 50}),
        ),
        "exit": _any(_c({"indicator": "stoch_k", "period": 14, "period2": 3}, ">", {"value": 80})),
        "stop": {"kind": "percent", "value": 4},
        "targets": [{"kind": "percent", "value": 8, "fraction": 1}],
    },
    {
        "name": "Bollinger squeeze breakout",
        "description": "Buy when the close breaks above the upper Bollinger band after the bands were narrow (width under 6% for 5 bars), with MACD above signal.",
        "timeframe": "1d",
        "entry": _all(
            _c({"indicator": "close"}, "crosses_above", {"indicator": "bb_upper", "period": 20, "param": 2}),
            _c({"indicator": "bb_width_pct", "period": 20, "param": 2, "offset": 1}, "<", {"value": 6}, for_bars=5),
            _c({"indicator": "macd"}, ">", {"indicator": "macd_signal"}),
        ),
        "stop": {"kind": "level", "level": {"indicator": "bb_mid", "period": 20, "param": 2}, "buffer_pct": 0.5},
        "targets": [{"kind": "r_multiple", "value": 1, "fraction": 0.5}, {"kind": "r_multiple", "value": 2.5, "fraction": 0.5}],
        "breakeven_after_first_target": True,
    },
    {
        "name": "Intraday VWAP fade (short, research)",
        "description": "Short when a 5-minute close falls back below VWAP after a gap up of more than 1%; out by 15:15. Research only: the paper engine trades long.",
        "timeframe": "5m",
        "direction": "short",
        "symbols": ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"],
        "entry": _all(
            _c({"indicator": "gap_pct"}, ">", {"value": 1}),
            _c({"indicator": "close"}, "crosses_below", {"indicator": "vwap"}),
        ),
        "stop": {"kind": "level", "level": {"indicator": "day_high"}, "buffer_pct": 0.1},
        "targets": [{"kind": "r_multiple", "value": 1, "fraction": 0.5}, {"kind": "r_multiple", "value": 2, "fraction": 0.5}],
        "breakeven_after_first_target": True,
        "square_off_intraday": True,
    },
]


def operand_catalog() -> list[dict[str, object]]:
    return catalog()

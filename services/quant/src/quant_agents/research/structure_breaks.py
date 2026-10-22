"""Market-structure-break study with two modest targets, scored per services/quant/docs/structure-breaks-protocol.md.

5-minute bullish breaks of structure, taken only when the 1-hour trend is up, entered on a retest
of the broken swing high. Half the position exits at TP1, after which the stop moves to breakeven.
The rest exits at TP2, the stop, or 15:15 IST. Three target pairs are scored. Long only, MIS charges.

    python -m quant_agents.research.structure_breaks
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research import order_blocks as ob

IST = ob.IST
PIVOT = ob.PIVOT
EMA_BARS = 50
ORDER_LIFE = 12
MIN_RISK = 0.0025
SLIP = ob.SLIP
NOTIONAL = ob.NOTIONAL
SQUARE_OFF = time(15, 15)
LAST_ENTRY = time(15, 0)
TARGETS: dict[str, tuple[float, float]] = {"T_0.5R_1R": (0.5, 1.0), "T_1R_1.5R": (1.0, 1.5), "T_1R_2R": (1.0, 2.0)}
COMPARISONS = len(TARGETS)


@dataclass(frozen=True)
class Break:
    bos: int  # bar whose close broke the swing high (known at its close)
    level: float  # the broken swing high: the retest limit
    swing_low: float  # lowest low between the swing high and the break: the stop


def bullish_breaks(bars: ob.Bars) -> list[Break]:
    """Closes above the most recent confirmed, unbroken pivot high (confirmed PIVOT bars after it)."""
    breaks: list[Break] = []
    last_pivot: int | None = None
    broken = True
    for b in range(2 * PIVOT, len(bars)):
        candidate = b - PIVOT
        window = bars.high[candidate - PIVOT : candidate + PIVOT + 1]
        if bars.high[candidate] == window.max() and (window == bars.high[candidate]).sum() == 1:
            last_pivot, broken = candidate, False
        if last_pivot is None or broken or b <= last_pivot + PIVOT or bars.close[b] <= bars.high[last_pivot]:
            continue
        broken = True
        breaks.append(Break(b, float(bars.high[last_pivot]), float(bars.low[last_pivot : b + 1].min())))
    return breaks


def ema(values: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if len(values) < period:
        return out
    alpha = 2 / (period + 1)
    out[period - 1] = values[:period].mean()
    for i in range(period, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def trend_up_at(hourly: ob.Bars) -> tuple[np.ndarray, np.ndarray]:
    """(hour-bar end timestamps, trend-up flag) using only completed hourly bars."""
    line = ema(hourly.close, EMA_BARS)
    flags = np.where(np.isnan(line), False, hourly.close > line)
    return np.array([moment.timestamp() for moment in hourly.end]), flags


@dataclass
class Trade:
    symbol: str
    entry_at: datetime
    exit_at: datetime
    exit_session: date
    entry: float
    stop: float
    quantity: int
    reached_tp1: bool
    reason: str
    net: float
    risk_money: float


def manage(symbol: str, bars: ob.Bars, i: int, entry: float, stop: float, targets: tuple[float, float], quantity: int) -> Trade:
    """Half at TP1, then stop to breakeven; rest at TP2, stop, or the 15:15 bar close. Stop wins ties."""
    risk = entry - stop
    tp1, tp2 = entry + targets[0] * risk, entry + targets[1] * risk
    first_half = quantity // 2
    rest = quantity - first_half
    day = bars.end[i].astimezone(IST).date()
    last = max(k for k in range(i, len(bars)) if bars.end[k].astimezone(IST).date() == day and bars.end[k].astimezone(IST).time() <= SQUARE_OFF) if bars.end[i].astimezone(IST).time() <= SQUARE_OFF else i
    legs: list[tuple[int, float]] = []  # (shares, raw exit price)
    current_stop = stop
    open_shares = quantity
    hit_tp1 = False
    reason = "time"
    exit_index = last
    for j in range(i, last + 1):
        low, high, open_ = float(bars.low[j]), float(bars.high[j]), float(bars.open[j])
        if low <= current_stop:  # on the fill bar the path is unknown: assume the stop first
            price = current_stop if j == i else min(open_, current_stop)
            legs.append((open_shares, price))
            open_shares, reason, exit_index = 0, ("breakeven" if hit_tp1 else "stop"), j
            break
        if j == i:
            continue  # no target on the fill bar
        if not hit_tp1 and high >= tp1 and first_half > 0:
            legs.append((first_half, max(open_, tp1)))
            open_shares -= first_half
            hit_tp1, current_stop = True, entry  # breakeven on the rest
            if low <= entry:  # the same bar also came back to entry: order unknown, assume breakeven hit
                legs.append((open_shares, entry))
                open_shares, reason, exit_index = 0, "breakeven", j
                break
        if hit_tp1 and high >= tp2:
            legs.append((open_shares, max(open_, tp2)))
            open_shares, reason, exit_index = 0, "tp2", j
            break
    if open_shares:
        legs.append((open_shares, float(bars.close[last])))
        exit_index = last
    # Zerodha intraday charges are linear at Rs 20,000 (the Rs 20 brokerage cap is never reached), so each leg
    # can be charged on its own shares: the sum equals one buy order plus the separate sell orders.
    net = sum(ob.mis_net(entry, raw * (1 - SLIP), shares) for shares, raw in legs if shares)
    return Trade(symbol, bars.end[i], bars.end[exit_index], bars.end[exit_index].astimezone(IST).date(), entry, stop, quantity, hit_tp1, reason, net, risk * quantity)


def candidate_trades(symbol: str, five: ob.Bars, hourly: ob.Bars, targets: tuple[float, float], *, use_filter: bool, first_day: date) -> list[Trade]:
    hour_ends, trend = trend_up_at(hourly)
    out: list[Trade] = []
    for brk in bullish_breaks(five):
        moment = five.end[brk.bos]
        local = moment.astimezone(IST)
        if local.date() < first_day:
            continue
        if use_filter:
            k = int(np.searchsorted(hour_ends, moment.timestamp(), side="right")) - 1
            if k < 0 or not trend[k]:
                continue
        for i in range(brk.bos + 1, min(len(five), brk.bos + 1 + ORDER_LIFE)):
            start = five.start[i].astimezone(IST)
            if start.date() != local.date() or start.time() >= LAST_ENTRY:
                break
            if five.low[i] <= brk.level:
                entry = min(float(five.open[i]), brk.level) * (1 + SLIP)
                risk = entry - brk.swing_low
                quantity = int(NOTIONAL // entry)
                if risk >= MIN_RISK * entry and quantity >= 2:
                    out.append(manage(symbol, five, i, entry, brk.swing_low, targets, quantity))
                break
    return out


def one_at_a_time(trades: list[Trade]) -> list[Trade]:
    taken: list[Trade] = []
    for trade in sorted(trades, key=lambda item: item.entry_at):
        if taken and trade.entry_at <= taken[-1].exit_at:
            continue
        taken.append(trade)
    return taken


def describe(trades: list[Trade], sessions: list[date]) -> dict[str, object]:
    index = {day: k for k, day in enumerate(sessions)}
    pnl = np.zeros(len(sessions))
    for t in trades:
        if t.exit_session in index:
            pnl[index[t.exit_session]] += t.net
    nets = [t.net for t in trades]
    wins, losses = [v for v in nets if v > 0], [-v for v in nets if v < 0]
    curve = np.concatenate([[0.0], np.cumsum(pnl)])
    half = len(sessions) // 2
    reasons: dict[str, int] = {}
    for t in trades:
        reasons[t.reason] = reasons.get(t.reason, 0) + 1
    bound = ob.lower_bound(pnl, quantile=0.10 / COMPARISONS) if trades else float("nan")
    first, second = float(pnl[:half].sum()), float(pnl[half:].sum())
    out = {
        "trades": len(trades),
        "tp1_rate": float(np.mean([t.reached_tp1 for t in trades])) if trades else None,
        "win_rate": len(wins) / len(nets) if nets else None,
        "mean_net_r": float(np.mean([t.net / t.risk_money for t in trades])) if trades else None,
        "mean_net_return_pct": float(np.mean([t.net / (t.entry * t.quantity) for t in trades]) * 100) if trades else None,
        "total_net_pnl": float(sum(nets)),
        "profit_factor": (sum(wins) / sum(losses)) if losses else None,
        "max_drawdown_rupees": float(np.max(np.maximum.accumulate(curve) - curve)),
        "exit_reasons": reasons,
        "session_pnl_lower_bound": bound,
        "first_half": first,
        "second_half": second,
    }
    out["profitable"] = bool(len(trades) >= 100 and out["total_net_pnl"] > 0 and bound > 0 and first > 0 and second > 0)
    return out


def run() -> dict[str, object]:
    er.split_snapshots()
    symbols = er.stock_symbols()
    all_days = sorted({er._ist(r["end"]).date() for r in er._bars(symbols[0], "1d") if er.regular(er._ist(r["end"]).date())})
    first_day = all_days[ob.WARMUP_SESSIONS]
    sessions = [day for day in all_days if day >= first_day]
    collected: dict[tuple[str, bool], list[Trade]] = {(name, flt): [] for name in TARGETS for flt in (True, False)}
    for symbol in symbols:
        five = ob.five_minute(symbol)
        hourly = ob.resample(five, 60)
        for name, targets in TARGETS.items():
            for use_filter in (True, False):
                collected[(name, use_filter)] += one_at_a_time(candidate_trades(symbol, five, hourly, targets, use_filter=use_filter, first_day=first_day))
        print(f"{symbol}: " + ", ".join(f"{name}={len(collected[(name, True)])}" for name in TARGETS), flush=True)
    return {
        "protocol": "services/quant/docs/structure-breaks-protocol.md",
        "period": {"first": first_day.isoformat(), "last": sessions[-1].isoformat(), "sessions": len(sessions)},
        "variants": {name: {"with_1h_trend_filter": describe(collected[(name, True)], sessions), "no_filter_diagnostic": describe(collected[(name, False)], sessions)} for name in TARGETS},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=er.ROOT / "services/quant/docs/results/structure-breaks-result.json")
    args = parser.parse_args()
    report = run()
    args.out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()

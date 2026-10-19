"""Multi-timeframe order-block study, scored per services/quant/docs/order-blocks-protocol.md.

A higher-timeframe (HTF) bullish order block marks a zone. When price returns into the zone, the
lower timeframe (LTF) must break structure upward; the entry is a limit at the top of the LTF order
block behind that break, stop below it, target 2R. Long only.

Book A: daily zone, 15-minute entry, CNC (holds up to 10 sessions).
Book B: 1-hour zone, 5-minute entry, MIS (squared off at 15:15 IST).

Run with the root virtualenv (the 5m/1D snapshot pickles come from exit_rules.split_snapshots):
    python -m quant_agents.research.order_blocks
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research import ml_ensemble as me

IST = ZoneInfo("Asia/Kolkata")
PIVOT = 2
ATR_BARS = 14
IMPULSE_ATR = 1.5
ZONE_LIFE = 20
ORDER_LIFE = 12
REWARD_R = 2.0
MIN_RISK = 0.001
SLIP = me.SLIPPAGE
NOTIONAL = me.NOTIONAL
MAX_HOLD_SESSIONS = 10
SQUARE_OFF = time(15, 15)
LAST_ENTRY_B = time(15, 0)
SESSION_OPEN = time(9, 15)
WARMUP_SESSIONS = 60
COMPARISONS = 2


# --- bars -----------------------------------------------------------------------------------------


@dataclass
class Bars:
    start: list[datetime]
    end: list[datetime]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray

    def __len__(self) -> int:
        return len(self.end)


def _from_rows(rows: list[dict]) -> Bars:
    return Bars(
        [datetime.fromisoformat(r["start"]) for r in rows],
        [datetime.fromisoformat(r["end"]) for r in rows],
        np.array([float(r["open"]) for r in rows]),
        np.array([float(r["high"]) for r in rows]),
        np.array([float(r["low"]) for r in rows]),
        np.array([float(r["close"]) for r in rows]),
    )


def five_minute(symbol: str) -> Bars:
    rows = [r for r in er._bars(symbol, "5m") if er.regular(er._ist(r["end"]).date())]
    return _from_rows(rows)


def daily(symbol: str) -> Bars:
    rows = [r for r in er._bars(symbol, "1d") if er.regular(er._ist(r["end"]).date())]
    return _from_rows(rows)


def resample(bars: Bars, minutes: int) -> Bars:
    """Session-anchored bars from 09:15 IST; a bar exists only if every 5-minute bar inside it exists."""
    groups: dict[tuple[date, int], list[int]] = defaultdict(list)
    for i, moment in enumerate(bars.start):
        local = moment.astimezone(IST)
        offset = (local.hour * 60 + local.minute) - (9 * 60 + 15)
        if offset < 0:
            continue
        groups[(local.date(), offset // minutes)].append(i)
    keys = sorted(groups)
    starts, ends, o, h, l, c = [], [], [], [], [], []
    for day, slot in keys:
        idx = groups[(day, slot)]
        slot_start = datetime.combine(day, SESSION_OPEN, IST) + timedelta(minutes=slot * minutes)
        slot_end = min(slot_start + timedelta(minutes=minutes), datetime.combine(day, time(15, 30), IST))
        expected = int((slot_end - slot_start).total_seconds() // 300)
        if len(idx) != expected:
            continue
        starts.append(slot_start.astimezone(timezone.utc))
        ends.append(slot_end.astimezone(timezone.utc))
        o.append(bars.open[idx[0]])
        h.append(bars.high[idx].max())
        l.append(bars.low[idx].min())
        c.append(bars.close[idx[-1]])
    return Bars(starts, ends, np.array(o), np.array(h), np.array(l), np.array(c))


# --- structure ------------------------------------------------------------------------------------


def atr(bars: Bars) -> np.ndarray:
    """Simple mean true range of the previous ATR_BARS bars (known at each bar's close)."""
    previous = np.concatenate([[bars.close[0]], bars.close[:-1]])
    tr = np.maximum(bars.high - bars.low, np.maximum(abs(bars.high - previous), abs(bars.low - previous)))
    out = np.full(len(bars), np.nan)
    sums = np.cumsum(np.insert(tr, 0, 0.0))
    for i in range(ATR_BARS, len(bars) + 1):
        out[i - 1] = (sums[i] - sums[i - ATR_BARS]) / ATR_BARS
    return out


@dataclass(frozen=True)
class Block:
    bos: int  # index of the bar whose close broke structure (the zone is known at its close)
    ob: int  # index of the order-block candle
    low: float
    high: float


def bullish_blocks(bars: Bars) -> list[Block]:
    """Order blocks behind each upward break of structure, using only confirmed pivots.

    A pivot high at i is confirmed at the close of i + PIVOT. A break is a close above the most recent
    confirmed, unbroken pivot high. The block is the last bearish candle between the lowest low since
    that pivot and the break, and the move must reach IMPULSE_ATR x ATR.
    """
    n = len(bars)
    vol = atr(bars)
    blocks: list[Block] = []
    last_pivot: int | None = None
    broken = True
    for b in range(2 * PIVOT, n):
        candidate = b - PIVOT  # becomes a confirmed pivot high at the close of b
        window = bars.high[candidate - PIVOT : candidate + PIVOT + 1]
        if bars.high[candidate] == window.max() and (window == bars.high[candidate]).sum() == 1:
            last_pivot, broken = candidate, False
        if last_pivot is None or broken or b <= last_pivot + PIVOT:
            continue
        if bars.close[b] <= bars.high[last_pivot]:
            continue
        broken = True
        span = range(last_pivot, b)
        lowest = min(span, key=lambda k: bars.low[k])
        bearish = [k for k in range(lowest, b) if bars.close[k] < bars.open[k]]
        if not bearish or math.isnan(vol[b]):
            continue
        ob = bearish[-1]
        if bars.close[b] - bars.low[ob] < IMPULSE_ATR * vol[b]:
            continue
        blocks.append(Block(b, ob, float(bars.low[ob]), float(bars.high[ob])))
    return blocks


# --- costs ----------------------------------------------------------------------------------------


def cnc_net(entry: float, exit_: float, quantity: int) -> float:
    bought, sold = entry * quantity, exit_ * quantity
    return sold - bought - me._charges(me._money(bought), buy=True) - me._charges(me._money(sold), buy=False)


def mis_net(entry: float, exit_: float, quantity: int) -> float:
    """Zerodha intraday equity charges (rates from core_paper.charges.ZERODHA_EQUITY_RI)."""
    bought, sold = entry * quantity, exit_ * quantity
    brokerage = min(bought * 0.0003, 20.0) + min(sold * 0.0003, 20.0)
    stt = sold * 0.00025
    exchange = (bought + sold) * 0.0000307
    sebi = (bought + sold) * 10 / 1e7
    stamp = bought * 0.00003
    gst = 0.18 * (brokerage + exchange + sebi)
    return sold - bought - (brokerage + stt + exchange + sebi + stamp + gst)


# --- simulation -----------------------------------------------------------------------------------


@dataclass
class Trade:
    symbol: str
    entry_at: datetime
    exit_at: datetime
    exit_session: date
    entry: float
    exit: float
    stop: float
    quantity: int
    reason: str
    net: float
    risk_money: float


@dataclass
class Book:
    name: str
    htf_minutes: int | None  # None = daily
    ltf_minutes: int
    intraday: bool
    trades: dict[str, list[Trade]] = field(default_factory=lambda: defaultdict(list))


def _session_index(bars: Bars) -> tuple[list[date], dict[date, list[int]]]:
    by_day: dict[date, list[int]] = defaultdict(list)
    for i, moment in enumerate(bars.end):
        by_day[moment.astimezone(IST).date()].append(i)
    return sorted(by_day), by_day


def candidate_trades(symbol: str, htf: Bars, ltf: Bars, book: Book, *, refine: bool, first_day: date) -> list[Trade]:
    """At most one candidate trade per HTF zone, each simulated on its own. refine=False is the HTF-only baseline."""
    zones = [z for z in bullish_blocks(htf) if htf.end[z.bos].astimezone(IST).date() >= first_day]
    ltf_by_bos = {blk.bos: blk for blk in bullish_blocks(ltf)} if refine else {}
    days, by_day = _session_index(ltf)
    day_pos = {day: k for k, day in enumerate(days)}
    stamps = np.array([moment.timestamp() for moment in ltf.end])
    out: list[Trade] = []
    for zone in zones:
        known_at = htf.end[zone.bos]
        # The zone lives ZONE_LIFE HTF bars, or until an HTF close below its low.
        last_htf = min(len(htf) - 1, zone.bos + ZONE_LIFE)
        dead_at = htf.end[last_htf]
        for k in range(zone.bos + 1, last_htf + 1):
            if htf.close[k] < zone.low:
                dead_at = htf.end[k]
                break
        first = int(np.searchsorted(stamps, known_at.timestamp(), side="right"))
        # Baseline: a limit rests at the zone top from the moment the zone is known, for the zone's life.
        order = {"limit": zone.high, "stop": zone.low, "placed": first - 1, "expires": len(ltf), "same_day": False} if not refine else None
        touched = False
        for i in range(first, len(ltf)):
            if ltf.end[i] > dead_at and (order is None or not order["same_day"]):
                break
            if refine and order is None:
                if not touched and ltf.low[i] <= zone.high:
                    touched = True
                blk = ltf_by_bos.get(i)
                if touched and blk is not None and blk.low <= zone.high and blk.high >= zone.low and ltf.end[blk.ob] > known_at:
                    order = {"limit": blk.high, "stop": blk.low, "placed": i, "expires": i + ORDER_LIFE, "same_day": book.intraday}
                continue
            if order is None or i <= order["placed"]:
                continue
            if i > order["expires"]:
                break
            if order["same_day"] and ltf.end[i].astimezone(IST).date() != ltf.end[order["placed"]].astimezone(IST).date():
                break
            if book.intraday and ltf.start[i].astimezone(IST).time() >= LAST_ENTRY_B:
                continue
            if ltf.low[i] <= order["limit"]:
                entry = min(float(ltf.open[i]), order["limit"]) * (1 + SLIP)
                risk = entry - order["stop"]
                quantity = int(NOTIONAL // entry)
                if risk > 0 and risk >= MIN_RISK * entry and quantity >= 1:
                    out.append(_manage(symbol, ltf, i, entry, order["stop"], entry + REWARD_R * risk, quantity, book, days, day_pos, by_day))
                break
    return out


def one_at_a_time(trades: list[Trade]) -> list[Trade]:
    """Take candidates in entry order; skip any that starts before the previous position closed."""
    taken: list[Trade] = []
    for trade in sorted(trades, key=lambda item: item.entry_at):
        if taken and trade.entry_at <= taken[-1].exit_at:
            continue
        taken.append(trade)
    return taken


def _manage(symbol, ltf: Bars, i: int, entry: float, stop: float, target: float, quantity: int, book: Book, days, day_pos, by_day) -> Trade:
    entry_day = ltf.end[i].astimezone(IST).date()
    if book.intraday:
        last = max(k for k in by_day[entry_day] if ltf.end[k].astimezone(IST).time() <= SQUARE_OFF)
    else:
        position = min(day_pos[entry_day] + MAX_HOLD_SESSIONS, len(days) - 1)
        last = by_day[days[position]][-1]
    j = i
    reason, raw = "time", float(ltf.close[last]) if last >= i else float(ltf.close[i])
    exit_index = max(last, i)
    while j <= exit_index:
        if ltf.low[j] <= stop:  # on the fill bar too: the bar's path is unknown, so assume the stop came first
            raw, reason, exit_index = (min(float(ltf.open[j]), stop) if j > i else stop), "stop", j
            break
        if j > i and ltf.high[j] >= target:
            raw, reason, exit_index = max(float(ltf.open[j]), target), "target", j
            break
        j += 1
    exit_price = raw * (1 - SLIP)
    net = (mis_net if book.intraday else cnc_net)(entry, exit_price, quantity)
    return Trade(symbol, ltf.end[i], ltf.end[exit_index], ltf.end[exit_index].astimezone(IST).date(), entry, exit_price, stop, quantity, reason, net, (entry - stop) * quantity)


# --- scoring --------------------------------------------------------------------------------------


def lower_bound(series: np.ndarray, *, quantile: float, resamples: int = 2000, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    means = np.empty(resamples)
    for k in range(resamples):
        means[k] = series[me.stationary_bootstrap_indices(len(series), 5.0, rng)].mean()
    return float(np.quantile(means, quantile))


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
    reasons: dict[str, int] = defaultdict(int)
    for t in trades:
        reasons[t.reason] += 1
    bound = lower_bound(pnl, quantile=0.10 / COMPARISONS) if len(trades) else float("nan")
    first, second = float(pnl[:half].sum()), float(pnl[half:].sum())
    result = {
        "trades": len(trades),
        "win_rate": len(wins) / len(nets) if nets else None,
        "mean_net_r": float(np.mean([t.net / t.risk_money for t in trades])) if trades else None,
        "mean_net_return_pct": float(np.mean([t.net / (t.entry * t.quantity) for t in trades]) * 100) if trades else None,
        "total_net_pnl": float(sum(nets)),
        "profit_factor": (sum(wins) / sum(losses)) if losses else None,
        "max_drawdown_rupees": float(np.max(np.maximum.accumulate(curve) - curve)),
        "exit_reasons": dict(reasons),
        "session_pnl_lower_bound": bound,
        "first_half": first,
        "second_half": second,
    }
    result["profitable"] = bool(len(trades) >= 100 and result["total_net_pnl"] > 0 and bound > 0 and first > 0 and second > 0)
    return result


def run() -> dict[str, object]:
    er.split_snapshots()
    books = [Book("A_daily_zone_15m_entry", None, 15, False), Book("B_1h_zone_5m_entry", 60, 5, True)]
    symbols = er.stock_symbols()
    all_days = sorted({er._ist(r["end"]).date() for r in er._bars(symbols[0], "1d") if er.regular(er._ist(r["end"]).date())})
    first_day = all_days[WARMUP_SESSIONS]
    sessions = [day for day in all_days if day >= first_day]
    report: dict[str, object] = {"protocol": "services/quant/docs/order-blocks-protocol.md", "period": {"first": first_day.isoformat(), "last": sessions[-1].isoformat(), "sessions": len(sessions)}, "books": {}}
    for book in books:
        refined, baseline = [], []
        for symbol in symbols:
            five = five_minute(symbol)
            ltf = five if book.ltf_minutes == 5 else resample(five, book.ltf_minutes)
            htf = daily(symbol) if book.htf_minutes is None else resample(five, book.htf_minutes)
            refined += one_at_a_time(candidate_trades(symbol, htf, ltf, book, refine=True, first_day=first_day))
            baseline += one_at_a_time(candidate_trades(symbol, htf, ltf, book, refine=False, first_day=first_day))
            print(f"{book.name} {symbol}: {len(refined)} refined / {len(baseline)} baseline trades so far", flush=True)
        report["books"][book.name] = {"mtf_refined": describe(refined, sessions), "htf_only_baseline": describe(baseline, sessions)}  # type: ignore[index]
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=er.ROOT / "services/quant/docs/results/order-blocks-result.json")
    args = parser.parse_args()
    report = run()
    args.out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()

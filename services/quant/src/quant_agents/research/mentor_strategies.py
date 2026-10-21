"""The mentor's three strategies (from screenshots of his settings), with and without a stop loss.

Definitions, interpretations and charges are in services/quant/docs/mentor-strategies.md. The parameters
are his, not tuned here. Open positions are marked to market at the end, so a loss that was never sold
still counts.

    python -m quant_agents.research.mentor_strategies
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from quant_agents.research import agent_tuning as at
from quant_agents.research import exit_rules as er
from quant_agents.research.price_action import BARS, Grid, bar_index, build_grid

START, END = date(2024, 4, 1), date(2026, 10, 5)
NOTIONAL = 20000.0
SLIP = 0.0005
EOD = bar_index(1515)
HANDOFF_DAYS = 30
POSITION_CAP = 35

# --- Zerodha charges (zerodha.com/charges, checked 2026-10-21) ---------------------------------------
TXN = 0.0000307  # NSE transaction charge
SEBI = 10 / 1e7
GST = 0.18
DP = 15.34  # per scrip per sell day, GST included; delivery sells only


def intraday_charges(buy: float, sell: float) -> float:
    """Bought and sold the same session: intraday rates, no DP (the shares never reach the demat account)."""
    brokerage = (min(buy * 0.0003, 20.0) if buy else 0.0) + (min(sell * 0.0003, 20.0) if sell else 0.0)
    exchange = (buy + sell) * TXN
    sebi = (buy + sell) * SEBI
    return brokerage + sell * 0.00025 + buy * 0.00003 + exchange + sebi + GST * (brokerage + exchange + sebi)


def delivery_charges(buy: float, sell: float) -> float:
    """Held overnight: zero brokerage, STT 0.1% both sides, stamp 0.015% on the buy, DP on the sell."""
    exchange = (buy + sell) * TXN
    sebi = (buy + sell) * SEBI
    return (buy + sell) * 0.001 + buy * 0.00015 + exchange + sebi + GST * (exchange + sebi) + (DP if sell else 0.0)


# --- per-symbol daily context (all known before the session opens) ------------------------------------


@dataclass
class DailyContext:
    row: dict[int, int]  # session ordinal -> daily index
    close: np.ndarray
    high: np.ndarray
    low: np.ndarray
    volume: np.ndarray
    ema_prev: np.ndarray  # 20-day EMA of closes through the previous session

    @classmethod
    def of(cls, raw: dict[str, np.ndarray]) -> "DailyContext":
        close = raw["close"].astype(float)
        ema = np.full(len(close), np.nan)
        if len(close) >= 20:
            ema[19] = close[:20].mean()
            alpha = 2 / 21
            for k in range(20, len(close)):
                ema[k] = alpha * close[k] + (1 - alpha) * ema[k - 1]
        prev = np.concatenate([[np.nan], ema[:-1]])
        return cls({int(s): k for k, s in enumerate(raw["sessions"])}, close, raw["high"].astype(float), raw["low"].astype(float), raw["last_volume"].astype(float), prev)

    def k(self, session: int) -> int | None:
        return self.row.get(session)

    def prev_close(self, k: int) -> float:
        return self.close[k - 1] if k >= 1 else math.nan

    def avg_volume(self, k: int, days: int = 10) -> float:
        return float(np.mean(self.volume[k - days: k])) if k >= days else math.nan

    def high_20(self, k: int) -> float:
        return float(np.max(self.high[k - 20: k])) if k >= 20 else math.nan

    def down_days(self, k: int) -> int:
        count, j = 0, k - 1
        while j >= 1 and self.close[j] < self.close[j - 1]:
            count, j = count + 1, j - 1
        return count

    def pivot_r1(self, k: int) -> float:
        if k < 1:
            return math.nan
        p = (self.high[k - 1] + self.low[k - 1] + self.close[k - 1]) / 3
        return 2 * p - self.low[k - 1]


# --- positions -----------------------------------------------------------------------------------------


@dataclass
class Lot:
    qty: int
    price: float  # fill price including slippage
    session: int  # row in the 5-minute grid


@dataclass
class Position:
    symbol: str
    opened: int  # grid row
    lots: list[Lot] = field(default_factory=list)
    tranche2_done: bool = False
    t1_done: bool = False

    @property
    def qty(self) -> int:
        return sum(lot.qty for lot in self.lots)

    @property
    def cost(self) -> float:
        return sum(lot.qty * lot.price for lot in self.lots)

    @property
    def avg(self) -> float:
        return self.cost / self.qty if self.qty else math.nan


@dataclass
class Book:
    closed: list[dict] = field(default_factory=list)
    open: dict[str, Position] = field(default_factory=dict)
    handed_off: list[dict] = field(default_factory=list)
    equity_marks: list[float] = field(default_factory=list)
    deployed_marks: list[float] = field(default_factory=list)
    realised: float = 0.0
    entries: int = 0

    def sell(self, pos: Position, qty: int, price: float, row: int, reason: str) -> None:
        """Sell qty (oldest lots first); same-session lots at intraday rates, older ones at delivery rates."""
        remaining, gross, charges = qty, 0.0, 0.0
        delivery_sell = 0.0
        while remaining > 0 and pos.lots:
            lot = pos.lots[0]
            take = min(remaining, lot.qty)
            buy, sell = take * lot.price, take * price
            gross += sell - buy
            if lot.session == row:
                charges += intraday_charges(buy, sell)
            else:
                charges += delivery_charges(buy, sell) - DP  # DP once per scrip per day, added below
                delivery_sell += sell
            lot.qty -= take
            remaining -= take
            if lot.qty == 0:
                pos.lots.pop(0)
        if delivery_sell:
            charges += DP
        net = gross - charges
        self.realised += net
        self.closed.append({"symbol": pos.symbol, "net": net, "gross": gross, "reason": reason, "row": row, "held_rows": row - pos.opened})


def unrealised(pos: Position, price: float) -> float:
    return sum(lot.qty * (price - lot.price) for lot in pos.lots) - delivery_charges(pos.cost, pos.qty * price)


# --- strategy rules ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Rules:
    name: str
    scan: tuple[int, int]  # first and last signal bar index
    scan_every: int  # bars between scans
    targets: tuple[float, float]  # T1, T2 above average cost
    stop: float | None  # below average cost; None = the mentor's no-stop setting
    exit_same_day_if_positive: bool
    handoff_days: int | None


MOMENTUM = Rules("market_boom_momentum", (bar_index(930), bar_index(1500)), 1, (0.01, 0.015), None, True, HANDOFF_DAYS)
PIVOTAL = Rules("new_pivotal", (bar_index(1000), bar_index(1300)), 1, (0.02, 0.035), None, True, HANDOFF_DAYS)
DIP = Rules("ema_dip_reversion", (bar_index(945), bar_index(1515)), 6, (math.nan, math.nan), None, False, None)
STOPS = {"market_boom_momentum": 0.01, "new_pivotal": 0.02, "ema_dip_reversion": 0.10}


def momentum_signal(g: Grid, d: DailyContext, s: int, b: int, k: int) -> bool:
    prev, ema, close = d.prev_close(k), d.ema_prev[k], g.close[s, b]
    avg, ceiling = d.avg_volume(k), d.high_20(k)
    if any(math.isnan(x) for x in (prev, ema, close, avg, ceiling)) or b < 2:
        return False
    gain = close / prev - 1
    green = all(g.close[s, j] > g.open[s, j] for j in (b - 2, b - 1, b))
    cum_volume = g.cum[s, b]
    return (
        0.005 <= gain <= 0.0075
        and green
        and cum_volume > avg * (b + 1) / BARS
        and abs(close / ema - 1) <= 0.03
        and close <= ceiling * 0.98
    )


def pivotal_signal(g: Grid, d: DailyContext, s: int, b: int, k: int) -> bool:
    prev, r1, close, avg = d.prev_close(k), d.pivot_r1(k), g.close[s, b], d.avg_volume(k)
    if any(math.isnan(x) for x in (prev, r1, close, avg)) or b < 1 or math.isnan(g.close[s, b - 1]):
        return False
    gain = close / prev - 1
    crossed = close > r1 >= g.close[s, b - 1]
    return 0.01 <= gain <= 0.04 and crossed and g.cum[s, b] > avg * (b + 1) / BARS


def dip_signal(g: Grid, d: DailyContext, s: int, b: int, k: int) -> bool:
    prev, ema, close = d.prev_close(k), d.ema_prev[k], g.close[s, b]
    if any(math.isnan(x) for x in (prev, ema, close)):
        return False
    below = 1 - close / ema
    return 0.05 <= below <= 0.12 and d.down_days(k) >= 3 and close / prev - 1 <= -0.01


SIGNALS = {"market_boom_momentum": momentum_signal, "new_pivotal": pivotal_signal, "ema_dip_reversion": dip_signal}


def run_strategy(rules: Rules, grids: dict[str, Grid], dailies: dict[str, DailyContext], sessions: np.ndarray) -> dict:
    book = Book()
    signal = SIGNALS[rules.name]
    lo, hi = START.toordinal(), END.toordinal()
    rows = [s for s in range(len(sessions)) if lo <= sessions[s] <= hi]
    last_price: dict[str, float] = {}
    for s in rows:
        session = int(sessions[s])
        ks = {symbol: d.k(session) for symbol, d in dailies.items()}
        for b in range(BARS):
            # 1) manage open positions on this bar
            for symbol in list(book.open):
                pos, g, k = book.open[symbol], grids[symbol], ks[symbol]
                o, hi_, lo_, c = g.open[s, b], g.high[s, b], g.low[s, b], g.close[s, b]
                if math.isnan(c):
                    continue
                last_price[symbol] = c
                if rules.handoff_days is not None and session - int(sessions[pos.opened]) >= rules.handoff_days:
                    book.handed_off.append({"symbol": symbol, "unrealised": unrealised(pos, c), "days": session - int(sessions[pos.opened])})
                    del book.open[symbol]
                    continue
                if rules.stop is not None:
                    stop = pos.avg * (1 - rules.stop)
                    if lo_ <= stop:
                        book.sell(pos, pos.qty, min(o, stop) * (1 - SLIP) if o <= stop else stop * (1 - SLIP), s, "stop")
                        del book.open[symbol]
                        continue
                if rules.name == "ema_dip_reversion":
                    ema = dailies[symbol].ema_prev[k] if k is not None else math.nan
                    if math.isnan(ema):
                        continue
                    first_qty = pos.lots[0].qty if pos.lots else 0
                    if not pos.t1_done and hi_ >= ema:
                        book.sell(pos, first_qty, max(o, ema) if o >= ema else ema, s, "target_ema")
                        pos.t1_done = True
                    if pos.qty and hi_ >= ema * 1.03:
                        book.sell(pos, pos.qty, ema * 1.03 if o < ema * 1.03 else o, s, "target_ema_plus_3")
                    if not pos.qty:
                        del book.open[symbol]
                    continue
                t1, t2 = pos.avg * (1 + rules.targets[0]), pos.avg * (1 + rules.targets[1])
                if not pos.t1_done and hi_ >= t1:
                    half = pos.qty // 2
                    if half:
                        book.sell(pos, half, max(o, t1), s, "target_1")
                    pos.t1_done = True
                if pos.qty and hi_ >= t2:
                    book.sell(pos, pos.qty, max(o, t2), s, "target_2")
                if pos.qty and b == EOD and rules.exit_same_day_if_positive and pos.lots and all(lot.session == s for lot in pos.lots):
                    price = c * (1 - SLIP)
                    if sum(lot.qty * (price - lot.price) for lot in pos.lots) - intraday_charges(pos.cost, pos.qty * price) > 0:
                        book.sell(pos, pos.qty, price, s, "eod_positive")
                if not pos.qty:
                    del book.open[symbol]
            # 2) new entries on scan bars, filled at the next bar's open
            if rules.scan[0] <= b <= rules.scan[1] and (b - rules.scan[0]) % rules.scan_every == 0 and b + 1 < BARS:
                for symbol, g in grids.items():
                    k = ks[symbol]
                    if k is None:
                        continue
                    held = book.open.get(symbol)
                    if rules.name == "ema_dip_reversion" and held is not None and not held.tranche2_done:
                        ema = dailies[symbol].ema_prev[k]
                        close = g.close[s, b]
                        if not math.isnan(ema) and not math.isnan(close) and 0.08 <= 1 - close / ema <= 0.12 and not math.isnan(g.open[s, b + 1]):
                            fill = g.open[s, b + 1] * (1 + SLIP)
                            held.lots.append(Lot(int(NOTIONAL // fill), fill, s))
                            held.tranche2_done = True
                        continue
                    if held is not None or len(book.open) >= POSITION_CAP or not signal(g, dailies[symbol], s, b, k):
                        continue
                    if math.isnan(g.open[s, b + 1]):
                        continue
                    fill = g.open[s, b + 1] * (1 + SLIP)
                    qty = int(NOTIONAL // fill)
                    if qty >= 1:
                        book.open[symbol] = Position(symbol, s, [Lot(qty, fill, s)])  # filled on bar b+1, same session
                        book.entries += 1
        marked = sum(unrealised(pos, last_price.get(sym, pos.avg)) for sym, pos in book.open.items())
        handed = sum(item["unrealised"] for item in book.handed_off)
        book.equity_marks.append(book.realised + marked + handed)
        book.deployed_marks.append(sum(pos.cost for pos in book.open.values()))
    return summarise(rules, book, last_price, sessions, rows)


def summarise(rules: Rules, book: Book, last_price: dict[str, float], sessions: np.ndarray, rows: list[int]) -> dict:
    nets = np.array([t["net"] for t in book.closed]) if book.closed else np.array([])
    open_unreal = {sym: unrealised(pos, last_price.get(sym, pos.avg)) for sym, pos in book.open.items()}
    end_row = rows[-1]
    ages = [int(sessions[end_row]) - int(sessions[pos.opened]) for pos in book.open.values()]
    equity = np.array(book.equity_marks)
    peak = np.maximum.accumulate(equity) if len(equity) else equity
    by_year: dict[str, float] = {}
    for t in book.closed:
        year = str(date.fromordinal(int(sessions[t["row"]])).year)
        by_year[year] = by_year.get(year, 0.0) + t["net"]
    handed_total = float(sum(item["unrealised"] for item in book.handed_off))
    total = float(book.realised + sum(open_unreal.values()) + handed_total)
    deployed_peak = float(max(book.deployed_marks)) if book.deployed_marks else 0.0
    return {
        "strategy": rules.name,
        "stop": rules.stop,
        "entries": book.entries,
        "closed_trades": int(len(nets)),  # sells; a position sold in two halves counts twice
        "closed_losing_trades": int((nets < 0).sum()) if len(nets) else 0,
        "closed_win_rate": float((nets > 0).mean()) if len(nets) else None,
        "realised_net": float(book.realised),
        "realised_by_year": by_year,
        "open_positions_at_end": len(book.open),
        "open_unrealised": float(sum(open_unreal.values())),
        "open_losing": int(sum(1 for v in open_unreal.values() if v < 0)),
        "oldest_open_days": max(ages) if ages else 0,
        "handed_off_after_30_days": len(book.handed_off),
        "handed_off_unrealised": handed_total,
        "total_net_including_open": total,
        "peak_capital_deployed": deployed_peak,
        "return_on_peak_capital_pct": total / deployed_peak * 100 if deployed_peak else None,
        "max_drawdown": float(np.max(peak - equity)) if len(equity) else 0.0,
        "exit_reasons": {reason: sum(1 for t in book.closed if t["reason"] == reason) for reason in sorted({t["reason"] for t in book.closed})},
        "worst_open": sorted(((sym, round(v)) for sym, v in open_unreal.items()), key=lambda x: x[1])[:5],
    }


def run() -> dict:
    symbols = er.stock_symbols()
    nifty = at.load("NIFTY50", "5m")
    sessions = np.unique(nifty["sessions"]).astype(int)
    grids = {symbol: build_grid(at.load(symbol, "5m"), sessions) for symbol in symbols}
    for grid in grids.values():
        grid.cum = np.nancumsum(np.nan_to_num(grid.volume, nan=0.0), axis=1)  # type: ignore[attr-defined]
    dailies = {symbol: DailyContext.of(at.load(symbol, "1d")) for symbol in symbols}
    results = []
    for base in (MOMENTUM, PIVOTAL, DIP):
        for stop in (None, STOPS[base.name]):
            rules = Rules(base.name, base.scan, base.scan_every, base.targets, stop, base.exit_same_day_if_positive, base.handoff_days)
            results.append(run_strategy(rules, grids, dailies, sessions))
            print(json.dumps({k: results[-1][k] for k in ("strategy", "stop", "closed_trades", "closed_losing_trades", "realised_net", "open_positions_at_end", "open_unrealised", "total_net_including_open", "max_drawdown")}), flush=True)
    return {"definitions": "services/quant/docs/mentor-strategies.md", "period": [START.isoformat(), END.isoformat()], "results": results}


def main() -> None:
    out = er.ROOT / "services/quant/docs/results/mentor-strategies.json"
    out.write_text(json.dumps(run(), indent=2, default=str))


if __name__ == "__main__":
    main()

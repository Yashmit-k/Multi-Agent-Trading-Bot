"""Published anomalies across the whole NSE market, and cross-asset ETF strategies.

Per services/quant/docs/whole-market-protocol.md, scored once.

    python -m quant_agents.research.whole_market
"""

from __future__ import annotations

import json
import math
from datetime import date

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research.bhavcopy import Panel, load
from quant_agents.research.mentor_strategies import delivery_charges
from quant_agents.research.risk_off_nifty import etf_costs

PERIODS = {"train": (date(2016, 1, 1), date(2020, 12, 31)), "validate": (date(2021, 1, 1), date(2023, 12, 31)), "test": (date(2024, 1, 1), date(2026, 10, 27))}
K = 14
Q = 0.10 / K
LOOK, SKIP, UNIVERSE, HOLD = 252, 21, 500, 20
BUFFER = HOLD  # a holding is kept while it ranks within BUFFER (BUFFER = HOLD: the plain top-HOLD rule)
NOTIONAL = 20_000.0
SLIP = 0.0010
ETF_SLIP = 0.0005
CASH = 0.06
LOCK = 0.049
EVENT_GAP = 0.20
STOCK_RULES = ("mom_12_1", "resid_mom", "high_52w", "frog_pan", "low_vol", "low_max", "rev_1m", "seasonal", "amihud", "conservative")
ASSETS = ("NIFTYBEES", "JUNIORBEES", "MON100", "GOLDBEES")


# --- shared -------------------------------------------------------------------------------------------


class Market:
    def __init__(self, panel: Panel) -> None:
        self.p = panel
        with np.errstate(invalid="ignore", divide="ignore"):
            gap = panel.open / panel.prev - 1
            # Amendment A: an open > 20% from PREVCLOSE is a split / bonus / listing; count only open -> close that day
            self.event = np.abs(gap) > EVENT_GAP
            self.r = np.where(self.event, panel.close / panel.open - 1, panel.close / panel.prev - 1).astype(np.float64)
        self.d = [date.fromordinal(int(x)) for x in panel.days]
        self.month_ends = [t for t in range(len(self.d) - 1) if self.d[t].month != self.d[t + 1].month]
        r0 = np.where(np.isnan(self.r), 0.0, self.r)
        self.index = np.cumprod(1 + r0, axis=0)  # adjusted price index per chain (flat on missing days)
        self.members = {t: self.universe(t) for t in self.month_ends if t >= LOOK}
        self.market = self._market_returns()

    def overnight(self, t: int, j: int) -> float:
        """Previous close -> today's open, with a corporate-action day treated as no move."""
        if self.event[t, j] or math.isnan(self.p.open[t, j]):
            return 1.0
        return float(self.p.open[t, j] / self.p.prev[t, j])

    def universe(self, t: int) -> np.ndarray:
        p = self.p
        window = self.r[t - LOOK + 1: t + 1]
        ok = (p.series[t] == 1) & ~p.etf & (p.close[t] >= 20) & ((~np.isnan(window)).sum(axis=0) >= 240)
        cols = np.where(ok)[0]
        turnover = np.nanmedian(p.value[t - 125: t + 1, cols], axis=0)
        order = np.argsort(-np.nan_to_num(turnover, nan=-1))
        return cols[order[:UNIVERSE]]

    def _market_returns(self) -> np.ndarray:
        out = np.full(len(self.d), np.nan)
        ends = sorted(self.members)
        for a, b in zip(ends, ends[1:] + [len(self.d) - 1]):
            cols = self.members[a]
            out[a + 1: b + 1] = np.nanmean(self.r[a + 1: b + 1, cols], axis=1)
        # before the first membership: all EQ stocks with data
        first = ends[0]
        eq = (~self.p.etf) & (self.p.series[first] == 1)
        out[: first + 1] = np.nanmean(self.r[: first + 1][:, eq], axis=1)
        return out

    def period(self, label: str, rule: str = "") -> tuple[int, int]:
        lo, hi = PERIODS[label]
        if rule == "seasonal" and label == "train":
            lo = date(2018, 1, 1)
        days = self.p.days
        first = min(self.members) + 1  # the first session with a full 252-session look-back behind it
        return max(first, int(np.searchsorted(days, lo.toordinal()))), int(np.searchsorted(days, hi.toordinal(), side="right")) - 1


def _boot(values: list[float], q: float) -> float:
    arr = np.array(values)
    rng = np.random.default_rng(0)
    return float(np.quantile(arr[rng.integers(0, len(arr), size=(2000, len(arr)))].mean(axis=1), q))


# --- stock scores (higher = better), using data to the close of t only ------------------------------


def scores(m: Market, rule: str, t: int, cols: np.ndarray) -> np.ndarray:
    r = m.r[t - LOOK + 1: t + 1, cols]
    idx = m.index[:, cols]
    mom = idx[t - SKIP] / idx[t - LOOK] - 1
    if rule == "mom_12_1":
        return mom
    if rule == "low_vol":
        return -np.nanstd(r, axis=0)
    if rule == "low_max":
        last = np.nan_to_num(r[-21:], nan=-np.inf)
        return -np.sort(last, axis=0)[-5:].mean(axis=0)
    if rule == "rev_1m":
        return -(idx[t] / idx[t - SKIP] - 1)
    if rule == "high_52w":
        with np.errstate(invalid="ignore", divide="ignore"):
            adj_high = m.p.high[t - LOOK + 1: t + 1, cols] * (idx[t - LOOK + 1: t + 1] / m.p.close[t - LOOK + 1: t + 1, cols])
        return idx[t] / np.nanmax(adj_high, axis=0)
    if rule == "amihud":
        v = m.p.value[t - LOOK + 1: t + 1, cols].astype(np.float64)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.nanmean(np.where(v > 0, np.abs(r) / v, np.nan), axis=0)
    if rule == "resid_mom":
        x = m.market[t - LOOK + 1: t + 1]
        out = np.full(len(cols), np.nan)
        for k in range(len(cols)):
            y = r[:, k]
            ok = ~np.isnan(y) & ~np.isnan(x)
            if ok.sum() < 200:
                continue
            beta, alpha = np.polyfit(x[ok], y[ok], 1)
            resid = np.where(ok, y - alpha - beta * x, np.nan)[: LOOK - SKIP]
            sd = np.nanstd(resid)
            out[k] = np.nansum(resid) / sd if sd > 0 else np.nan
        return out
    if rule == "frog_pan":
        part = r[: LOOK - SKIP]
        n = (~np.isnan(part)).sum(axis=0)
        discrete = np.sign(mom) * (((part < 0).sum(axis=0) - (part > 0).sum(axis=0)) / np.maximum(n, 1))
        top = mom >= np.nanmedian(mom)
        return np.where(top, -discrete, -np.inf)
    if rule == "conservative":
        vol_rank = np.argsort(np.argsort(np.nanstd(r, axis=0)))
        mom_rank = np.argsort(np.argsort(-np.nan_to_num(mom, nan=-np.inf)))
        return -(vol_rank + mom_rank) / 2.0
    if rule == "seasonal":
        target = m.d[t + 1].month
        ends = [k for k in m.month_ends if k <= t]
        rets = [idx[b] / idx[a] - 1 for a, b in zip(ends, ends[1:]) if m.d[b].month == target]
        if len(rets) < 3:
            return np.full(len(cols), np.nan)
        stack = np.vstack(rets)
        count = (~np.isnan(stack)).sum(axis=0)
        return np.where(count >= 3, np.nanmean(stack, axis=0), np.nan)
    raise ValueError(rule)


def _locked(m: Market, t: int, j: int, up: bool) -> bool:
    p = m.p
    o, h, l, pc = p.open[t, j], p.high[t, j], p.low[t, j], p.prev[t, j]
    if math.isnan(o):
        return False
    flat = o == h == l
    move = o / pc - 1
    return bool(flat and (move >= LOCK if up else move <= -LOCK))


def simulate_stocks(m: Market, rule: str, label: str) -> dict[str, object]:
    lo, hi = m.period(label, rule)
    return simulate_range(m, rule, lo, hi)


def simulate_range(m: Market, rule: str, lo: int, hi: int) -> dict[str, object]:
    """Fixed-capital P&L: each day, sells at the open, then buys at the open, then holdings roll to the close.

    Plans at lo - 1 when that is a month-end, so a book that starts the day after a month-end is invested at once.
    """
    p = m.p
    paid: dict[int, float] = {}  # chain -> rupees paid, including charges
    trades: list[dict[str, object]] = []
    held: dict[int, float] = {}  # chain -> value at the last close
    stale: dict[int, int] = {}
    pnl = charges = 0.0
    buys = 0
    want_sell: set[int] = set()
    to_buy: list[int] = []
    marks: dict[int, float] = {}

    def plan(t: int, selling: set[int]) -> tuple[set[int], list[int]]:
        cols = m.members[t]
        s = scores(m, rule, t, cols)
        order = [int(cols[k]) for k in np.argsort(-np.nan_to_num(s, nan=-np.inf)) if np.isfinite(s[k])]
        target: list[int] = []
        if BUFFER > HOLD:
            # Keep a holding while it ranks within BUFFER; fill the free slots with the best-ranked stocks not held.
            rank = {j: k for k, j in enumerate(order)}
            target = [j for j in held if j not in selling and rank.get(j, BUFFER) < BUFFER][:HOLD]
        for j in order:
            if j in target:
                continue
            if len(target) == HOLD:
                break
            if j in held and j not in selling:
                if BUFFER > HOLD:
                    continue  # ranked below the buffer: sold
                target.append(j)
                continue
            o = p.open[t + 1, j]
            if j in held or math.isnan(o) or o * (1 + SLIP) > NOTIONAL or p.series[t + 1, j] != 1 or _locked(m, t + 1, j, up=True):
                continue  # cannot be bought at tomorrow's open: take the next one
            target.append(j)
        return selling | {j for j in held if j not in target}, [j for j in target if j not in held]

    if lo - 1 in m.members:
        want_sell, to_buy = plan(lo - 1, want_sell)
    for t in range(lo, hi + 1):
        start = set(held)
        for j in sorted(want_sell):
            if j not in held:
                want_sell.discard(j)
                continue
            o = p.open[t, j]
            if math.isnan(o):
                stale[j] = stale.get(j, 0) + 1
                if stale[j] >= 21:  # stopped trading: sold at the last close
                    fee = delivery_charges(0.0, held[j])
                    value = held.pop(j)
                    pnl += value - fee
                    charges += fee
                    want_sell.discard(j)
                    trades.append({"day": m.d[t].isoformat(), "side": "SELL", "symbol": str(p.symbols[j]), "value": value, "charges": fee, "pnl": value - fee - paid.pop(j, 0.0), "note": "stopped trading"})
                continue
            if _locked(m, t, j, up=False):
                continue  # locked at the lower circuit: try again tomorrow
            value = held.pop(j) * m.overnight(t, j) * (1 - SLIP)
            fee = delivery_charges(0.0, value)
            pnl += value - fee
            charges += fee
            want_sell.discard(j)
            trades.append({"day": m.d[t].isoformat(), "side": "SELL", "symbol": str(p.symbols[j]), "value": value, "charges": fee, "pnl": value - fee - paid.pop(j, 0.0)})
        for j in held:
            r = m.r[t, j]
            if j in start and not math.isnan(r):
                held[j] *= 1 + r
        for j in to_buy:
            price = p.open[t, j] * (1 + SLIP)
            qty = int(NOTIONAL // price)
            cost = qty * price
            fee = delivery_charges(cost, 0.0)
            pnl -= cost + fee
            charges += fee
            held[j] = qty * float(p.close[t, j])
            paid[j] = cost + fee
            buys += 1
            trades.append({"day": m.d[t].isoformat(), "side": "BUY", "symbol": str(p.symbols[j]), "qty": qty, "price": price, "value": cost, "charges": fee})
        to_buy = []
        marks[t] = pnl + sum(held.values())
        if t in m.members and t < hi:
            want_sell, to_buy = plan(t, want_sell)
    final = sum(held.values())
    fee = sum(delivery_charges(0.0, v) for v in held.values())
    open_marks = dict(marks)
    if hi in marks:
        marks[hi] = pnl + final - fee  # liquidated at the end, for the backtest's totals
    holdings = [{"symbol": str(p.symbols[j]), "value": v, "cost": paid.get(j, 0.0), "pending_sell": j in want_sell} for j, v in held.items()]
    return {"marks": marks, "open_marks": open_marks, "capital": NOTIONAL * HOLD, "charges": charges + fee, "buys": buys, "lo": lo, "hi": hi,
            "holdings": holdings, "trades": trades, "pending_buys": [str(p.symbols[j]) for j in to_buy], "pending_sells": [str(p.symbols[j]) for j in want_sell]}


def monthly(m: Market, marks: dict[int, float], capital: float, lo: int, hi: int) -> list[tuple[int, float]]:
    """(month-end index, return on capital) for each month that ends inside [lo, hi]."""
    ends = [t for t in m.month_ends if lo <= t <= hi]
    if not ends or ends[-1] != hi:
        ends.append(hi)
    out, prev = [], 0.0
    start = lo - 1
    for t in ends:
        out.append((t, (marks[t] - prev) / capital))
        prev = marks[t]
        start = t
    return out


def benchmark_months(m: Market, months: list[tuple[int, float]], lo: int) -> list[float]:
    """Equal-weight Liquid-500, gross, close to close over each strategy month."""
    out, start = [], lo - 1
    for t, _ in months:
        anchor = max(k for k in m.members if k <= max(start, min(m.members)))
        cols = m.members[anchor]
        out.append(float(np.nanmean(m.index[t, cols] / m.index[start, cols] - 1)))
        start = t
    return out


def chain_of(m: Market, symbol: str) -> int:
    hits = np.where(m.p.symbols == symbol)[0]
    if len(hits) != 1:
        raise LookupError(f"{symbol}: {len(hits)} chains")
    return int(hits[0])


def asset_months(m: Market, j: int, months: list[tuple[int, float]], lo: int) -> list[float]:
    out, start = [], lo - 1
    for t, _ in months:
        out.append(float(m.index[t, j] / m.index[start, j] - 1))
        start = t
    return out


def decile_spread(m: Market, rule: str, label: str) -> float:
    lo, hi = m.period(label, rule)
    ends = [t for t in m.month_ends if lo - 1 <= t < hi and t in m.members]
    spreads = []
    for a, b in zip(ends, ends[1:] + [hi]):
        cols = m.members[a]
        s = scores(m, rule, a, cols)
        ok = np.isfinite(s)
        if ok.sum() < 100:
            continue
        cols, s = cols[ok], s[ok]
        fwd = m.index[b, cols] / m.index[a, cols] - 1
        order = np.argsort(-s)
        n = len(order) // 10
        spreads.append(float(np.nanmean(fwd[order[:n]]) - np.nanmean(fwd[order[-n:]])))
    return float(np.mean(spreads) * 100) if spreads else math.nan


def stock_study(m: Market) -> dict[str, object]:
    nifty = chain_of(m, "NIFTYBEES")
    out: dict[str, object] = {}
    gate = {}
    for rule in STOCK_RULES:
        per = {}
        pooled = []
        for label in PERIODS:
            sim = simulate_stocks(m, rule, label)
            months = monthly(m, sim["marks"], sim["capital"], sim["lo"], sim["hi"])
            strat = [x for _, x in months]
            bench = benchmark_months(m, months, sim["lo"])
            nb = asset_months(m, nifty, months, sim["lo"])
            excess = [a - b for a, b in zip(strat, bench)]
            pooled += excess
            per[label] = {
                "annual": float(np.mean(strat) * 12),
                "benchmark_annual": float(np.mean(bench) * 12),
                "niftybees_annual": float(np.mean(nb) * 12),
                "charges": sim["charges"],
                "buys": sim["buys"],
                "months": len(strat),
                "decile_spread_monthly_pct": decile_spread(m, rule, label),
                "worst_month": float(min(strat)),
            }
        beats_b = {k: bool(v["annual"] > v["benchmark_annual"]) for k, v in per.items()}
        beats_n = {k: bool(v["annual"] > v["niftybees_annual"]) for k, v in per.items()}
        low = _boot(pooled, Q)
        t_stat = float(np.mean(pooled) / (np.std(pooled, ddof=1) / math.sqrt(len(pooled))))
        gate[rule] = {"beats_benchmark": beats_b, "beats_niftybees": beats_n, "pooled_monthly_excess": float(np.mean(pooled)), "t_stat": t_stat, "bonferroni_low": low,
                      "works": bool(all(beats_b.values()) and all(beats_n.values()) and low > 0)}
        out[rule] = per
    out["gate"] = gate
    return out


# --- cross-asset ----------------------------------------------------------------------------------


def asset_study(m: Market) -> dict[str, object]:
    cols = {a: chain_of(m, a) for a in ASSETS}
    idx = m.index

    def trailing(j: int, t: int, sessions: int) -> float:
        return float(idx[t, j] / idx[t - sessions, j] - 1)

    def weights(rule: str, t: int) -> dict[str, float]:
        if rule == "one_over_n":
            return {a: 0.25 for a in ASSETS}
        if rule == "buy_hold_nifty":
            return {"NIFTYBEES": 1.0}
        if rule == "asset_mom":
            best = sorted(ASSETS, key=lambda a: trailing(cols[a], t, LOOK), reverse=True)[:2]
            return {a: 0.5 for a in best}
        if rule == "dual_mom":
            best = max(("NIFTYBEES", "MON100"), key=lambda a: trailing(cols[a], t, LOOK))
            return {best: 1.0} if trailing(cols[best], t, LOOK) > CASH else {}
        if rule == "risk_parity":
            inv = {a: 1 / np.nanstd(m.r[t - 62: t + 1, cols[a]]) for a in ASSETS}
            total = sum(inv.values())
            return {a: v / total for a, v in inv.items()}
        if rule == "gtaa_trend":
            ends = [k for k in m.month_ends if k <= t][-10:]
            return {a: 0.25 for a in ASSETS if idx[t, cols[a]] > np.mean(idx[ends, cols[a]])}
        raise ValueError(rule)

    rules = ("one_over_n", "buy_hold_nifty", "asset_mom", "dual_mom", "risk_parity", "gtaa_trend")
    capital = 400_000.0
    out: dict[str, object] = {}
    series: dict[str, dict[str, list[float]]] = {}
    for rule in rules:
        per = {}
        series[rule] = {}
        for label in PERIODS:
            lo, hi = m.period(label)
            hold = {a: 0.0 for a in ASSETS}  # rupee value at the last close
            cash = capital
            switch_cost = 0.0
            equity = []
            pending: dict[str, float] | None = weights(rule, lo - 1)
            for t in range(lo, hi + 1):
                if pending is not None:
                    # trade at today's open to the target weights
                    for a in ASSETS:
                        hold[a] *= m.overnight(t, cols[a])
                    total = cash + sum(hold.values())
                    for a in ASSETS:
                        target = total * pending.get(a, 0.0)
                        diff = target - hold[a]
                        if abs(diff) < 1:
                            continue
                        fee = etf_costs(diff, 0.0) if diff > 0 else etf_costs(0.0, -diff)
                        fee += abs(diff) * ETF_SLIP
                        switch_cost += fee
                        cash -= diff + fee
                        hold[a] = target
                    for a in ASSETS:
                        hold[a] *= m.p.close[t, cols[a]] / m.p.open[t, cols[a]]
                    pending = None
                else:
                    for a in ASSETS:
                        r = m.r[t, cols[a]]
                        if not math.isnan(r):
                            hold[a] *= 1 + r
                cash *= 1 + CASH / 252
                equity.append(cash + sum(hold.values()))
                if t in m.month_ends and t < hi:
                    pending = weights(rule, t)
            ends = [k - lo for k in range(lo, hi + 1) if k in m.month_ends or k == hi]
            values = np.array([capital] + [equity[k] for k in ends])
            rets = values[1:] / values[:-1] - 1
            years = (m.p.days[hi] - m.p.days[lo - 1]) / 365.25
            eq = np.array([capital] + equity)
            per[label] = {
                "cagr": float((equity[-1] / capital) ** (1 / years) - 1),
                "sharpe": float(rets.mean() / rets.std(ddof=1) * math.sqrt(12)),
                "max_drawdown": float(np.max(1 - eq / np.maximum.accumulate(eq))),
                "costs": switch_cost,
            }
            series[rule][label] = rets.tolist()
        out[rule] = per
    gate = {}
    for rule in ("asset_mom", "dual_mom", "risk_parity", "gtaa_trend"):
        cagr = {k: bool(out[rule][k]["cagr"] > out["one_over_n"][k]["cagr"]) for k in PERIODS}  # type: ignore[index]
        sharpe = {k: bool(out[rule][k]["sharpe"] > out["one_over_n"][k]["sharpe"]) for k in PERIODS}  # type: ignore[index]
        pooled = [a - b for k in PERIODS for a, b in zip(series[rule][k], series["one_over_n"][k])]
        low = _boot(pooled, Q)
        gate[rule] = {"cagr_beats_1n": cagr, "sharpe_beats_1n": sharpe, "bonferroni_low": low, "works": bool(all(cagr.values()) and all(sharpe.values()) and low > 0)}
    out["gate"] = gate
    return out


def run() -> dict[str, object]:
    m = Market(load())
    return {"protocol": "services/quant/docs/whole-market-protocol.md", "sessions": len(m.d), "first": m.d[0], "last": m.d[-1],
            "stocks": stock_study(m), "assets": asset_study(m)}


def main() -> None:
    report = run()
    (er.ROOT / "services/quant/docs/results/whole-market-result.json").write_text(json.dumps(report, indent=1, default=str))
    for rule in STOCK_RULES:
        per = report["stocks"][rule]  # type: ignore[index]
        print(f"{rule:13}", "  ".join(f"{k} {v['annual']:+.1%} (bm {v['benchmark_annual']:+.1%}, nb {v['niftybees_annual']:+.1%}, spread {v['decile_spread_monthly_pct']:+.2f}%/m, buys {v['buys']})" for k, v in per.items()))
    print(json.dumps(report["stocks"]["gate"], indent=1))  # type: ignore[index]
    for rule, per in report["assets"].items():  # type: ignore[union-attr]
        if rule != "gate":
            print(f"{rule:15}", "  ".join(f"{k} cagr {v['cagr']:+.1%} sharpe {v['sharpe']:.2f} dd {v['max_drawdown']:.0%}" for k, v in per.items()))
    print(json.dumps(report["assets"]["gate"], indent=1))  # type: ignore[index]


if __name__ == "__main__":
    main()

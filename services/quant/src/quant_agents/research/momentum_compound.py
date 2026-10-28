"""12-1 momentum as one compounding book: ₹1,00,000 invested once, never topped up or withdrawn. At every month-end
the whole book (holdings + cash) is split equally across the top 10, trading at the next open: holdings that left
the top 10 are sold, the rest are trimmed or topped up to an equal share, new ones are bought.

Same universe, score, charges (Zerodha delivery), slippage (10 bp each way) and circuit rules as
research.whole_market. Whole shares only; idle cash earns nothing. Result: services/quant/docs/momentum-compound.md.

    python -m quant_agents.research.momentum_compound
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import date

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research import whole_market as wm
from quant_agents.research.bhavcopy import load
from quant_agents.research.mentor_strategies import delivery_charges

CAPITAL = 100_000.0
HOLD = 10
START = date(2016, 2, 1)
OUT = er.ROOT / "services/quant/docs/results"


def simulate(m: wm.Market, *, rebalance_holdings: bool = True, start: date = START, end: date | None = None, fill_leftover: bool = False, park=None) -> dict[str, object]:
    """rebalance_holdings=False: holdings that stay in the top 10 are left alone; only new buys get an equal share.
    fill_leftover=True: after the split, the cash left by whole-share rounding buys one more share at a time of the
    most underweight holding that still fits, until no share fits.
    park: optional callable (t) -> chain or None; when it returns a chain, the whole book is held in that one security
    for the month (used to hold NIFTYBEES instead of the stocks)."""
    p = m.p
    lo = int(np.searchsorted(p.days, start.toordinal()))
    hi = len(m.d) - 1 if end is None else int(np.searchsorted(p.days, end.toordinal(), side="right")) - 1
    cash = CAPITAL
    held: dict[int, float] = {}  # chain -> value at the last close
    cost: dict[int, float] = {}  # chain -> rupees paid for what is still held (charges included), reduced pro rata on trims
    charges = 0.0
    trades: list[dict[str, object]] = []
    marks: dict[int, float] = {}
    plan: list[int] | None = None

    def ranked(t: int) -> list[int]:
        cols = m.members[t]
        s = wm.scores(m, "mom_12_1", t, cols)
        return [int(cols[k]) for k in np.argsort(-np.nan_to_num(s, nan=-np.inf)) if np.isfinite(s[k])]

    def tradable(t: int, j: int, budget: float) -> bool:
        o = p.open[t, j]
        return not (math.isnan(o) or o * (1 + wm.SLIP) > budget or p.series[t, j] != 1 or wm._locked(m, t, j, up=True))

    def choose(t: int) -> list[int]:
        """At the close of t: the top 10 that can be bought at the open of t + 1 (holdings count as they are)."""
        value = cash + sum(held.values())
        parked = park(t) if park is not None else None
        if parked is not None:
            return [parked]
        target: list[int] = []
        for j in ranked(t):
            if len(target) == HOLD:
                break
            if j in held or tradable(t + 1, j, value / HOLD):
                target.append(j)
        return target

    if lo - 1 in m.members:
        plan = choose(lo - 1)
    for t in range(lo, hi + 1):
        start = set(held)
        if plan is not None:
            # Opens: value everything at the open, then sell, trim, top up and buy towards value / 10 each.
            at_open = {j: v * m.overnight(t, j) for j, v in held.items()}
            total = cash + sum(at_open.values())
            share = total / max(len(plan), 1)
            keep_as_is = set(plan) & set(held) if not rebalance_holdings else set()
            if not rebalance_holdings and plan:
                free = total - sum(at_open[j] for j in keep_as_is)
                newcomers = [j for j in plan if j not in held]
                share = free / len(newcomers) if newcomers else share
            orders = []
            for j in list(held):
                o = p.open[t, j]
                if math.isnan(o):
                    continue  # no price today: held as it is
                if j in keep_as_is:
                    continue
                want = share if j in plan else 0.0
                qty_now = at_open[j] / o
                qty_want = math.floor(want / (o * (1 + wm.SLIP))) if want else 0
                if qty_want < qty_now - 0.5:
                    if not want and wm._locked(m, t, j, up=False):
                        continue  # locked at the lower circuit: sell another day (next month's plan)
                    orders.append((j, qty_want - round(qty_now)))
            for j in plan:
                if j in held:
                    if j in keep_as_is:
                        continue
                    o = p.open[t, j]
                    if math.isnan(o):
                        continue
                    qty_now = round(at_open[j] / o)
                    qty_want = math.floor(share / (o * (1 + wm.SLIP)))
                    if qty_want > qty_now:
                        orders.append((j, qty_want - qty_now))
                elif tradable(t, j, share):
                    orders.append((j, math.floor(share / (p.open[t, j] * (1 + wm.SLIP)))))
            for j, delta in sorted(orders, key=lambda x: x[1]):  # sells (negative) before buys
                o = float(p.open[t, j])
                if delta < 0:
                    amount = -delta * o * (1 - wm.SLIP)
                    fee = delivery_charges(0.0, amount)
                    cash += amount - fee
                    charges += fee
                    remaining = at_open[j] - (-delta) * o
                    if remaining <= o * 0.5:
                        held.pop(j, None)
                        at_open.pop(j, None)
                        cost.pop(j, None)
                    else:
                        cost[j] = cost.get(j, 0.0) * remaining / at_open[j]
                        at_open[j] = remaining
                    trades.append({"day": m.d[t].isoformat(), "side": "SELL", "symbol": str(p.symbols[j]), "qty": -delta, "price": o * (1 - wm.SLIP), "charges": fee})
                elif delta > 0:
                    price = o * (1 + wm.SLIP)
                    qty = min(delta, math.floor((cash - 50) / (price * 1.0013))) if cash > 50 else 0
                    if qty <= 0:
                        continue
                    amount = qty * price
                    fee = delivery_charges(amount, 0.0)
                    cash -= amount + fee
                    charges += fee
                    at_open[j] = at_open.get(j, 0.0) + qty * o
                    cost[j] = cost.get(j, 0.0) + amount + fee
                    trades.append({"day": m.d[t].isoformat(), "side": "BUY", "symbol": str(p.symbols[j]), "qty": qty, "price": price, "charges": fee})
            if fill_leftover and plan:
                extra: dict[int, int] = {}
                while True:
                    fits = [j for j in plan if j in at_open and not math.isnan(p.open[t, j]) and float(p.open[t, j]) * (1 + wm.SLIP) * 1.0013 <= cash - 50]
                    if not fits:
                        break
                    j = min(fits, key=lambda k: at_open[k])
                    price = float(p.open[t, j]) * (1 + wm.SLIP)
                    cash -= price
                    at_open[j] += float(p.open[t, j])
                    extra[j] = extra.get(j, 0) + 1
                for j, qty in extra.items():
                    price = float(p.open[t, j]) * (1 + wm.SLIP)
                    fee = delivery_charges(qty * price, 0.0)
                    cash -= fee
                    charges += fee
                    cost[j] = cost.get(j, 0.0) + qty * price + fee
                    trades.append({"day": m.d[t].isoformat(), "side": "BUY", "symbol": str(p.symbols[j]), "qty": qty, "price": price, "charges": fee, "note": "leftover"})
            # From the open to the close for everything held after the trades.
            held = {j: v * (float(p.close[t, j]) / float(p.open[t, j])) if not math.isnan(p.open[t, j]) else v for j, v in at_open.items()}
            plan = None
        else:
            for j in held:
                r = m.r[t, j]
                if j in start and not math.isnan(r):
                    held[j] *= 1 + r
        marks[t] = cash + sum(held.values())
        if t in m.members and t < hi:
            plan = choose(t)
    holdings = [{"symbol": str(p.symbols[j]), "value": v, "cost": cost.get(j, 0.0), "weight": v / marks[hi]} for j, v in held.items()]
    return {"marks": marks, "charges": charges, "trades": trades, "lo": lo, "hi": hi, "final": marks[hi], "cash_end": cash, "holdings": holdings,
            "pending": [str(p.symbols[j]) for j in plan] if plan else []}


def summary(m: wm.Market, sim: dict[str, object]) -> dict[str, object]:
    marks, lo, hi = sim["marks"], sim["lo"], sim["hi"]
    ends = [t for t in m.month_ends if lo <= t <= hi] + ([hi] if hi not in m.month_ends else [])
    values = [CAPITAL] + [marks[t] for t in ends]
    months = [(m.d[t], values[k + 1] / values[k] - 1) for k, t in enumerate(ends)]
    fixed = [(t, 0.0) for t in ends]
    bench = wm.benchmark_months(m, fixed, lo)
    nifty = wm.asset_months(m, wm.chain_of(m, "NIFTYBEES"), fixed, lo)
    years = (m.p.days[hi] - m.p.days[lo - 1]) / 365.25
    eq = np.array(values)
    grow = lambda xs: float(np.prod([1 + x for x in xs]))  # noqa: E731
    by_year = defaultdict(lambda: {"start": None, "end": None, "bench": 1.0, "nifty": 1.0, "charges": 0.0})
    for k, (d, r) in enumerate(months):
        y = by_year[d.year]
        y["start"] = values[k] if y["start"] is None else y["start"]
        y["end"] = values[k + 1]
        y["bench"] *= 1 + bench[k]
        y["nifty"] *= 1 + nifty[k]
    for tr in sim["trades"]:
        by_year[int(tr["day"][:4])]["charges"] += tr["charges"]
    return {
        "start_value": CAPITAL,
        "final_value": float(sim["final"]),
        "cagr": float((sim["final"] / CAPITAL) ** (1 / years) - 1),
        "benchmark_final": CAPITAL * grow(bench),
        "niftybees_final": CAPITAL * grow(nifty),
        "max_drawdown": float(np.max(1 - eq / np.maximum.accumulate(eq))),
        "charges": float(sim["charges"]),
        "trades": len(sim["trades"]),
        "years": {y: v for y, v in sorted(by_year.items())},
        "months": [(d.isoformat(), r, b, n) for (d, r), b, n in zip(months, bench, nifty)],
    }


def main() -> None:
    m = wm.Market(load())
    full = simulate(m)
    lite = simulate(m, rebalance_holdings=False)
    report = {"full_rebalance": summary(m, full), "new_buys_only": summary(m, lite)}
    (OUT / "momentum-compound-result.json").write_text(json.dumps(report, indent=1, default=float))
    with (OUT / "momentum-compound-trades.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["day", "side", "symbol", "qty", "price", "charges"])
        w.writeheader()
        for tr in full["trades"]:
            w.writerow({k: (round(v, 2) if isinstance(v, float) else v) for k, v in tr.items()})
    for name, r in report.items():
        print(f"{name}: ₹1,00,000 -> ₹{r['final_value']:,.0f}  CAGR {r['cagr']:+.1%}  worst fall {r['max_drawdown']:.0%}  charges ₹{r['charges']:,.0f}  trades {r['trades']}  "
              f"| benchmark ₹{r['benchmark_final']:,.0f}  NIFTYBEES ₹{r['niftybees_final']:,.0f}")
        for y, v in r["years"].items():
            print(f"   {y}: ₹{v['start']:>12,.0f} -> ₹{v['end']:>12,.0f}  {v['end'] / v['start'] - 1:+7.1%}   benchmark {v['bench'] - 1:+7.1%}  niftybees {v['nifty'] - 1:+7.1%}  charges ₹{v['charges']:,.0f}")


if __name__ == "__main__":
    main()

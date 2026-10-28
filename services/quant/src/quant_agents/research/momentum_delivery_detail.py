"""Detailed backtest of 12-1 momentum with the delivery-% filter (V5 of momentum-variants-protocol.md): one continuous
₹1,00,000 book from 2020-02, month by month, its trades, a worked example month, and checks against chance.
Descriptive: the pre-registered verdict is in momentum-variants-result.md.

    python -m quant_agents.research.momentum_delivery_detail
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research import momentum_compound as mc
from quant_agents.research import momentum_variants as mv
from quant_agents.research import whole_market as wm
from quant_agents.research.bhavcopy import load

START = date(2020, 2, 1)
OUT = er.ROOT / "services/quant/docs/results"


def run(m, scorer=None):
    if scorer is not None:
        wm.scores = scorer
    try:
        sim = mc.simulate(m, start=START, fill_leftover=True)
    finally:
        wm.scores = mv.ORIGINAL
    lo, hi, marks = sim["lo"], sim["hi"], sim["marks"]
    ends = [t for t in m.month_ends if lo <= t <= hi] + ([hi] if hi not in m.month_ends else [])
    values = [mc.CAPITAL] + [marks[t] for t in ends]
    fixed = [(t, 0.0) for t in ends]
    bench = wm.benchmark_months(m, fixed, lo)
    nifty = wm.asset_months(m, wm.chain_of(m, "NIFTYBEES"), fixed, lo)
    years = (m.p.days[hi] - m.p.days[lo - 1]) / 365.25
    eq = np.array(values)
    peak = np.maximum.accumulate(eq)
    w = int(np.argmax(1 - eq / peak))
    p = int(np.argmax(eq[: w + 1]))
    return {"sim": sim, "ends": ends, "values": values, "bench": bench, "nifty": nifty, "years": years,
            "cagr": float((values[-1] / mc.CAPITAL) ** (1 / years) - 1), "dd": float(1 - eq[w] / peak[w]),
            "dd_from": m.d[ends[p - 1]].isoformat() if p else START.isoformat(), "dd_to": m.d[ends[w - 1]].isoformat() if w else START.isoformat(),
            "monthly": [values[k + 1] / values[k] - 1 for k in range(len(ends))]}


def random_within_top30(seed):
    def secondary(m, t, cols):
        return np.random.default_rng(seed * 7919 + t).random(len(cols))
    return mv._top30_then(secondary)


def stale_delivery(grid, sessions):
    def secondary(m, t, cols):
        with np.errstate(invalid="ignore"):
            return np.nanmean(grid[t - 62 - sessions: t + 1 - sessions, cols], axis=0)
    return secondary


def round_trips(trades):
    """FIFO-free view: pair each symbol's buys and sells into holding spells with net rupee P&L."""
    spells, open_ = [], {}
    for t in trades:
        s = t["symbol"]
        amt = t["qty"] * t["price"]
        o = open_.setdefault(s, {"first": t["day"], "paid": 0.0, "got": 0.0})
        if t["side"] == "BUY":
            o["paid"] += amt + t["charges"]
        else:
            o["got"] += amt - t["charges"]
        o["last"] = t["day"]
    return open_


def main() -> None:
    m = wm.Market(load())
    grid = mv.load_delivery(m)
    v5 = run(m, mv._top30_then(mv.delivery_secondary(grid)))
    base = run(m)
    placebo = [run(m, random_within_top30(s)) for s in range(20)]
    stale = run(m, mv._top30_then(stale_delivery(grid, 5)))

    # holdings spells for V5: buy/sell totals per symbol, sold out completely (closed) or still held
    sim = v5["sim"]
    spells = defaultdict(lambda: {"paid": 0.0, "got": 0.0, "first": None, "last": None})
    for t in sim["trades"]:
        sp = spells[t["symbol"]]
        sp["first"] = sp["first"] or t["day"]
        sp["last"] = t["day"]
        amt = t["qty"] * t["price"]
        if t["side"] == "BUY":
            sp["paid"] += amt + t["charges"]
        else:
            sp["got"] += amt - t["charges"]
    held_value = {h["symbol"]: h["value"] for h in sim["holdings"]}
    pnl = {s: sp["got"] + held_value.get(s, 0.0) - sp["paid"] for s, sp in spells.items()}
    best = sorted(pnl.items(), key=lambda kv: -kv[1])[:10]
    worst = sorted(pnl.items(), key=lambda kv: kv[1])[:10]

    # a worked example: the latest complete month-end in the data
    t = max(k for k in m.members if k < len(m.d) - 1)
    cols = m.members[t]
    mom = mv.ORIGINAL(m, "mom_12_1", t, cols)
    top = cols[np.argsort(-np.nan_to_num(mom, nan=-np.inf))[:30]]
    with np.errstate(invalid="ignore"):
        deliv = np.nanmean(grid[t - 62: t + 1, top], axis=0)
    mom_top = mv.ORIGINAL(m, "mom_12_1", t, top)
    example = sorted(({"symbol": str(m.p.symbols[j]), "mom_12_1": float(mm), "delivery_pct_63d": float(dd), "close": float(m.p.close[t, j])}
                      for j, mm, dd in zip(top, mom_top, deliv)), key=lambda r: -r["mom_12_1"])
    chosen = {r["symbol"] for r in sorted(example, key=lambda r: -(r["delivery_pct_63d"] if np.isfinite(r["delivery_pct_63d"]) else -1))[:10]}

    yearly = defaultdict(lambda: {"start": None, "end": None, "base_start": None, "base_end": None, "bench": 1.0, "nifty": 1.0, "charges": 0.0, "trades": 0})
    for k, t2 in enumerate(v5["ends"]):
        y = yearly[m.d[t2].year]
        y["start"] = v5["values"][k] if y["start"] is None else y["start"]
        y["end"] = v5["values"][k + 1]
        y["base_start"] = base["values"][k] if y["base_start"] is None else y["base_start"]
        y["base_end"] = base["values"][k + 1]
        y["bench"] *= 1 + v5["bench"][k]
        y["nifty"] *= 1 + v5["nifty"][k]
    for tr in sim["trades"]:
        y = yearly[int(tr["day"][:4])]
        y["charges"] += tr["charges"]
        y["trades"] += 1

    report = {
        "v5": {k: v5[k] for k in ("cagr", "dd", "dd_from", "dd_to", "years")} | {"final": v5["values"][-1], "charges": sim["charges"], "trades": len(sim["trades"])},
        "baseline": {k: base[k] for k in ("cagr", "dd", "dd_from", "dd_to")} | {"final": base["values"][-1], "charges": base["sim"]["charges"], "trades": len(base["sim"]["trades"])},
        "benchmark_final": mc.CAPITAL * float(np.prod([1 + b for b in v5["bench"]])),
        "niftybees_final": mc.CAPITAL * float(np.prod([1 + n for n in v5["nifty"]])),
        "placebo_random_10_of_top30": {"cagr": sorted(p["cagr"] for p in placebo), "mean": float(np.mean([p["cagr"] for p in placebo])), "max": float(max(p["cagr"] for p in placebo))},
        "delivery_5_sessions_stale": {"cagr": stale["cagr"], "dd": stale["dd"]},
        "months_v5_beat_baseline": float(np.mean(np.array(v5["monthly"]) > np.array(base["monthly"]))),
        "yearly": {y: v for y, v in sorted(yearly.items())},
        "months": [{"month_end": m.d[t2].isoformat(), "delivery": a, "baseline": b, "benchmark": c, "niftybees": d}
                   for t2, a, b, c, d in zip(v5["ends"], v5["monthly"], base["monthly"], v5["bench"], v5["nifty"])],
        "best_stocks": best, "worst_stocks": worst,
        "example": {"decided_at_close": m.d[t].isoformat(), "top30": example, "chosen": sorted(chosen)},
        "holdings_now": sorted(sim["holdings"], key=lambda h: -h["value"]),
    }
    (OUT / "momentum-delivery-detail.json").write_text(json.dumps(report, indent=1, default=float))
    with (OUT / "momentum-delivery-trades.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["day", "side", "symbol", "qty", "price", "charges", "note"])
        w.writeheader()
        for tr in sim["trades"]:
            w.writerow({k: (round(v, 2) if isinstance(v, float) else v) for k, v in tr.items()})
    print(json.dumps({k: report[k] for k in ("v5", "baseline", "benchmark_final", "niftybees_final", "placebo_random_10_of_top30", "delivery_5_sessions_stale", "months_v5_beat_baseline")}, indent=1, default=float))
    for y, v in report["yearly"].items():
        print(y, f"V5 ₹{v['start']:,.0f} -> ₹{v['end']:,.0f} {v['end']/v['start']-1:+.1%} | base {v['base_end']/v['base_start']-1:+.1%} | bench {v['bench']-1:+.1%} | nifty {v['nifty']-1:+.1%} | charges ₹{v['charges']:,.0f} trades {v['trades']}")
    print("best", [(s, round(x)) for s, x in best])
    print("worst", [(s, round(x)) for s, x in worst])
    print("example", report["example"]["decided_at_close"], [(r["symbol"], round(r["mom_12_1"] * 100), round(r["delivery_pct_63d"], 1), r["symbol"] in chosen) for r in example])
    print("holdings", [(h["symbol"], round(h["weight"] * 100, 1)) for h in report["holdings_now"]])


if __name__ == "__main__":
    main()

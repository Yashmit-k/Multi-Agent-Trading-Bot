"""Audit of the 12-1 momentum backtest (services/quant/docs/momentum-audit.md): one continuous run, exported trade by
trade, and tests built to expose look-ahead or engine bias.

    python -m quant_agents.research.momentum_audit
"""

from __future__ import annotations

import csv
import json
from datetime import date

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research import whole_market as wm
from quant_agents.research.bhavcopy import load

OUT = er.ROOT / "services/quant/docs/results"
START, END = date(2016, 2, 1), date(2026, 10, 27)
ORIGINAL = wm.scores


def _span(m: wm.Market) -> tuple[int, int]:
    return int(np.searchsorted(m.p.days, START.toordinal())), len(m.d) - 1


def run(m: wm.Market, scorer=None, **settings) -> dict[str, object]:
    saved = {k: getattr(wm, k) for k in settings}
    for k, v in settings.items():
        setattr(wm, k, v)
    if scorer is not None:
        wm.scores = scorer
    try:
        lo, hi = _span(m)
        sim = wm.simulate_range(m, "mom_12_1", lo, hi)
        months = wm.monthly(m, sim["marks"], sim["capital"], lo, hi)
        bench = wm.benchmark_months(m, months, lo)
        nifty = wm.asset_months(m, wm.chain_of(m, "NIFTYBEES"), months, lo)
    finally:
        wm.scores = ORIGINAL
        for k, v in saved.items():
            setattr(wm, k, v)
    years = len(months) / 12

    def cagr(xs: list[float]) -> float:
        return float(np.prod([1 + x for x in xs]) ** (1 / years) - 1)

    strat = [x for _, x in months]
    eq = np.cumprod([1 + x for x in strat])
    return {"cagr": cagr(strat), "benchmark_cagr": cagr(bench), "niftybees_cagr": cagr(nifty), "max_drawdown": float(np.max(1 - eq / np.maximum.accumulate(eq))),
            "months": months, "bench": bench, "nifty": nifty, "sim": sim}


def lagged(sessions: int):
    def scorer(m, rule, t, cols):
        return ORIGINAL(m, rule, t - sessions, cols)
    return scorer


def strict_corporate_actions(m, rule, t, cols):
    s = ORIGINAL(m, rule, t, cols)
    flagged = m.event[t - wm.LOOK + 1: t + 1][:, cols].any(axis=0)
    return np.where(flagged, -np.inf, s)


def random_scores(seed: int):
    def scorer(m, rule, t, cols):
        return np.random.default_rng(seed * 100_003 + t).random(len(cols))
    return scorer


def export(m: wm.Market, base: dict[str, object]) -> None:
    sim = base["sim"]
    with (OUT / "momentum-backtest-trades.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["day", "side", "symbol", "qty", "price", "value", "charges", "pnl", "note"])
        w.writeheader()
        for t in sim["trades"]:
            w.writerow({k: (round(v, 2) if isinstance(v, float) else v) for k, v in t.items()})
    with (OUT / "momentum-backtest-monthly.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["month_end", "momentum_net", "equal_weight_liquid500_gross", "niftybees"])
        for (t, s), b, n in zip(base["months"], base["bench"], base["nifty"]):
            w.writerow([m.d[t].isoformat(), round(s, 6), round(b, 6), round(n, 6)])


def main() -> None:
    m = wm.Market(load())
    base = run(m)
    export(m, base)
    sells = [t for t in base["sim"]["trades"] if t["side"] == "SELL"]
    pnl = sorted((float(t["pnl"]) for t in sells), reverse=True)
    total = sum(pnl)
    report: dict[str, object] = {
        "baseline": {k: base[k] for k in ("cagr", "benchmark_cagr", "niftybees_cagr", "max_drawdown")},
        "round_trips": len(sells),
        "win_rate": float(np.mean([p > 0 for p in pnl])),
        "realised_pnl": total,
        "top10_share_of_realised_pnl": float(sum(pnl[:10]) / total),
        "realised_pnl_without_top10": float(total - sum(pnl[:10])),
        "charges": base["sim"]["charges"],
    }
    tests = {
        "signal 1 session stale": run(m, lagged(1)),
        "signal 5 sessions stale": run(m, lagged(5)),
        "signal 21 sessions stale": run(m, lagged(21)),
        "no circuit-lock filter": run(m, LOCK=9.0),
        "skip any stock with a corporate-action day in its look-back": run(m, strict_corporate_actions),
        "slippage 50 bp each way": run(m, SLIP=0.005),
    }
    placebo = [run(m, random_scores(seed)) for seed in range(20)]
    report["tests"] = {name: {k: r[k] for k in ("cagr", "benchmark_cagr", "max_drawdown")} for name, r in tests.items()}
    report["placebo_random_picks"] = {"cagr": [r["cagr"] for r in placebo], "mean": float(np.mean([r["cagr"] for r in placebo])),
                                      "max": float(max(r["cagr"] for r in placebo)), "benchmark_cagr": placebo[0]["benchmark_cagr"]}
    (OUT / "momentum-audit-result.json").write_text(json.dumps(report, indent=1, default=float))
    print(json.dumps(report, indent=1, default=float))


if __name__ == "__main__":
    main()

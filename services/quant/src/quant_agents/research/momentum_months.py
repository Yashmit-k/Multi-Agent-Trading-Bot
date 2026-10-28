"""Month-by-month review of the 12-1 momentum backtest: returns, the holdings that drove each month, and a rule-based
label of why (services/quant/docs/momentum-monthly-review.md). Descriptive only: nothing here is a tested rule.

    python -m quant_agents.research.momentum_months
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research import momentum_audit as ma
from quant_agents.research import whole_market as wm
from quant_agents.research.bhavcopy import load

DOC = er.ROOT / "services/quant/docs/momentum-monthly-review.md"
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def label(strategy: float, bench: float, prior3: float) -> str:
    excess = strategy - bench
    if excess >= 0.03:
        return "leaders kept leading" if bench > -0.03 else "leaders fell less than the market"
    if excess <= -0.03:
        if bench >= 0.05 and prior3 <= -0.05:
            return "momentum crash: rebound led by beaten-down stocks"
        if bench <= -0.03:
            return "leaders fell harder than the market"
        return "leadership rotated away from the leaders"
    return "moved with the market"


def main() -> None:
    m = wm.Market(load())
    base = ma.run(m)
    sim, months, bench, nifty = base["sim"], base["months"], base["bench"], base["nifty"]
    capital = sim["capital"]
    by_day = defaultdict(list)
    for t in sim["trades"]:
        by_day[t["day"]].append(t)
    chains = {str(s): j for j, s in enumerate(m.p.symbols)}
    held: set[str] = set()
    rows = []
    start = int(np.searchsorted(m.p.days, ma.START.toordinal())) - 1
    for k, ((t, s), b, n) in enumerate(zip(months, bench, nifty)):
        for d in range(start + 1, t + 1):  # trades inside the month, applied in order
            for tr in by_day.get(m.d[d].isoformat(), []):
                (held.add if tr["side"] == "BUY" else held.discard)(tr["symbol"])
        names = sorted(held)
        contrib = []
        for name in names:
            j = chains[name]
            r = m.index[t, j] / m.index[start, j] - 1 if not np.isnan(m.p.close[start, j]) else m.index[t, j] / m.index[start + 1, j] - 1
            contrib.append((float(r) * wm.NOTIONAL / capital, name, float(r)))
        contrib.sort(reverse=True)
        prior3 = float(np.prod([1 + x for x in bench[max(0, k - 3): k]]) - 1) if k else 0.0
        rows.append({"month": m.d[t].strftime("%Y-%m"), "momentum": s, "benchmark": b, "niftybees": n, "excess": s - b, "prior3_benchmark": prior3,
                     "best": [(nm, r) for _, nm, r in contrib[:3]], "worst": [(nm, r) for _, nm, r in contrib[-3:][::-1]], "why": label(s, b, prior3)})
        start = t
    write(rows)
    (er.ROOT / "services/quant/docs/results/momentum-monthly-review.json").write_text(json.dumps(rows, indent=1))


def pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:+.{digits}f}%"


def write(rows: list[dict]) -> None:
    years = sorted({r["month"][:4] for r in rows})
    grid = {r["month"]: r for r in rows}
    out = ["# 12-1 momentum backtest: month by month", "",
           "One continuous book, ₹4,00,000, top 20 of the NSE Liquid-500. Net of charges and slippage. Code: `quant_agents/research/momentum_months.py`. "
           "Monthly figures are return on the ₹4,00,000 capital; the year column compounds them. "
           "The \"why\" labels come from a fixed rule (below), not from hindsight judgement. **Everything here is descriptive: no pattern below is a tested trading rule.**", ""]
    for title, key in (("Momentum, net", "momentum"), ("Equal-weight Liquid-500, gross (benchmark)", "benchmark"), ("Momentum minus benchmark", "excess")):
        out += [f"## {title}", "", "| Year | " + " | ".join(MONTHS) + " | Year |", "|---|" + "---|" * 13]
        for y in years:
            cells, total = [], 1.0
            for mo in range(1, 13):
                r = grid.get(f"{y}-{mo:02d}")
                cells.append(pct(r[key]) if r else "")
                if r and key != "excess":
                    total *= 1 + r[key]
            if key == "excess":
                ms = [grid[f"{y}-{mo:02d}"] for mo in range(1, 13) if f"{y}-{mo:02d}" in grid]
                total = np.prod([1 + r["momentum"] for r in ms]) / np.prod([1 + r["benchmark"] for r in ms])
            out.append(f"| {y} | " + " | ".join(cells) + f" | **{pct(total - 1)}** |")
        out.append("")
    counts = defaultdict(lambda: [0, 0.0])
    for r in rows:
        counts[r["why"]][0] += 1
        counts[r["why"]][1] += r["excess"]
    out += ["## Why, summed over all months", "", "| Label | Months | Mean excess per month | Total excess (sum) |", "|---|---|---|---|"]
    for name, (n, total) in sorted(counts.items(), key=lambda kv: -kv[1][1]):
        out.append(f"| {name} | {n} | {pct(total / n)} | {pct(total, 0)} |")
    out += ["", "Label rule: excess ≥ +3 points → *leaders kept leading* (or *fell less than the market* when the benchmark fell ≥ 3%). "
            "Excess ≤ −3 points → *momentum crash* when the benchmark rose ≥ 5% after falling ≥ 5% over the previous 3 months; "
            "*leaders fell harder* when the benchmark fell ≥ 3%; otherwise *leadership rotated away*. Anything else → *moved with the market*.", "",
            "## Every month", "", "| Month | Momentum | Benchmark | Excess | Why | Best holdings | Worst holdings |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        best = ", ".join(f"{n} {pct(x, 0)}" for n, x in r["best"])
        worst = ", ".join(f"{n} {pct(x, 0)}" for n, x in r["worst"])
        out.append(f"| {r['month']} | {pct(r['momentum'])} | {pct(r['benchmark'])} | {pct(r['excess'])} | {r['why']} | {best} | {worst} |")
    DOC.write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

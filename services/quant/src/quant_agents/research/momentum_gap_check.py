"""Momentum live: how often would a limit buy at the decision close + BAND miss at the next open, does missing cost
anything, and does the global-markets composite see it coming? Descriptive, for choosing the live order band
(services/quant/docs/momentum-live-plan.md). No trading rule is tested.

    python -m quant_agents.research.momentum_gap_check
"""

from __future__ import annotations

import json
import math
from datetime import date

import numpy as np
from scipy.stats import spearmanr

from quant_agents.research import exit_rules as er
from quant_agents.research import global_markets as gm
from quant_agents.research import whole_market as wm
from quant_agents.research.bhavcopy import load

OUT = er.ROOT / "services/quant/docs/results/momentum-gap-check.json"
HOLD = 10
BANDS = (0.015, 0.03, 0.05)
PERIODS = {"2016-20": (date(2016, 1, 1), date(2020, 12, 31)), "2021-23": (date(2021, 1, 1), date(2023, 12, 31)), "2024-26": (date(2024, 1, 1), date(2026, 12, 31))}


def composite_by_day() -> dict[date, float]:
    """The global agent's composite (global-markets-result.md), known before 09:15 IST of each NIFTY session."""
    days, _, _ = gm.nifty()
    raw = {name: gm.input_series(name, days) for name in gm.INPUTS}
    raw["asia"] = (raw["nikkei"] + raw["kospi"] + raw["hang_seng"]) / 3
    z = {name: gm.scaled(values) for name, values in raw.items()}
    composite = np.nanmean(np.vstack([z[name] for name in gm.COMPOSITE]), axis=0)
    composite[: gm.WINDOW] = np.nan
    return {d: float(v) for d, v in zip(days, composite) if np.isfinite(v)}


def picks(m, t: int) -> list[int]:
    cols = m.members[t]
    s = wm.scores(m, "mom_12_1", t, cols)
    order = [k for k in np.argsort(-np.nan_to_num(s, nan=-np.inf)) if np.isfinite(s[k])][:HOLD]
    return [int(cols[k]) for k in order]


def run() -> dict[str, object]:
    m = wm.Market(load())
    comp = composite_by_day()
    nifty_chain = wm.chain_of(m, "NIFTYBEES")
    ends = [t for t in sorted(m.members) if m.d[t] >= date(2016, 1, 1) and t + 1 < len(m.d)]
    rows, months, previous = [], [], set()
    for n, t in enumerate(ends):
        top = picks(m, t)
        nxt = ends[n + 1] if n + 1 < len(ends) else len(m.d) - 1
        month_gaps = []
        for j in top:
            close, open_ = m.p.close[t, j], m.p.open[t + 1, j]
            if not (np.isfinite(close) and np.isfinite(open_) and close > 0 and open_ > 0):
                continue
            gap = open_ / close - 1
            if abs(gap) > 0.2:  # a corporate action, not a price move
                continue
            low = m.p.low[t + 1, j]
            # Return of a buy at the open, held to the next month-end close (adjusted index, so splits are handled).
            ret = float(m.index[nxt, j] / m.index[t, j] / (1 + gap) - 1) if np.isfinite(m.index[nxt, j]) and np.isfinite(m.index[t, j]) else math.nan
            rows.append({"decided": m.d[t].isoformat(), "symbol": str(m.p.symbols[j]), "new": j not in previous, "gap": float(gap),
                         "low_vs_close": float(low / close - 1) if np.isfinite(low) else math.nan, "ret": ret})
            month_gaps.append(gap)
        previous = set(top)
        nb = m.p.close[t, nifty_chain], m.p.open[t + 1, nifty_chain]
        months.append({"decided": m.d[t], "trade": m.d[t + 1], "mean_gap": float(np.mean(month_gaps)) if month_gaps else math.nan,
                       "nifty_gap": float(nb[1] / nb[0] - 1) if np.isfinite(nb[0]) and np.isfinite(nb[1]) else math.nan, "composite": comp.get(m.d[t + 1], math.nan)})

    def summary(sel: list[dict]) -> dict[str, object]:
        new = [r for r in sel if r["new"]]
        gaps = np.array([r["gap"] for r in new])
        out: dict[str, object] = {"buys": len(new), "gap_median": float(np.median(gaps)), "gap_mean": float(gaps.mean()),
                                  "share_gap_up_over": {}, "share_never_reached_limit": {}, "missed_vs_filled_month_return": {}, "monthly_drag": {}}
        n_months = len({r["decided"] for r in sel})
        for band in BANDS:
            missed = [r for r in new if r["gap"] > band]
            filled = [r for r in new if r["gap"] <= band]
            out["share_gap_up_over"][band] = len(missed) / len(new)
            out["share_never_reached_limit"][band] = float(np.mean([r["low_vs_close"] > band for r in new if np.isfinite(r["low_vs_close"])]))
            mr = [r["ret"] for r in missed if np.isfinite(r["ret"])]
            fr = [r["ret"] for r in filled if np.isfinite(r["ret"])]
            out["missed_vs_filled_month_return"][band] = [float(np.mean(mr)) if mr else math.nan, float(np.mean(fr)) if fr else math.nan]
            # Each missed buy is a tenth of the book left in cash for the month.
            out["monthly_drag"][band] = float(sum(mr) / HOLD / n_months) if n_months else 0.0
        return out

    by_period = {}
    for label, (lo, hi) in PERIODS.items():
        sel = [r for r in rows if lo.isoformat() <= r["decided"] <= hi.isoformat()]
        by_period[label] = summary(sel)
    mg = np.array([x["mean_gap"] for x in months])
    ng = np.array([x["nifty_gap"] for x in months])
    cp = np.array([x["composite"] for x in months])

    def corr(a, b):
        ok = np.isfinite(a) & np.isfinite(b)
        return [float(spearmanr(a[ok], b[ok])[0]), int(ok.sum())]

    return {"pooled": summary(rows), "by_period": by_period,
            "rebalance_days": {"picks_gap_vs_nifty_gap": corr(mg, ng), "picks_gap_vs_global_composite": corr(mg, cp), "nifty_gap_vs_global_composite": corr(ng, cp)}}


def main() -> None:
    report = run()
    OUT.write_text(json.dumps(report, indent=1, default=str))
    p = report["pooled"]
    print("new buys", p["buys"], "median gap", round(p["gap_median"] * 100, 2), "% mean", round(p["gap_mean"] * 100, 2), "%")
    for band in BANDS:
        print(f"band {band:.1%}: open above {p['share_gap_up_over'][band]:.1%}, never back to limit {p['share_never_reached_limit'][band]:.1%}, "
              f"missed/filled month return {p['missed_vs_filled_month_return'][band][0]:+.2%} / {p['missed_vs_filled_month_return'][band][1]:+.2%}, "
              f"drag {p['monthly_drag'][band]*100:+.3f}%/month")
    for label, s in report["by_period"].items():
        print(label, {f"{b:.1%}": f"{s['share_gap_up_over'][b]:.1%} missed, drag {s['monthly_drag'][b]*100:+.2f}%/m" for b in BANDS})
    print("rebalance days:", report["rebalance_days"])


if __name__ == "__main__":
    main()

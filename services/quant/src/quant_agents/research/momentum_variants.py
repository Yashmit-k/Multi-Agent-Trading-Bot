"""Momentum variants from the literature, per services/quant/docs/momentum-variants-protocol.md. Scored once.

    python -m quant_agents.research.momentum_variants
"""

from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research import momentum_compound as mc
from quant_agents.research import whole_market as wm
from quant_agents.research.bhavcopy import load

K = 5
DELIVERY = er.ROOT / "datasets/research/delivery/raw"
ORIGINAL = wm.scores
PERIODS = {"train": (date(2016, 2, 1), date(2020, 12, 31)), "validate": (date(2021, 1, 1), date(2023, 12, 31)), "test": (date(2024, 1, 1), date(2026, 10, 27))}
DELIVERY_PERIODS = {"train": (date(2020, 2, 1), date(2022, 6, 30)), "validate": (date(2022, 7, 1), date(2024, 6, 30)), "test": (date(2024, 7, 1), date(2026, 10, 27))}


def _zscore(x: np.ndarray) -> np.ndarray:
    ok = np.isfinite(x)
    out = np.full(len(x), np.nan)
    if ok.sum() > 2:
        out[ok] = (x[ok] - x[ok].mean()) / x[ok].std()
    return out


def nse_score(m, rule, t, cols):
    idx = m.index[:, cols]
    vol = np.nanstd(m.r[t - 251: t + 1, cols], axis=0) * math.sqrt(252)
    with np.errstate(invalid="ignore", divide="ignore"):
        r6 = (idx[t] / idx[t - 126] - 1) / vol
        r12 = (idx[t] / idx[t - 252] - 1) / vol
    return (_zscore(r6) + _zscore(r12)) / 2


def mom_12_7(m, rule, t, cols):
    idx = m.index[:, cols]
    return idx[t - 147] / idx[t - 252] - 1


def _top30_then(secondary):
    """Top 30 by 12-1, re-ordered by `secondary` (higher first); the rest follow in 12-1 order as fallbacks."""
    def scorer(m, rule, t, cols):
        mom = ORIGINAL(m, rule, t, cols).astype(float)
        finite = np.where(np.isfinite(mom))[0]
        top = finite[np.argsort(-mom[finite])[:30]]
        sec = secondary(m, t, cols[top])
        sec = np.where(np.isfinite(sec), sec, -1e12)
        out = np.where(np.isfinite(mom), mom, -np.inf)  # fallbacks keep their 12-1 score (always < 1e6)
        order = np.argsort(-sec)
        out[top[order]] = 1e6 + np.arange(len(top))[::-1]
        return out
    return scorer


def low_volume_ratio(m, t, cols):
    qty = m.p.value[t - 251: t + 1, cols].astype(float) / m.p.close[t - 251: t + 1, cols].astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return -(np.nanmean(qty[-63:], axis=0) / np.nanmean(qty, axis=0))


def load_delivery(m, folder: Path | None = None) -> np.ndarray:
    """Delivery % on the panel grid (NaN where missing), matched by symbol and checked against that day's close."""
    p = m.p
    grid = np.full(p.close.shape, np.nan, dtype=np.float32)
    by_symbol: dict[str, list[int]] = {}
    for j, s in enumerate(p.symbols):
        by_symbol.setdefault(str(s), []).append(j)
    day_index = {int(d): k for k, d in enumerate(p.days)}
    matched = unmatched = 0
    for path in sorted(Path(folder or DELIVERY).glob("*.csv")):
        k = day_index.get(date.fromisoformat(path.stem).toordinal())
        if k is None:
            continue
        closes = {}
        for j in np.where(p.series[k] == 1)[0]:
            closes.setdefault(round(float(p.close[k, j]), 2), []).append(int(j))
        with path.open(newline="") as f:
            for row in csv.DictReader(f, skipinitialspace=True):
                if (row.get("SERIES") or "").strip() != "EQ":
                    continue
                try:
                    close, deliv = float(row["CLOSE_PRICE"]), float(row["DELIV_PER"])
                except (KeyError, ValueError):
                    continue
                cands = [j for j in by_symbol.get(row["SYMBOL"].strip(), []) if round(float(p.close[k, j]), 2) == round(close, 2)]
                if not cands:
                    same = closes.get(round(close, 2), [])
                    cands = same if len(same) == 1 else []
                if len(cands) == 1:
                    grid[k, cands[0]] = deliv
                    matched += 1
                else:
                    unmatched += 1
    print(f"delivery rows matched {matched:,}, unmatched {unmatched:,}", flush=True)
    return grid


def delivery_secondary(grid):
    def secondary(m, t, cols):
        with np.errstate(invalid="ignore"):
            return np.nanmean(grid[t - 62: t + 1, cols], axis=0)
    return secondary


def factor_park(m):
    """NIFTYBEES when the momentum factor's trailing 12 months (from completed months only) are <= 0."""
    nifty = wm.chain_of(m, "NIFTYBEES")
    ends = sorted(m.members)
    fwd = {}
    for a, b in zip(ends, ends[1:]):
        cols = m.members[a]
        s = ORIGINAL(m, "mom_12_1", a, cols)
        top = cols[np.argsort(-np.nan_to_num(s, nan=-np.inf))[:mc.HOLD]]
        fwd[b] = float(np.nanmean(m.index[b, top] / m.index[a, top] - 1))  # known at the close of b
    state = {}

    def park(t):
        past = [v for e, v in fwd.items() if e <= t][-12:]
        off = len(past) == 12 and np.prod([1 + v for v in past]) - 1 <= 0
        state[m.d[t].isoformat()] = bool(off)
        return nifty if off else None
    park.state = state  # type: ignore[attr-defined]
    return park


def book(m, start, end, scorer=None, park=None) -> dict[str, object]:
    if scorer is not None:
        wm.scores = scorer
    try:
        sim = mc.simulate(m, start=start, end=end, fill_leftover=True, park=park)
    finally:
        wm.scores = ORIGINAL
    lo, hi, marks = sim["lo"], sim["hi"], sim["marks"]
    ends = [t for t in m.month_ends if lo <= t <= hi] + ([hi] if hi not in m.month_ends else [])
    values = [mc.CAPITAL] + [marks[t] for t in ends]
    bench = wm.benchmark_months(m, [(t, 0.0) for t in ends], lo)
    years = (m.p.days[hi] - m.p.days[lo - 1]) / 365.25
    eq = np.array(values)
    return {"monthly": [values[k + 1] / values[k] - 1 for k in range(len(ends))], "final": float(values[-1]),
            "cagr": float((values[-1] / mc.CAPITAL) ** (1 / years) - 1), "benchmark_cagr": float(np.prod([1 + b for b in bench]) ** (1 / years) - 1),
            "max_drawdown": float(np.max(1 - eq / np.maximum.accumulate(eq))), "charges": float(sim["charges"]), "trades": len(sim["trades"])}


def gate(base: dict, var: dict, periods) -> dict[str, object]:
    beats = {k: bool(var[k]["cagr"] > base[k]["cagr"]) for k in periods}
    bench = {k: bool(var[k]["cagr"] > var[k]["benchmark_cagr"]) for k in periods}
    diff = np.array([a - b for k in periods for a, b in zip(var[k]["monthly"], base[k]["monthly"])])
    rng = np.random.default_rng(0)
    low = float(np.quantile(diff[rng.integers(0, len(diff), size=(2000, len(diff)))].mean(axis=1), 0.10 / K))
    return {"beats_baseline": beats, "beats_benchmark": bench, "mean_monthly_diff": float(diff.mean()),
            "t_stat": float(diff.mean() / (diff.std(ddof=1) / math.sqrt(len(diff)))), "bonferroni_low": low,
            "improves": bool(all(beats.values()) and all(bench.values()) and low > 0)}


def strip(r: dict) -> dict:
    return {k: v for k, v in r.items() if k != "monthly"}


def main() -> None:
    m = wm.Market(load())
    report: dict[str, object] = {"protocol": "services/quant/docs/momentum-variants-protocol.md"}
    base = {k: book(m, a, b) for k, (a, b) in PERIODS.items()}
    variants = {"nse_score": (nse_score, None), "mom_12_7": (mom_12_7, None), "factor_timing": (None, "park"), "low_volume": (_top30_then(low_volume_ratio), None)}
    report["baseline"] = {k: strip(v) for k, v in base.items()}
    for name, (scorer, park) in variants.items():
        per = {}
        for k, (a, b) in PERIODS.items():
            per[k] = book(m, a, b, scorer, factor_park(m) if park else None)
        report[name] = {"periods": {k: strip(v) for k, v in per.items()}, "gate": gate(base, per, PERIODS)}
    grid = load_delivery(m)
    base_d = {k: book(m, a, b) for k, (a, b) in DELIVERY_PERIODS.items()}
    per = {k: book(m, a, b, _top30_then(delivery_secondary(grid))) for k, (a, b) in DELIVERY_PERIODS.items()}
    report["delivery"] = {"baseline": {k: strip(v) for k, v in base_d.items()}, "periods": {k: strip(v) for k, v in per.items()}, "gate": gate(base_d, per, DELIVERY_PERIODS)}
    # continuous books (reported, not gated)
    cont = {"baseline": book(m, date(2016, 2, 1), None)}
    for name, (scorer, park) in variants.items():
        cont[name] = book(m, date(2016, 2, 1), None, scorer, factor_park(m) if park else None)
    report["continuous"] = {k: strip(v) for k, v in cont.items()}
    (er.ROOT / "services/quant/docs/results/momentum-variants-result.json").write_text(json.dumps(report, indent=1, default=float))

    def line(name, per, basep):
        cells = "  ".join(f"{k} {v['cagr']:+.1%} (base {basep[k]['cagr']:+.1%}, bm {v['benchmark_cagr']:+.1%}, dd {v['max_drawdown']:.0%})" for k, v in per.items())
        print(f"{name:14} {cells}")

    for name in variants:
        line(name, report[name]["periods"], report["baseline"])
        g = report[name]["gate"]
        print(f"{'':14} gate {g['beats_baseline']} diff {g['mean_monthly_diff']*100:+.2f}%/m t {g['t_stat']:.2f} low {g['bonferroni_low']*100:+.2f}% -> {'IMPROVES' if g['improves'] else 'no'}")
    line("delivery", report["delivery"]["periods"], report["delivery"]["baseline"])
    g = report["delivery"]["gate"]
    print(f"{'':14} gate {g['beats_baseline']} diff {g['mean_monthly_diff']*100:+.2f}%/m t {g['t_stat']:.2f} low {g['bonferroni_low']*100:+.2f}% -> {'IMPROVES' if g['improves'] else 'no'}")
    for name, v in report["continuous"].items():
        print(f"continuous {name:14} ₹{v['final']:,.0f}  CAGR {v['cagr']:+.1%}  dd {v['max_drawdown']:.0%}  charges ₹{v['charges']:,.0f}")


if __name__ == "__main__":
    main()

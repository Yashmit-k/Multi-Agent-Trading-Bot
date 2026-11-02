"""Trend, volume and options signals, per services/quant/docs/trend-volume-options-protocol.md. Scored once.

    python -m quant_agents.research.trend_volume_options batch1
    python -m quant_agents.research.trend_volume_options batch2
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research import momentum_variants as mv
from quant_agents.research import whole_market as wm
from quant_agents.research.bhavcopy import load

OUT = er.ROOT / "services/quant/docs/results/trend-volume-options-result.json"
BATCH1_PERIODS = {"train": (date(2017, 1, 1), date(2020, 12, 31)), "validate": (date(2021, 1, 1), date(2023, 12, 31)), "test": (date(2024, 1, 1), date(2026, 10, 27))}
LAGS = (3, 5, 10, 20, 50, 100, 200)


def _ma(m, t, cols, n):
    return np.nanmean(m.index[t - n + 1: t + 1, cols], axis=0)


def ma_distance(m, rule, t, cols):
    return _ma(m, t, cols, 21) / _ma(m, t, cols, 200)


def high_volume(m, rule, t, cols):
    qty = m.p.value[t - 49: t + 1, cols].astype(float) / m.p.close[t - 49: t + 1, cols].astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.nanmean(qty[-5:], axis=0) / np.nanmean(qty[:-5], axis=0)


class TrendFactor:
    """Han, Zhou & Zhu (2016): MA/price signals combined with the mean of the last 12 monthly cross-sectional betas."""

    def __init__(self, m) -> None:
        self.m = m
        self.ends = sorted(t for t in m.members if t >= max(LAGS))
        self.beta: dict[int, np.ndarray] = {}  # month-end at which the return month finished -> coefficients
        for a, b in zip(self.ends, self.ends[1:]):
            cols = m.members[a]
            x = self.signals(a, cols)
            y = m.index[b, cols] / m.index[a, cols] - 1
            ok = np.isfinite(x).all(axis=1) & np.isfinite(y)
            if ok.sum() < 50:
                continue
            design = np.column_stack([np.ones(ok.sum()), x[ok]])
            self.beta[b] = np.linalg.lstsq(design, y[ok], rcond=None)[0]

    def signals(self, t, cols):
        price = self.m.index[t, cols]
        return np.column_stack([_ma(self.m, t, cols, n) / price for n in LAGS])

    def __call__(self, m, rule, t, cols):
        past = [v for e, v in self.beta.items() if e <= t][-12:]
        if len(past) < 12:
            return np.full(len(cols), np.nan)
        coef = np.mean(past, axis=0)
        x = self.signals(t, cols)
        return coef[0] + x @ coef[1:]


def strip(r):
    return {k: v for k, v in r.items() if k != "monthly"}


def batch1() -> dict[str, object]:
    m = wm.Market(load())
    base = {k: mv.book(m, a, b) for k, (a, b) in BATCH1_PERIODS.items()}
    signals = {"trend_factor": TrendFactor(m), "ma_distance": ma_distance, "high_volume": high_volume}
    out: dict[str, object] = {"baseline": {k: strip(v) for k, v in base.items()}}
    for name, scorer in signals.items():
        per = {k: mv.book(m, a, b, scorer) for k, (a, b) in BATCH1_PERIODS.items()}
        out[name] = {"periods": {k: strip(v) for k, v in per.items()}, "gate": mv.gate(base, per, BATCH1_PERIODS)}
        cont = mv.book(m, date(2017, 1, 1), None, scorer)
        out[name]["continuous_2017"] = strip(cont)
    out["baseline_continuous_2017"] = strip(mv.book(m, date(2017, 1, 1), None))
    return out


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "batch1"
    report = json.loads(OUT.read_text()) if OUT.exists() else {"protocol": "services/quant/docs/trend-volume-options-protocol.md"}
    if which == "batch1":
        report["batch1"] = batch1()
        r = report["batch1"]
        for name in ("trend_factor", "ma_distance", "high_volume"):
            cells = "  ".join(f"{k} {v['cagr']:+.1%} (base {r['baseline'][k]['cagr']:+.1%}, bm {v['benchmark_cagr']:+.1%}, dd {v['max_drawdown']:.0%})" for k, v in r[name]["periods"].items())
            g = r[name]["gate"]
            c = r[name]["continuous_2017"]
            print(f"{name:13} {cells}")
            print(f"{'':13} gate {g['beats_baseline']} diff {g['mean_monthly_diff']*100:+.2f}%/m t {g['t_stat']:.2f} low {g['bonferroni_low']*100:+.2f}% -> {'IMPROVES' if g['improves'] else 'no'} | 2017-> ₹{c['final']:,.0f} {c['cagr']:+.1%} dd {c['max_drawdown']:.0%}")
        b = r["baseline_continuous_2017"]
        print(f"baseline 2017-> ₹{b['final']:,.0f} {b['cagr']:+.1%} dd {b['max_drawdown']:.0%}")
    else:
        from quant_agents.research import options_signals

        report["batch2"] = options_signals.batch2()
    OUT.write_text(json.dumps(report, indent=1, default=float))


if __name__ == "__main__":
    main()

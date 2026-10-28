"""12-1 momentum improvements, per services/quant/docs/momentum-improvements-protocol.md. Scored once.

    python -m quant_agents.research.momentum_improvements
"""

from __future__ import annotations

import json
import math

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research import momentum_audit as ma
from quant_agents.research import whole_market as wm
from quant_agents.research.bhavcopy import load

K = 4
ORIGINAL = wm.scores


def skip_top(n: int):
    def scorer(m, rule, t, cols):
        s = ORIGINAL(m, rule, t, cols).astype(float)
        finite = np.where(np.isfinite(s))[0]
        top = finite[np.argsort(-s[finite])[:n]]
        s[top] = -np.inf
        return s
    return scorer


VARIANTS = {
    "baseline": ({}, None),
    "buffer40": ({"BUFFER": 40}, None),
    "hold30": ({"HOLD": 30, "BUFFER": 30}, None),
    "skip_top5pct": ({}, skip_top(25)),
    "buffer40_hold30": ({"HOLD": 30, "BUFFER": 40}, None),
}


def periods(m: wm.Market, settings: dict, scorer) -> dict[str, dict[str, object]]:
    saved = {k: getattr(wm, k) for k in settings}
    for k, v in settings.items():
        setattr(wm, k, v)
    if scorer is not None:
        wm.scores = scorer
    out = {}
    try:
        for label in wm.PERIODS:
            sim = wm.simulate_stocks(m, "mom_12_1", label)
            months = wm.monthly(m, sim["marks"], sim["capital"], sim["lo"], sim["hi"])
            strat = [x for _, x in months]
            bench = wm.benchmark_months(m, months, sim["lo"])
            out[label] = {"monthly": strat, "annual": float(np.mean(strat) * 12), "benchmark_annual": float(np.mean(bench) * 12), "charges": sim["charges"], "buys": sim["buys"]}
    finally:
        wm.scores = ORIGINAL
        for k, v in saved.items():
            setattr(wm, k, v)
    return out


def boot(values: list[float], q: float) -> float:
    arr = np.array(values)
    rng = np.random.default_rng(0)
    return float(np.quantile(arr[rng.integers(0, len(arr), size=(2000, len(arr)))].mean(axis=1), q))


def main() -> None:
    m = wm.Market(load())
    report: dict[str, object] = {"protocol": "services/quant/docs/momentum-improvements-protocol.md"}
    per = {name: periods(m, settings, scorer) for name, (settings, scorer) in VARIANTS.items()}
    for name, (settings, scorer) in VARIANTS.items():
        saved = {k: getattr(wm, k) for k in settings}
        for k, v in settings.items():
            setattr(wm, k, v)
        try:
            cont = ma.run(m, scorer)
        finally:
            for k, v in saved.items():
                setattr(wm, k, v)
        report[name] = {"periods": {k: {a: b for a, b in v.items() if a != "monthly"} for k, v in per[name].items()},
                        "continuous": {k: cont[k] for k in ("cagr", "benchmark_cagr", "max_drawdown")}, "continuous_charges": cont["sim"]["charges"], "continuous_buys": cont["sim"]["buys"]}
    gate = {}
    for name in VARIANTS:
        if name == "baseline":
            continue
        beats = {k: bool(per[name][k]["annual"] > per["baseline"][k]["annual"]) for k in wm.PERIODS}
        bench = {k: bool(per[name][k]["annual"] > per[name][k]["benchmark_annual"]) for k in wm.PERIODS}
        diff = [a - b for k in wm.PERIODS for a, b in zip(per[name][k]["monthly"], per["baseline"][k]["monthly"])]
        low = boot(diff, 0.10 / K)
        t = float(np.mean(diff) / (np.std(diff, ddof=1) / math.sqrt(len(diff))))
        gate[name] = {"beats_baseline": beats, "beats_benchmark": bench, "mean_monthly_vs_baseline": float(np.mean(diff)), "t_stat": t, "bonferroni_low": low,
                      "improves": bool(all(beats.values()) and all(bench.values()) and low > 0)}
    report["gate"] = gate
    (er.ROOT / "services/quant/docs/results/momentum-improvements-result.json").write_text(json.dumps(report, indent=1, default=float))
    for name in VARIANTS:
        r = report[name]
        cells = "  ".join(f"{k} {v['annual']:+.1%} (bm {v['benchmark_annual']:+.1%}, buys {v['buys']}, charges {v['charges']:,.0f})" for k, v in r["periods"].items())
        c = r["continuous"]
        print(f"{name:16} {cells}  | continuous CAGR {c['cagr']:+.1%} dd {c['max_drawdown']:.0%} charges {r['continuous_charges']:,.0f}")
    print(json.dumps(gate, indent=1))


if __name__ == "__main__":
    main()

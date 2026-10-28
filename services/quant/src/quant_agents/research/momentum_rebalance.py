"""Equal split every month vs new buys only, per services/quant/docs/momentum-rebalance-protocol.md. Scored once.

    python -m quant_agents.research.momentum_rebalance
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np

from quant_agents.research import exit_rules as er
from quant_agents.research import momentum_audit as ma
from quant_agents.research import momentum_compound as mc
from quant_agents.research import whole_market as wm
from quant_agents.research.bhavcopy import load

PERIODS = {"train": (date(2016, 2, 1), date(2020, 12, 31)), "validate": (date(2021, 1, 1), date(2023, 12, 31)), "test": (date(2024, 1, 1), date(2026, 10, 27))}


def book(m: wm.Market, equal_split: bool, start: date, end: date) -> dict[str, object]:
    sim = mc.simulate(m, rebalance_holdings=equal_split, start=start, end=end)
    lo, hi, marks = sim["lo"], sim["hi"], sim["marks"]
    ends = [t for t in m.month_ends if lo <= t <= hi] + ([hi] if hi not in m.month_ends else [])
    values = [mc.CAPITAL] + [marks[t] for t in ends]
    monthly = [values[k + 1] / values[k] - 1 for k in range(len(ends))]
    bench = wm.benchmark_months(m, [(t, 0.0) for t in ends], lo)
    years = (m.p.days[hi] - m.p.days[lo - 1]) / 365.25
    eq = np.array(values)
    return {"monthly": monthly, "cagr": float((values[-1] / mc.CAPITAL) ** (1 / years) - 1), "final": float(values[-1]),
            "benchmark_cagr": float(np.prod([1 + b for b in bench]) ** (1 / years) - 1),
            "max_drawdown": float(np.max(1 - eq / np.maximum.accumulate(eq))), "charges": float(sim["charges"]), "trades": len(sim["trades"])}


def compare(m: wm.Market) -> dict[str, object]:
    out: dict[str, object] = {}
    diff: list[float] = []
    for label, (a, b) in PERIODS.items():
        A, B = book(m, True, a, b), book(m, False, a, b)
        diff += [x - y for x, y in zip(B["monthly"], A["monthly"])]
        out[label] = {"equal_split": {k: v for k, v in A.items() if k != "monthly"}, "new_buys_only": {k: v for k, v in B.items() if k != "monthly"}}
    arr = np.array(diff)
    rng = np.random.default_rng(0)
    low = float(np.quantile(arr[rng.integers(0, len(arr), size=(2000, len(arr)))].mean(axis=1), 0.10))
    beats = {k: bool(v["new_buys_only"]["cagr"] > v["equal_split"]["cagr"]) for k, v in out.items()}
    bench = {k: bool(v["new_buys_only"]["cagr"] > v["new_buys_only"]["benchmark_cagr"]) for k, v in out.items()}
    out["gate"] = {"b_beats_a": beats, "b_beats_benchmark": bench, "mean_monthly_b_minus_a": float(arr.mean()),
                   "t_stat": float(arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr)))), "boot_low_10": low,
                   "b_better": bool(all(beats.values()) and all(bench.values()) and low > 0)}
    return out


def main() -> None:
    m = wm.Market(load())
    report = {"protocol": "services/quant/docs/momentum-rebalance-protocol.md", "registered": compare(m)}
    wm.scores = ma.lagged(1)
    report["stale_signal_1_session"] = compare(m)
    wm.scores = ma.ORIGINAL
    saved, wm.SLIP = wm.SLIP, 0.003
    report["slippage_30bp"] = compare(m)
    wm.SLIP = saved
    (er.ROOT / "services/quant/docs/results/momentum-rebalance-result.json").write_text(json.dumps(report, indent=1, default=float))
    for name, part in report.items():
        if name == "protocol":
            continue
        print(name)
        for label in PERIODS:
            a, b = part[label]["equal_split"], part[label]["new_buys_only"]
            print(f"  {label:8} A equal split {a['cagr']:+.1%} (dd {a['max_drawdown']:.0%}, ₹{a['charges']:,.0f}, {a['trades']} trades)   "
                  f"B new buys only {b['cagr']:+.1%} (dd {b['max_drawdown']:.0%}, ₹{b['charges']:,.0f}, {b['trades']} trades)   benchmark {b['benchmark_cagr']:+.1%}")
        g = part["gate"]
        print(f"  gate: B beats A {g['b_beats_a']}  B beats benchmark {g['b_beats_benchmark']}  mean B-A {g['mean_monthly_b_minus_a']*100:+.2f}%/month  t {g['t_stat']:.2f}  10th pct {g['boot_low_10']*100:+.2f}%  -> {'B better' if g['b_better'] else 'not shown better'}")


if __name__ == "__main__":
    main()

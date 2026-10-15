"""Risk-based sizing, scored per services/quant/docs/risk-sizing-protocol.md.

Uses study 3's walk-forward volatility model unchanged: weights proportional to
1 - P(high volatility over the next 10 sessions), against equal weights, for three books.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from quant_agents.research import ml_combined as mc
from quant_agents.research import ml_ensemble as me
from quant_agents.research.ml_rank import load_panel

H = mc.H


def position_returns(panel, t: int, symbols: list[int]) -> dict[int, float]:
    out: dict[int, float] = {}
    for j in symbols:
        a, b = panel.open[t + 1, j], panel.open[t + 1 + H, j]
        if math.isnan(a) or math.isnan(b):
            continue
        result = me.trade_net(float(a), float(b))
        if result is not None:
            out[j] = result[0] / result[1]
    return out


def weighted(returns: dict[int, float], weights: dict[int, float]) -> float:
    total = sum(weights[j] for j in returns)
    return sum(returns[j] * weights[j] for j in returns) / total if total > 0 else 0.0


def stats(values: list[float]) -> dict[str, float]:
    arr = np.asarray(values)
    per_year = 250 / H
    curve = np.cumprod(1 + arr)
    std = float(arr.std(ddof=1))
    return {
        "windows": len(arr),
        "annualized_net": float(arr.mean() * per_year),
        "annualized_vol": float(std * math.sqrt(per_year)),
        "sharpe": float(arr.mean() / std * math.sqrt(per_year)) if std > 0 else float("nan"),
        "max_drawdown": float(np.max(1 - curve / np.maximum.accumulate(curve))),
        "total_compounded": float(curve[-1] - 1),
    }


def sharpe_improvement_bounds(risk: list[float], equal: list[float], *, resamples: int = 2000, seed: int = 0) -> tuple[float, float]:
    """90% bounds on annualized Sharpe(risk) - Sharpe(equal), resampling windows jointly."""
    r, e = np.asarray(risk), np.asarray(equal)
    n = len(r)
    rng = np.random.default_rng(seed)
    per_year = math.sqrt(250 / H)
    diffs = np.empty(resamples)
    for k in range(resamples):
        idx = me.stationary_bootstrap_indices(n, 4.0, rng)
        rs, es = r[idx], e[idx]
        diffs[k] = (rs.mean() / rs.std(ddof=1) - es.mean() / es.std(ddof=1)) * per_year
    return float(np.quantile(diffs, 0.05)), float(np.quantile(diffs, 0.95))


def run(stock: Path, context_path: Path, intraday_path: Path, cache: Path | None = None) -> dict[str, object]:
    panel = load_panel(stock)
    context = me.load_context(context_path, panel.dates)
    intraday = mc.load_intraday(intraday_path, panel.symbols, panel.dates, cache)
    design = mc.build_design(panel, context, intraday)
    T = len(panel.dates)
    start = me.FEATURE_START + mc.MIN_TRAIN_SESSIONS + mc.EMBARGO + (1 + H) + mc.REFIT_EVERY
    last = T - 2 - H
    proba = mc.walk_forward_proba(design.X, mc.volatility_labels(panel), start, last)
    momentum = design.X[:, :, design.names.index("ret_20_rank")]
    books: dict[str, dict[str, list[float]]] = {name: {"equal": [], "risk": []} for name in ("all_stocks", "momentum_top6", "model_calm24")}
    for t in range(start, last + 1, H):
        eligible = [j for j in range(len(panel.symbols)) if not math.isnan(proba[t, j])]
        if len(eligible) < 24:
            continue
        picks = {
            "all_stocks": eligible,
            "momentum_top6": sorted([j for j in eligible if not math.isnan(momentum[t, j])], key=lambda j: momentum[t, j], reverse=True)[:6],
            "model_calm24": sorted(eligible, key=lambda j: proba[t, j])[:24],
        }
        for name, chosen in picks.items():
            returns = position_returns(panel, t, chosen)
            if not returns:
                continue
            books[name]["equal"].append(weighted(returns, {j: 1.0 for j in returns}))
            books[name]["risk"].append(weighted(returns, {j: max(1e-6, 1.0 - float(proba[t, j])) for j in returns}))
    report: dict[str, object] = {"protocol": "services/quant/docs/risk-sizing-protocol.md", "period": {"first": panel.dates[start].isoformat(), "last": panel.dates[last].isoformat()}, "books": {}}
    for name, series in books.items():
        equal, risk = stats(series["equal"]), stats(series["risk"])
        bounds = sharpe_improvement_bounds(series["risk"], series["equal"])
        helps = risk["annualized_vol"] < equal["annualized_vol"] and risk["max_drawdown"] <= equal["max_drawdown"] and bounds[0] > -0.05
        report["books"][name] = {  # type: ignore[index]
            "equal": equal,
            "risk": risk,
            "sharpe_improvement_90": bounds,
            "risk_sizing_helps": bool(helps),
            "risk_weighted_profitable": risk["annualized_net"] > 0,
        }
    return report

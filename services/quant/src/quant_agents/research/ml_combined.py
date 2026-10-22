"""Combined-hypothesis model, scored per services/quant/docs/ml-combined-protocol.md.

One logistic model per target, fed every hypothesis family: trend, reversal,
risk, volume, intraday microstructure from 5-minute bars, sector, market
regime, calendar. Target A is return direction; target B is next-period
volatility. Return edges are judged by the Deflated Sharpe Ratio over every
trial run in this repo; risk edges by a paired bootstrap against persistence.
"""

from __future__ import annotations

import json
import math
import warnings
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from quant_agents.research import ml_ensemble as me
from quant_agents.research.ml_rank import Panel, _rank, _shift, load_panel

IST = ZoneInfo("Asia/Kolkata")
H = 10
TOP_K = 6
REFIT_EVERY = 21
EMBARGO = 10
MIN_TRAIN_SESSIONS = 120
FIRST_HOUR_END = time(10, 15)
LAST_HOUR_START = time(14, 30)
SESSION_END = time(15, 30)
PRIOR_TRIALS = 46
INTRADAY_NAMES = ("first_hour_ret", "last_hour_ret", "intraday_rv", "vwap_dist", "last_hour_vol_share")


# --- intraday aggregation -------------------------------------------------------------------------

@dataclass
class _Day:
    open: float | None = None
    close: float | None = None
    close_first_hour: float | None = None
    close_before_last_hour: float | None = None
    sum_sq: float = 0.0
    sum_pv: float = 0.0
    sum_v: float = 0.0
    last_hour_v: float = 0.0


def intraday_daily(lines, symbols: list[str], dates: list[date]) -> dict[str, np.ndarray]:
    """Daily intraday features [T, N] from 5-minute bar JSON lines, in time order per symbol.

    Each value for session d uses only that session's bars (all end by 15:30 IST on d).
    """
    sym_index = {symbol: j for j, symbol in enumerate(symbols)}
    day_index = {day: i for i, day in enumerate(dates)}
    days: dict[tuple[int, int], _Day] = {}
    for line in lines:
        bar = json.loads(line) if isinstance(line, (str, bytes)) else line
        j = sym_index.get(bar["symbol"])
        if j is None:
            continue
        end = datetime.fromisoformat(bar["end"]).astimezone(IST)
        i = day_index.get(end.date())
        if i is None:
            continue
        o, c, h, low, v = float(bar["open"]), float(bar["close"]), float(bar["high"]), float(bar["low"]), float(bar["volume"])
        state = days.setdefault((i, j), _Day())
        if state.open is None:
            state.open = o
        elif state.close is not None and state.close > 0 and c > 0:
            state.sum_sq += math.log(c / state.close) ** 2
        clock = end.time()
        if clock <= FIRST_HOUR_END:
            state.close_first_hour = c
        if clock <= LAST_HOUR_START:
            state.close_before_last_hour = c
        else:
            state.last_hour_v += v
        state.close = c
        state.sum_pv += (h + low + c) / 3 * v
        state.sum_v += v
    out = {name: np.full((len(dates), len(symbols)), np.nan) for name in INTRADAY_NAMES}
    for (i, j), s in days.items():
        if s.open and s.close_first_hour:
            out["first_hour_ret"][i, j] = s.close_first_hour / s.open - 1
        if s.close and s.close_before_last_hour:
            out["last_hour_ret"][i, j] = s.close / s.close_before_last_hour - 1
        out["intraday_rv"][i, j] = math.sqrt(s.sum_sq)
        if s.sum_v > 0 and s.close:
            out["vwap_dist"][i, j] = s.close / (s.sum_pv / s.sum_v) - 1
            out["last_hour_vol_share"][i, j] = s.last_hour_v / s.sum_v
    return out


def load_intraday(path: Path, symbols: list[str], dates: list[date], cache: Path | None = None) -> dict[str, np.ndarray]:
    if cache is not None and cache.exists():
        data = np.load(cache)
        return {name: data[name] for name in INTRADAY_NAMES}
    with path.open() as handle:
        result = intraday_daily(handle, symbols, dates)
    if cache is not None:
        np.savez_compressed(cache, **result)
    return result


# --- features and labels --------------------------------------------------------------------------

@dataclass
class Design:
    X: np.ndarray  # [T, N, F]
    names: list[str]
    vol_rank: np.ndarray  # [T, N] 20-session volatility rank (persistence baseline)
    trend_up: np.ndarray
    vix_high: np.ndarray


def build_design(panel: Panel, context: dict[str, np.ndarray], intraday: dict[str, np.ndarray]) -> Design:
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    base = me.build(panel, context)
    keep = [k for k, name in enumerate(base.stock_names) if name.endswith("_rank")]
    names = [base.stock_names[k] for k in keep]
    layers = [base.stock[:, :, k] for k in keep]
    c, o, h, low = panel.close, panel.open, panel.high, panel.low
    with np.errstate(all="ignore"):
        extra = {
            "clv": (c - low) / (h - low),
            "open_to_close": c / o - 1,
            **intraday,
        }
        ret5 = c / _shift(c, 5) - 1
        sector5 = np.full_like(c, np.nan)
        for j, symbol in enumerate(panel.symbols):
            sector = me.SECTOR_OF.get(symbol)
            if sector and sector in context:
                series = context[sector]
                sector5[:, j] = series / _shift(series[:, None], 5)[:, 0] - 1
        extra["rel_sector_5"] = ret5 - sector5
    for name, values in extra.items():
        names.append(f"{name}_rank")
        layers.append(_rank(values))
    T, N = c.shape
    market_idx = [base.stock_names.index(name) for name in base.market_names]
    for k, name in zip(market_idx, base.market_names):
        names.append(name)
        layers.append(base.stock[:, :, k])
    weekday = np.array([day.weekday() for day in panel.dates], dtype=float)
    to_month_end = np.zeros(T)
    for t in range(T):
        month = panel.dates[t].month
        to_month_end[t] = sum(1 for u in range(t + 1, min(T, t + 30)) if panel.dates[u].month == month)
    for name, values in (("weekday", weekday), ("sessions_to_month_end", to_month_end)):
        names.append(name)
        layers.append(np.repeat(values[:, None], N, axis=1))
    vol_rank = base.stock[:, :, base.stock_names.index("vol_20_rank")]
    return Design(np.stack(layers, axis=2), names, vol_rank, base.nifty_trend_up, base.vix_high)


def direction_labels(panel: Panel) -> np.ndarray:
    o = panel.open
    fwd = np.full_like(o, np.nan)
    for t in range(o.shape[0] - 1 - H):
        fwd[t] = o[t + 1 + H] / o[t + 1] - 1
    with np.errstate(all="ignore"):
        med = np.nanmedian(fwd, axis=1, keepdims=True)
    out = np.where(np.isnan(fwd), np.nan, (fwd > med).astype(float))
    return out


def volatility_labels(panel: Panel) -> np.ndarray:
    c = panel.close
    with np.errstate(all="ignore"):
        daily = c / _shift(c, 1) - 1
    T = c.shape[0]
    rv = np.full_like(c, np.nan)
    for t in range(T - H):
        with np.errstate(all="ignore"):
            rv[t] = np.nanstd(daily[t + 1 : t + 1 + H], axis=0)
    with np.errstate(all="ignore"):
        med = np.nanmedian(rv, axis=1, keepdims=True)
    return np.where(np.isnan(rv), np.nan, (rv > med).astype(float))


# --- model ----------------------------------------------------------------------------------------

def make_model():
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.1, max_iter=1000))


def walk_forward_proba(X: np.ndarray, y: np.ndarray, first: int, last: int, feature_start: int = me.FEATURE_START) -> np.ndarray:
    """P(y=1) for rows first..last. A fit at row t uses label rows s <= t - EMBARGO - (1 + H)."""
    proba = np.full(y.shape, np.nan)
    model = None
    fitted_at = None
    columns = None
    for t in range(first, last + 1):
        if fitted_at is None or t - fitted_at >= REFIT_EVERY:
            cutoff = t - EMBARGO - (1 + H)
            if cutoff + 1 - feature_start >= MIN_TRAIN_SESSIONS:
                rows_x = X[feature_start : cutoff + 1].reshape(-1, X.shape[2])
                rows_y = y[feature_start : cutoff + 1].reshape(-1)
                keep = ~np.isnan(rows_y)
                columns = ~np.all(np.isnan(rows_x[keep]), axis=0)
                if keep.sum() > 100 and len(set(rows_y[keep])) == 2:
                    model = make_model()
                    model.fit(rows_x[keep][:, columns], rows_y[keep])
                    fitted_at = t
        if model is None:
            continue
        row = X[t][:, columns]
        valid = ~np.all(np.isnan(row), axis=1)
        if valid.any():
            proba[t, valid] = model.predict_proba(row[valid])[:, 1]
    return proba


# --- statistics -----------------------------------------------------------------------------------

def deflated_sharpe(per_window: np.ndarray, trial_sharpes: np.ndarray, n_trials: int) -> dict[str, float]:
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014) on non-annualized per-window Sharpe."""
    from scipy.stats import kurtosis, norm, skew

    returns = np.asarray(per_window, dtype=float)
    T = len(returns)
    sr = returns.mean() / returns.std(ddof=1) if T > 1 and returns.std(ddof=1) > 0 else 0.0
    g3 = float(skew(returns)) if T > 2 else 0.0
    g4 = float(kurtosis(returns, fisher=False)) if T > 3 else 3.0
    variance = float(np.var(trial_sharpes, ddof=1)) if len(trial_sharpes) > 1 else 0.0
    euler = 0.5772156649
    if n_trials > 1 and variance > 0:
        sr0 = math.sqrt(variance) * ((1 - euler) * norm.ppf(1 - 1 / n_trials) + euler * norm.ppf(1 - 1 / (n_trials * math.e)))
    else:
        sr0 = 0.0
    denom = math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr**2))
    dsr = float(norm.cdf((sr - sr0) * math.sqrt(max(T - 1, 1)) / denom))
    psr = float(norm.cdf(sr * math.sqrt(max(T - 1, 1)) / denom))
    return {"sharpe_per_window": float(sr), "benchmark_sharpe": float(sr0), "deflated_sharpe": dsr, "probabilistic_sharpe": psr, "windows": T}


def bootstrap_mean_bounds(series: np.ndarray, *, resamples: int = 2000, mean_block: float = 10.0, seed: int = 0) -> tuple[float, float]:
    data = np.asarray(series, dtype=float)
    n = len(data)
    rng = np.random.default_rng(seed)
    means = np.empty(resamples)
    for k in range(resamples):
        means[k] = data[me.stationary_bootstrap_indices(n, mean_block, rng)].mean()
    return float(np.quantile(means, 0.05)), float(np.quantile(means, 0.95))


def _auc(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score

    ok = ~np.isnan(y) & ~np.isnan(p)
    return float(roc_auc_score(y[ok], p[ok])) if ok.sum() > 10 and len(set(y[ok])) == 2 else float("nan")


def daily_accuracy(y: np.ndarray, p: np.ndarray, rows: list[int]) -> np.ndarray:
    out = []
    for t in rows:
        ok = ~np.isnan(y[t]) & ~np.isnan(p[t])
        if ok.sum() >= 10:
            out.append(float(np.mean((p[t, ok] > 0.5) == (y[t, ok] == 1))))
    return np.array(out)


# --- run ------------------------------------------------------------------------------------------

def run(stock: Path, context_path: Path, intraday_path: Path, ensemble_result: Path, cache: Path | None = None) -> dict[str, object]:
    panel = load_panel(stock)
    context = me.load_context(context_path, panel.dates)
    intraday = load_intraday(intraday_path, panel.symbols, panel.dates, cache)
    design = build_design(panel, context, intraday)
    T = len(panel.dates)
    start = me.FEATURE_START + MIN_TRAIN_SESSIONS + EMBARGO + (1 + H) + REFIT_EVERY
    last = T - 2 - H
    rows = list(range(start, last + 1))

    # Target A: direction.
    ya = direction_labels(panel)
    pa = walk_forward_proba(design.X, ya, start, last)
    acc_a = daily_accuracy(ya, pa, rows)
    top_hits = []
    for t in rows:
        ok = ~np.isnan(pa[t]) & ~np.isnan(ya[t])
        if ok.sum() >= TOP_K * 2:
            idx = np.where(ok)[0][np.argsort(-pa[t, ok])[:TOP_K]]
            top_hits.append(float(np.mean(ya[t, idx] == 1)))
    ew = me.equal_weight_net(panel, H)
    trading = {}
    for exposure in ("always", "trend"):
        windows = []
        for t in rows[::H]:
            ok = [j for j in range(len(panel.symbols)) if not math.isnan(pa[t, j]) and not math.isnan(panel.open[t + 1, j]) and not math.isnan(panel.open[t + 1 + H, j])]
            if len(ok) < TOP_K * 2 or math.isnan(ew[t]):
                continue
            invest = exposure == "always" or bool(design.trend_up[t])
            ret = me.basket_return(panel, t, H, sorted(ok, key=lambda j: pa[t, j], reverse=True)[:TOP_K]) if invest else 0.0
            if ret is None:
                continue
            windows.append((t, ret, float(ew[t]), invest))
        variant = me.Variant(H, "combined-logistic", exposure, windows)
        trading[exposure] = me.summarize(variant, me.Features(design.X, design.names, np.zeros((T, 1)), [], design.trend_up, design.vix_high))
        trading[exposure]["per_window"] = [ret for _, ret, _, _ in windows]
    prior = json.loads(ensemble_result.read_text())["variants"]
    trial_sharpes = np.array([item["sharpe"] / math.sqrt(250 / item["horizon"]) for item in prior if item["sharpe"] == item["sharpe"]])
    n_trials = PRIOR_TRIALS + 2
    for exposure in trading:
        trading[exposure]["deflated"] = deflated_sharpe(np.array(trading[exposure]["per_window"]), trial_sharpes, n_trials)
    best = max(trading.values(), key=lambda item: item["deflated"]["deflated_sharpe"])  # type: ignore[index]
    regime_ok = sum(1 for item in best["regimes"].values() if item["mean_net"] >= 0) >= 3  # type: ignore[union-attr]
    a_candidate = best["deflated"]["deflated_sharpe"] > 0.95 and best["mean_net"] > 0 and regime_ok  # type: ignore[index]
    target_a = {
        "accuracy": float(acc_a.mean()),
        "accuracy_90": bootstrap_mean_bounds(acc_a),
        "auc": _auc(ya[rows].reshape(-1), pa[rows].reshape(-1)),
        "top6_accuracy": float(np.mean(top_hits)) if top_hits else float("nan"),
        "base_rate": 0.5,
        "trading": {key: {k: v for k, v in value.items() if k != "per_window"} for key, value in trading.items()},
        "verdict": "robust return edge" if a_candidate else (
            "inconclusive" if best["mean_net"] > 0 else "no return edge"  # type: ignore[operator]
        ),
    }

    # Target B: volatility.
    yb = volatility_labels(panel)
    pb = walk_forward_proba(design.X, yb, start, last)
    persistence = np.where(np.isnan(design.vol_rank), np.nan, (design.vol_rank > 0.5).astype(float))
    model_acc, base_acc = [], []
    for t in rows:
        ok = ~np.isnan(yb[t]) & ~np.isnan(pb[t]) & ~np.isnan(persistence[t])
        if ok.sum() >= 10:
            model_acc.append(float(np.mean((pb[t, ok] > 0.5) == (yb[t, ok] == 1))))
            base_acc.append(float(np.mean((persistence[t, ok] == 1) == (yb[t, ok] == 1))))
    model_acc_a, base_acc_a = np.array(model_acc), np.array(base_acc)
    diff_bounds = bootstrap_mean_bounds(model_acc_a - base_acc_a)
    acc_bounds = bootstrap_mean_bounds(model_acc_a)
    low_vol, everyone = [], []
    for t in rows[::H]:
        ok = [j for j in range(len(panel.symbols)) if not math.isnan(pb[t, j]) and not math.isnan(panel.open[t + 1, j]) and not math.isnan(panel.open[t + 1 + H, j])]
        if len(ok) < TOP_K * 2:
            continue
        calm = sorted(ok, key=lambda j: pb[t, j])[: len(ok) // 2]
        a, b = me.basket_return(panel, t, H, calm), me.basket_return(panel, t, H, ok)
        if a is not None and b is not None:
            low_vol.append(a)
            everyone.append(b)

    def _stats(values: list[float]) -> dict[str, float]:
        arr = np.array(values)
        curve = np.cumprod(1 + arr)
        return {
            "mean_net": float(arr.mean()),
            "annualized_net": float(arr.mean() * 250 / H),
            "annualized_vol": float(arr.std(ddof=1) * math.sqrt(250 / H)),
            "max_drawdown": float(np.max(1 - curve / np.maximum.accumulate(curve))),
            "windows": len(arr),
        }

    target_b = {
        "accuracy": float(model_acc_a.mean()),
        "accuracy_90": acc_bounds,
        "persistence_accuracy": float(base_acc_a.mean()),
        "improvement_90": diff_bounds,
        "auc": _auc(yb[rows].reshape(-1), pb[rows].reshape(-1)),
        "persistence_auc": _auc(yb[rows].reshape(-1), design.vol_rank[rows].reshape(-1)),
        "low_vol_half": _stats(low_vol),
        "all_stocks": _stats(everyone),
        "verdict": "robust risk edge" if diff_bounds[0] > 0 and acc_bounds[0] > 0.5 else (
            "high accuracy, but not better than persistence" if acc_bounds[0] > 0.5 else "no risk edge"
        ),
    }
    return {
        "protocol": "services/quant/docs/ml-combined-protocol.md",
        "period": {"first_decision": panel.dates[start].isoformat(), "last_decision": panel.dates[last].isoformat()},
        "symbols": len(panel.symbols),
        "features": design.names,
        "trials_counted": n_trials,
        "target_a_direction": target_a,
        "target_b_volatility": target_b,
    }

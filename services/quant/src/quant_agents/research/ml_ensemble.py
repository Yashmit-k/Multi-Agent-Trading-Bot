"""ML ensemble study, scored per services/quant/docs/ml-ensemble-protocol.md.

Grid: holding period x selector (ridge, hgb, rf, et, rank-ensemble) x exposure
rule (always, trend, ML timing). Walk-forward only; every prediction uses
bars ending at or before the decision close. Every variant is reported, and
White's Reality Check guards against picking the luckiest one.
"""

from __future__ import annotations

import json
import math
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import numpy as np

from quant_agents.research.ml_rank import Panel, _rank, _rolling, _shift, load_panel
from quant_agents.research.timesfm3.scores import official_session_date

HORIZONS = (5, 10, 20)
SELECTORS = ("ridge", "hgb", "rf", "et", "ensemble")
EXPOSURES = ("always", "trend", "timing")
TOP_K = 6
NOTIONAL = 20000.0
SLIPPAGE = 0.0005
REFIT_EVERY = 21
MIN_TRAIN_SESSIONS = 120
FEATURE_START = 60  # first decision row with full 60-session lookbacks

# NIFTY sector index for each constituent, fixed before any run. None: no matching sector index.
SECTOR_OF: dict[str, str | None] = {
    "AXISBANK": "NIFTY BANK", "HDFCBANK": "NIFTY BANK", "ICICIBANK": "NIFTY BANK", "INDUSINDBK": "NIFTY BANK",
    "KOTAKBANK": "NIFTY BANK", "SBIN": "NIFTY BANK",
    "BAJFINANCE": "NIFTY FIN SERVICE", "BAJAJFINSV": "NIFTY FIN SERVICE", "HDFCLIFE": "NIFTY FIN SERVICE",
    "SBILIFE": "NIFTY FIN SERVICE", "SHRIRAMFIN": "NIFTY FIN SERVICE",
    "HCLTECH": "NIFTY IT", "INFY": "NIFTY IT", "TCS": "NIFTY IT", "TECHM": "NIFTY IT", "WIPRO": "NIFTY IT",
    "BAJAJ-AUTO": "NIFTY AUTO", "EICHERMOT": "NIFTY AUTO", "HEROMOTOCO": "NIFTY AUTO", "M&M": "NIFTY AUTO",
    "MARUTI": "NIFTY AUTO", "TMPV": "NIFTY AUTO",
    "BRITANNIA": "NIFTY FMCG", "HINDUNILVR": "NIFTY FMCG", "ITC": "NIFTY FMCG", "NESTLEIND": "NIFTY FMCG",
    "TATACONSUM": "NIFTY FMCG",
    "HINDALCO": "NIFTY METAL", "JSWSTEEL": "NIFTY METAL", "TATASTEEL": "NIFTY METAL",
    "CIPLA": "NIFTY PHARMA", "DRREDDY": "NIFTY PHARMA", "SUNPHARMA": "NIFTY PHARMA",
    "BPCL": "NIFTY ENERGY", "NTPC": "NIFTY ENERGY", "ONGC": "NIFTY ENERGY", "POWERGRID": "NIFTY ENERGY",
    "RELIANCE": "NIFTY ENERGY",
    "TITAN": "NIFTY CONSR DURBL",
}


# --- costs (float mirror of research/delivery_costs.py; a test pins them together) ---------------

def _money(value: float) -> float:
    """Round half up to paise, as delivery_costs.money does (Python's round() is half-even)."""
    return math.floor(value * 100 + 0.5 + 1e-9) / 100


def _charges(notional: float, *, buy: bool) -> float:
    txn = _money(notional * 0.0000307)
    sebi = _money(notional / 1e7 * 10)
    gst = _money((sebi + txn) * 0.18)
    stt = _money(notional * 0.001)
    stamp = _money(notional * 0.00015) if buy else 0.0
    dp = 0.0 if buy else 15.34
    return txn + sebi + gst + stt + stamp + dp


def trade_net(entry_open: float, exit_open: float) -> tuple[float, float, float] | None:
    """(net pnl, invested, costs) for one ₹20k position, or None if under one share."""
    entry = entry_open * (1 + SLIPPAGE)
    exit_ = exit_open * (1 - SLIPPAGE)
    quantity = int(NOTIONAL // entry)
    if quantity < 1:
        return None
    bought, sold = quantity * entry, quantity * exit_
    costs = _charges(_money(bought), buy=True) + _charges(_money(sold), buy=False)
    return sold - bought - costs, bought, costs


def basket_return(panel: Panel, t: int, h: int, picks: list[int]) -> float | None:
    pnl = invested = 0.0
    for j in picks:
        a, b = panel.open[t + 1, j], panel.open[t + 1 + h, j]
        if math.isnan(a) or math.isnan(b):
            continue
        result = trade_net(float(a), float(b))
        if result is not None:
            pnl += result[0]
            invested += result[1]
    return None if invested == 0 else pnl / invested


# --- data -----------------------------------------------------------------------------------------

def load_context(path: Path, dates: list[date]) -> dict[str, np.ndarray]:
    """Close series per index, aligned to the stock calendar (NaN where missing)."""
    index = {day: i for i, day in enumerate(dates)}
    out: dict[str, np.ndarray] = {}
    with path.open() as handle:
        for line in handle:
            bar = json.loads(line)
            session = official_session_date(datetime.fromisoformat(bar["end"]))
            if session is None or session not in index:
                continue
            series = out.setdefault(bar["symbol"], np.full(len(dates), np.nan))
            series[index[session]] = float(bar["close"])
    return out


@dataclass
class Features:
    stock: np.ndarray  # [T, N, F]
    stock_names: list[str]
    market: np.ndarray  # [T, M]
    market_names: list[str]
    nifty_trend_up: np.ndarray  # [T] bool
    vix_high: np.ndarray  # [T] bool


def build(panel: Panel, context: dict[str, np.ndarray]) -> Features:
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    c, o, h, low, v = panel.close, panel.open, panel.high, panel.low, panel.volume
    T, N = c.shape
    nifty = context["NIFTY 50"]
    vix = context["INDIA VIX"]
    with np.errstate(all="ignore"):
        daily = c / _shift(c, 1) - 1
        prev = _shift(c, 1)
        tr = np.fmax(h - low, np.fmax(np.abs(h - prev), np.abs(low - prev)))
        gains, losses = np.where(daily > 0, daily, 0.0), np.where(daily < 0, -daily, 0.0)
        rsi = 100 - 100 / (1 + _rolling(gains, 14, np.nanmean) / np.where(_rolling(losses, 14, np.nanmean) == 0, np.nan, _rolling(losses, 14, np.nanmean)))
        nifty_col = np.repeat(nifty[:, None], N, axis=1)
        nifty_daily = nifty_col / _shift(nifty_col, 1) - 1
        cov = _rolling(daily * nifty_daily, 60, np.nanmean) - _rolling(daily, 60, np.nanmean) * _rolling(nifty_daily, 60, np.nanmean)
        beta = cov / _rolling(nifty_daily, 60, np.nanvar)
        ret_20 = c / _shift(c, 20) - 1
        nifty_ret20 = nifty_col / _shift(nifty_col, 20) - 1
        sector_ret20 = np.full((T, N), np.nan)
        for j, symbol in enumerate(panel.symbols):
            sector = SECTOR_OF.get(symbol)
            if sector and sector in context:
                series = context[sector]
                sector_ret20[:, j] = series / _shift(series[:, None], 20)[:, 0] - 1
        vol20 = _rolling(v, 20, np.nanmean)
        stock = {
            "ret_1": daily,
            "ret_5": c / _shift(c, 5) - 1,
            "ret_10": c / _shift(c, 10) - 1,
            "ret_20": ret_20,
            "ret_60": c / _shift(c, 60) - 1,
            "vol_20": _rolling(daily, 20, np.nanstd),
            "atr_14": _rolling(tr, 14, np.nanmean) / c,
            "rsi_14": rsi,
            "dist_ma20": c / _rolling(c, 20, np.nanmean) - 1,
            "dist_ma50": c / _rolling(c, 50, np.nanmean) - 1,
            "vol_ratio": _rolling(v, 5, np.nanmean) / vol20,
            "vol_z": (v - vol20) / _rolling(v, 20, np.nanstd),
            "gap": o / prev - 1,
            "dist_high_250": c / _rolling(h, 250, np.nanmax) - 1,
            "beta_60": beta,
            "rel_nifty_20": ret_20 - nifty_ret20,
            "rel_sector_20": ret_20 - sector_ret20,
            "sector_ret_20": sector_ret20,
        }
        names, layers = [], []
        for name, values in stock.items():
            names += [name, f"{name}_rank"]
            layers += [values, _rank(values)]
        ma50 = c / _rolling(c, 50, np.nanmean) - 1
        nifty_ma50 = _rolling(nifty[:, None], 50, np.nanmean)[:, 0]
        vix_median = _rolling(vix[:, None], 120, np.nanmedian)[:, 0]
        vix_pct = np.full(T, np.nan)
        for t in range(119, T):
            window = vix[t - 119 : t + 1]
            vix_pct[t] = np.mean(window <= vix[t])
        market = {
            "nifty_ret_5": nifty / _shift(nifty[:, None], 5)[:, 0] - 1,
            "nifty_ret_20": nifty / _shift(nifty[:, None], 20)[:, 0] - 1,
            "nifty_ret_60": nifty / _shift(nifty[:, None], 60)[:, 0] - 1,
            "nifty_vs_ma50": nifty / nifty_ma50 - 1,
            "vix": vix,
            "vix_chg_5": vix / _shift(vix[:, None], 5)[:, 0] - 1,
            "vix_pct_120": vix_pct,
            "breadth_ma50": np.nanmean(ma50 > 0, axis=1),
            "dispersion_5": np.nanstd(stock["ret_5"], axis=1),
        }
    market_names = list(market)
    market_matrix = np.stack([market[name] for name in market_names], axis=1)
    stock_matrix = np.concatenate([np.stack(layers, axis=2), np.repeat(market_matrix[:, None, :], N, axis=1)], axis=2)
    return Features(
        stock=stock_matrix,
        stock_names=names + market_names,
        market=market_matrix,
        market_names=market_names,
        nifty_trend_up=np.nan_to_num(nifty / nifty_ma50 - 1, nan=0.0) > 0,
        vix_high=np.nan_to_num(vix - vix_median, nan=0.0) > 0,
    )


def labels(panel: Panel, h: int) -> tuple[np.ndarray, np.ndarray]:
    """(excess label [T,N], gross forward return [T,N]) for entry at open t+1 and exit at open t+1+h."""
    o = panel.open
    fwd = np.full_like(o, np.nan)
    for t in range(o.shape[0] - 1 - h):
        fwd[t] = o[t + 1 + h] / o[t + 1] - 1
    with np.errstate(all="ignore"):
        return fwd - np.nanmean(fwd, axis=1, keepdims=True), fwd


# --- models ---------------------------------------------------------------------------------------

def make_selector(name: str):
    from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if name == "ridge":
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=10.0))
    if name == "hgb":
        return HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0, random_state=0)
    trees = dict(n_estimators=150, max_depth=6, min_samples_leaf=100, max_features=0.5, random_state=0, n_jobs=-1)
    if name == "rf":
        return make_pipeline(SimpleImputer(strategy="median"), RandomForestRegressor(**trees))
    if name == "et":
        return make_pipeline(SimpleImputer(strategy="median"), ExtraTreesRegressor(**trees))
    raise ValueError(name)


def make_timer():
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.5, max_iter=500))


BASE_SELECTORS = ("ridge", "hgb", "rf", "et")


def walk_forward(features: Features, y: np.ndarray, market_target: np.ndarray, h: int, first: int, last: int) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Selector predictions per base model, plus timing probabilities, for rows first..last.

    A fit at decision row t uses label rows s with s + 1 + h <= t - h (exit on or before t, minus an h-session embargo).
    """
    X = features.stock
    preds = {name: np.full(y.shape, np.nan) for name in BASE_SELECTORS}
    timing = np.full(y.shape[0], np.nan)
    models: dict[str, object] = {}
    timer = None
    fitted_at = None
    for t in range(first, last + 1):
        if fitted_at is None or t - fitted_at >= REFIT_EVERY:
            cutoff = t - h - (1 + h)
            if cutoff + 1 - FEATURE_START < MIN_TRAIN_SESSIONS:
                continue
            rows_x = X[FEATURE_START : cutoff + 1].reshape(-1, X.shape[2])
            rows_y = y[FEATURE_START : cutoff + 1].reshape(-1)
            keep = ~np.isnan(rows_y)
            # Features with no value yet (e.g. the 250-session high early on) are left out of this fit.
            columns = ~np.all(np.isnan(rows_x[keep]), axis=0)
            for name in BASE_SELECTORS:
                model = make_selector(name)
                model.fit(rows_x[keep][:, columns], rows_y[keep])
                models[name] = model
            mx = features.market[FEATURE_START : cutoff + 1]
            my = market_target[FEATURE_START : cutoff + 1]
            ok = ~np.isnan(my)
            if ok.sum() > 30 and len(set(my[ok] > 0)) == 2:
                timer = make_timer()
                timer.fit(mx[ok], my[ok] > 0)
            fitted_at = t
        if not models:
            continue
        row = X[t]
        valid = ~np.isnan(row[:, 0]) | ~np.isnan(row[:, 2])
        for name, model in models.items():
            if valid.any():
                preds[name][t, valid] = model.predict(row[valid][:, columns])
        if timer is not None:
            timing[t] = timer.predict_proba(features.market[t : t + 1])[0, 1]
    return preds, timing


def ensemble(preds: dict[str, np.ndarray]) -> np.ndarray:
    ranks = [_rank(preds[name]) for name in BASE_SELECTORS]
    with np.errstate(all="ignore"):
        stacked = np.stack(ranks, axis=0)
        out = np.nanmean(stacked, axis=0)
    out[np.all(np.isnan(stacked), axis=0)] = np.nan
    return out


# --- evaluation -----------------------------------------------------------------------------------

@dataclass
class Variant:
    horizon: int
    selector: str
    exposure: str
    windows: list[tuple[int, float, float, bool]] = field(default_factory=list)  # (t, net return, equal-weight return, invested)

    @property
    def key(self) -> str:
        return f"H{self.horizon}-{self.selector}-{self.exposure}"


def equal_weight_net(panel: Panel, h: int) -> np.ndarray:
    out = np.full(panel.open.shape[0], np.nan)
    for t in range(panel.open.shape[0] - 1 - h):
        eligible = [j for j in range(len(panel.symbols)) if not math.isnan(panel.open[t + 1, j]) and not math.isnan(panel.open[t + 1 + h, j])]
        value = basket_return(panel, t, h, eligible)
        out[t] = np.nan if value is None else value
    return out


def run_variants(panel: Panel, features: Features, start_row: int) -> tuple[list[Variant], dict[int, np.ndarray]]:
    variants: list[Variant] = []
    ew_by_h: dict[int, np.ndarray] = {}
    last_row = panel.open.shape[0] - 1
    for h in HORIZONS:
        excess, _ = labels(panel, h)
        ew = equal_weight_net(panel, h)
        ew_by_h[h] = ew
        rows = [t for t in range(start_row, last_row - h) if t + 1 + h <= last_row][::h]
        base, timing = walk_forward(features, excess, ew, h, rows[0], rows[-1])
        scores = {**base, "ensemble": ensemble(base)}
        for selector in SELECTORS:
            for exposure in EXPOSURES:
                variant = Variant(h, selector, exposure)
                for t in rows:
                    pred = scores[selector][t]
                    eligible = [j for j in range(len(panel.symbols)) if not math.isnan(pred[j])
                                and not math.isnan(panel.open[t + 1, j]) and not math.isnan(panel.open[t + 1 + h, j])]
                    if len(eligible) < TOP_K * 2 or math.isnan(ew[t]):
                        continue
                    invest = exposure == "always" or (exposure == "trend" and bool(features.nifty_trend_up[t])) or (
                        exposure == "timing" and not math.isnan(timing[t]) and timing[t] > 0.5
                    )
                    if invest:
                        picks = sorted(eligible, key=lambda j: pred[j], reverse=True)[:TOP_K]
                        ret = basket_return(panel, t, h, picks)
                        if ret is None:
                            continue
                    else:
                        ret = 0.0
                    variant.windows.append((t, ret, float(ew[t]), invest))
                variants.append(variant)
    return variants, ew_by_h


def daily_series(windows: list[tuple[int, float, float, bool]], h: int, length: int, *, excess: bool = False) -> np.ndarray:
    out = np.zeros(length)
    for t, ret, ew, _ in windows:
        value = (ret - ew) if excess else ret
        for k in range(t + 1, min(t + 1 + h, length)):
            out[k] += value / h
    return out


def stationary_bootstrap_indices(n: int, mean_block: float, rng: np.random.Generator) -> np.ndarray:
    idx = np.empty(n, dtype=int)
    idx[0] = rng.integers(n)
    p = 1.0 / mean_block
    for i in range(1, n):
        idx[i] = rng.integers(n) if rng.random() < p else (idx[i - 1] + 1) % n
    return idx


def reality_check(series: np.ndarray, *, resamples: int = 2000, mean_block: float = 10.0, seed: int = 0) -> tuple[float, int]:
    """White's Reality Check on mean > 0 across variants (rows). Returns (p-value, index of best)."""
    n = series.shape[1]
    means = series.mean(axis=1)
    best = int(np.argmax(means))
    observed = math.sqrt(n) * means.max()
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(resamples):
        idx = stationary_bootstrap_indices(n, mean_block, rng)
        boot = math.sqrt(n) * (series[:, idx].mean(axis=1) - means)
        if boot.max() >= observed:
            exceed += 1
    return exceed / resamples, best


def summarize(variant: Variant, features: Features) -> dict[str, object]:
    rets = np.array([ret for _, ret, _, _ in variant.windows])
    ews = np.array([ew for _, _, ew, _ in variant.windows])
    invested = np.array([inv for *_, inv in variant.windows])
    per_year = 250 / variant.horizon
    curve = np.cumprod(1 + rets) if len(rets) else np.array([1.0])
    drawdown = float(np.max(1 - curve / np.maximum.accumulate(curve))) if len(rets) else 0.0
    regimes: dict[str, list[float]] = {}
    for t, ret, _, _ in variant.windows:
        label = f"{'up' if features.nifty_trend_up[t] else 'down'}-trend/{'high' if features.vix_high[t] else 'low'}-vol"
        regimes.setdefault(label, []).append(ret)
    std = float(rets.std(ddof=1)) if len(rets) > 1 else float("nan")
    return {
        "variant": variant.key,
        "horizon": variant.horizon,
        "selector": variant.selector,
        "exposure": variant.exposure,
        "windows": len(rets),
        "mean_net": float(rets.mean()) if len(rets) else float("nan"),
        "annualized_net": float(rets.mean() * per_year) if len(rets) else float("nan"),
        "sharpe": float(rets.mean() / std * math.sqrt(per_year)) if std and std == std and std > 0 else float("nan"),
        "hit_rate": float(np.mean(rets > 0)) if len(rets) else float("nan"),
        "max_drawdown": drawdown,
        "exposure_share": float(invested.mean()) if len(invested) else float("nan"),
        "excess_vs_equal_weight": float((rets - ews).mean()) if len(rets) else float("nan"),
        "total_compounded": float(curve[-1] - 1),
        "regimes": {key: {"windows": len(values), "mean_net": float(np.mean(values))} for key, values in sorted(regimes.items())},
    }


def run(stock_path: Path, context_path: Path) -> dict[str, object]:
    panel = load_panel(stock_path)
    context = load_context(context_path, panel.dates)
    features = build(panel, context)
    start_row = FEATURE_START + MIN_TRAIN_SESSIONS + 2 * max(HORIZONS) + REFIT_EVERY
    variants, ew_by_h = run_variants(panel, features, start_row)
    length = panel.open.shape[0]
    first = min(t for variant in variants for t, *_ in variant.windows)
    net = np.stack([daily_series(v.windows, v.horizon, length)[first:] for v in variants])
    excess = np.stack([daily_series(v.windows, v.horizon, length, excess=True)[first:] for v in variants])
    p_net, best_net = reality_check(net)
    p_excess, best_excess = reality_check(excess)
    summaries = [summarize(variant, features) for variant in variants]
    baselines = {}
    for h in HORIZONS:
        rows = [t for t, *_ in next(v for v in variants if v.horizon == h).windows]
        values = np.array([ew_by_h[h][t] for t in rows])
        baselines[f"H{h}-equal-weight"] = {"windows": len(values), "mean_net": float(values.mean()), "annualized_net": float(values.mean() * 250 / h)}
    candidates = []
    for summary, variant_index in zip(summaries, range(len(summaries))):
        regime_ok = sum(1 for item in summary["regimes"].values() if item["mean_net"] >= 0) >= 3  # type: ignore[union-attr]
        if p_net < 0.10 and variant_index == best_net and summary["mean_net"] > 0 and regime_ok and summary["excess_vs_equal_weight"] > 0:  # type: ignore[operator]
            candidates.append(summary["variant"])
    return {
        "protocol": "services/quant/docs/ml-ensemble-protocol.md",
        "period": {"first_decision": panel.dates[first].isoformat(), "last_bar": panel.dates[-1].isoformat()},
        "symbols": len(panel.symbols),
        "features": features.stock_names,
        "variants": summaries,
        "baselines": baselines,
        "reality_check": {
            "net_return_p_value": p_net,
            "best_net_variant": summaries[best_net]["variant"],
            "excess_p_value": p_excess,
            "best_excess_variant": summaries[best_excess]["variant"],
        },
        "candidates": candidates,
        "verdict": "candidate for forward paper test" if candidates else "no robust edge",
    }

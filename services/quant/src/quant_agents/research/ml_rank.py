"""ML cross-sectional ranker, scored per services/quant/docs/ml-rank-protocol.md.

Pick 6 NIFTY 50 stocks after the close of t, buy at the open of t+1, sell at
the open of t+6, pay Zerodha delivery charges plus 5 bp slippage per fill.
Features use bars ending on or before t only; labels are never features.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import numpy as np

from quant_agents.research.delivery_costs import delivery_buy, delivery_sell
from quant_agents.research.timesfm3.scores import EXCLUDED_SYMBOL, official_session_date

HOLD = 5
TOP_K = 6
NOTIONAL = 20000.0
SLIPPAGE = 0.0005
REFIT_EVERY = 21
EMBARGO = 5
MIN_TRAIN_SESSIONS = 120
DEV_START = date(2024, 4, 1)
DEV_END = date(2025, 12, 31)
OOS_START = date(2026, 1, 1)
PRICE_FEATURES = (
    "ret_1", "ret_5", "ret_10", "ret_20", "ret_60", "vol_20", "atr_14", "dist_ma20", "dist_ma50", "rsi_14", "vol_ratio", "gap",
)
MARKET_FEATURES = ("mkt_ret_5", "mkt_ret_20", "disp_ret_5")


@dataclass
class Panel:
    dates: list[date]
    symbols: list[str]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray


def load_panel(path: Path) -> Panel:
    rows: dict[str, dict[date, tuple[float, float, float, float, float]]] = {}
    with path.open() as handle:
        for line in handle:
            bar = json.loads(line)
            if bar["symbol"] == EXCLUDED_SYMBOL or bar.get("timeframe") != "1d":
                continue
            session = official_session_date(datetime.fromisoformat(bar["end"]))
            if session is None:
                continue
            rows.setdefault(bar["symbol"], {})[session] = (
                float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"]), float(bar["volume"]),
            )
    symbols = sorted(rows)
    dates = sorted({day for series in rows.values() for day in series})
    shape = (len(dates), len(symbols))
    arrays = [np.full(shape, np.nan) for _ in range(5)]
    index = {day: i for i, day in enumerate(dates)}
    for j, symbol in enumerate(symbols):
        for day, values in rows[symbol].items():
            for k, value in enumerate(values):
                arrays[k][index[day], j] = value
    return Panel(dates, symbols, *arrays)


def _shift(a: np.ndarray, n: int) -> np.ndarray:
    """Value n rows earlier (n > 0); NaN where unavailable."""
    out = np.full_like(a, np.nan)
    out[n:] = a[:-n]
    return out


def _rolling(a: np.ndarray, n: int, fn) -> np.ndarray:
    out = np.full_like(a, np.nan)
    for t in range(n - 1, a.shape[0]):
        window = a[t - n + 1 : t + 1]
        with np.errstate(all="ignore"):
            out[t] = fn(window, axis=0)
    return out


def _rank(a: np.ndarray) -> np.ndarray:
    """Cross-sectional percentile rank per row, ignoring NaN."""
    out = np.full_like(a, np.nan)
    for t in range(a.shape[0]):
        row = a[t]
        ok = ~np.isnan(row)
        if ok.sum() > 1:
            order = row[ok].argsort().argsort()
            out[t, ok] = order / (ok.sum() - 1)
    return out


def build_features(panel: Panel) -> tuple[np.ndarray, list[str]]:
    """X[t, j, f] uses only rows <= t."""
    import warnings

    warnings.filterwarnings("ignore", category=RuntimeWarning, module=__name__)
    c, o, h, low, v = panel.close, panel.open, panel.high, panel.low, panel.volume
    with np.errstate(all="ignore"):
        daily = c / _shift(c, 1) - 1
        prev_close = _shift(c, 1)
        true_range = np.fmax(h - low, np.fmax(np.abs(h - prev_close), np.abs(low - prev_close)))
        gains = np.where(daily > 0, daily, 0.0)
        losses = np.where(daily < 0, -daily, 0.0)
        avg_gain = _rolling(gains, 14, np.nanmean)
        avg_loss = _rolling(losses, 14, np.nanmean)
        rsi = 100 - 100 / (1 + avg_gain / np.where(avg_loss == 0, np.nan, avg_loss))
        price = {
            "ret_1": daily,
            "ret_5": c / _shift(c, 5) - 1,
            "ret_10": c / _shift(c, 10) - 1,
            "ret_20": c / _shift(c, 20) - 1,
            "ret_60": c / _shift(c, 60) - 1,
            "vol_20": _rolling(daily, 20, np.nanstd),
            "atr_14": _rolling(true_range, 14, np.nanmean) / c,
            "dist_ma20": c / _rolling(c, 20, np.nanmean) - 1,
            "dist_ma50": c / _rolling(c, 50, np.nanmean) - 1,
            "rsi_14": rsi,
            "vol_ratio": _rolling(v, 5, np.nanmean) / _rolling(v, 20, np.nanmean),
            "gap": o / prev_close - 1,
        }
        ret_5 = price["ret_5"]
        market = {
            "mkt_ret_5": np.repeat(np.nanmean(ret_5, axis=1, keepdims=True), c.shape[1], axis=1),
            "mkt_ret_20": np.repeat(np.nanmean(price["ret_20"], axis=1, keepdims=True), c.shape[1], axis=1),
            "disp_ret_5": np.repeat(np.nanstd(ret_5, axis=1, keepdims=True), c.shape[1], axis=1),
        }
    names: list[str] = []
    layers: list[np.ndarray] = []
    for name in PRICE_FEATURES:
        names += [name, f"{name}_rank"]
        layers += [price[name], _rank(price[name])]
    for name in MARKET_FEATURES:
        names.append(name)
        layers.append(market[name])
    return np.stack(layers, axis=2), names


def forward_returns(panel: Panel) -> np.ndarray:
    """R[t, j] = open[t+1+HOLD] / open[t+1] - 1 (gross, no costs). Uses future bars: label only."""
    o = panel.open
    out = np.full_like(o, np.nan)
    n = o.shape[0]
    for t in range(n - 1 - HOLD):
        out[t] = o[t + 1 + HOLD] / o[t + 1] - 1
    return out


def excess_labels(fwd: np.ndarray) -> np.ndarray:
    import warnings

    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)  # rows with no exit bar yet are all-NaN
        return fwd - np.nanmean(fwd, axis=1, keepdims=True)


def make_model(name: str):
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer

    if name == "A":
        return HistGradientBoostingRegressor(
            max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=1.0, random_state=0
        )
    if name == "B":
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=10.0))
    raise ValueError(name)


def walk_forward_predictions(X: np.ndarray, y: np.ndarray, model_name: str, first: int, last: int) -> np.ndarray:
    """Predictions for decision rows first..last. Each fit sees labels whose exit is <= t - EMBARGO."""
    preds = np.full(y.shape, np.nan)
    model = None
    fitted_at = None
    for t in range(first, last + 1):
        if model is None or t - fitted_at >= REFIT_EVERY:
            cutoff = t - EMBARGO - (1 + HOLD)  # last label row whose exit open (row s+1+HOLD) is <= t - EMBARGO
            if cutoff + 1 < MIN_TRAIN_SESSIONS:
                continue
            rows_x = X[: cutoff + 1].reshape(-1, X.shape[2])
            rows_y = y[: cutoff + 1].reshape(-1)
            keep = ~np.isnan(rows_y) & ~np.all(np.isnan(rows_x), axis=1)
            model = make_model(model_name)
            model.fit(rows_x[keep], rows_y[keep])
            fitted_at = t
        row = X[t]
        ok = ~np.all(np.isnan(row), axis=1)
        if ok.any():
            preds[t, ok] = model.predict(row[ok])
    return preds


@dataclass
class Trade:
    symbol: str
    entry: float
    exit: float
    quantity: int
    net_pnl: float
    cost: float
    invested: float


def trade_for(symbol: str, entry_open: float, exit_open: float) -> Trade | None:
    entry = entry_open * (1 + SLIPPAGE)
    exit_ = exit_open * (1 - SLIPPAGE)
    quantity = int(NOTIONAL // entry)
    if quantity < 1:
        return None
    bought = quantity * entry
    sold = quantity * exit_
    cost = float(delivery_buy(Decimal(str(round(bought, 2)))).total + delivery_sell(Decimal(str(round(sold, 2)))).total)
    return Trade(symbol, entry, exit_, quantity, sold - bought - cost, cost, bought)


def window_trades(panel: Panel, t: int, picks: list[int]) -> list[Trade]:
    trades = []
    for j in picks:
        entry, exit_ = panel.open[t + 1, j], panel.open[t + 1 + HOLD, j]
        if math.isnan(entry) or math.isnan(exit_):
            continue
        trade = trade_for(panel.symbols[j], float(entry), float(exit_))
        if trade is not None:
            trades.append(trade)
    return trades


def window_return(trades: list[Trade]) -> float | None:
    invested = sum(item.invested for item in trades)
    return None if invested == 0 else sum(item.net_pnl for item in trades) / invested


@dataclass
class PeriodResult:
    name: str
    windows: int
    strategy_mean: float
    equal_weight_mean: float
    momentum_mean: float
    random_mean: float
    excess_mean: float
    excess_lower_90: float
    excess_upper_90: float
    hit_rate: float
    trades: int
    total_cost: float
    total_net_pnl: float
    excess_without_best_symbol: float
    best_symbol: str
    passed: dict[str, bool] = field(default_factory=dict)


def block_bootstrap(values: list[float], *, block: int = 4, resamples: int = 5000, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    data = np.asarray(values)
    n = len(data)
    if n < 2:
        return (float("nan"), float("nan"))
    means = np.empty(resamples)
    for i in range(resamples):
        starts = rng.integers(0, n, size=math.ceil(n / block))
        sample = np.concatenate([np.take(data, range(s, s + block), mode="wrap") for s in starts])[:n]
        means[i] = sample.mean()
    return float(np.quantile(means, 0.05)), float(np.quantile(means, 0.95))


def score_period(panel: Panel, X: np.ndarray, names: list[str], preds: np.ndarray, decision_rows: list[int], name: str) -> PeriodResult:
    rng = np.random.default_rng(0)
    momentum_signal = X[:, :, names.index("ret_20")]
    windows: list[tuple[list[Trade], float, float, float]] = []  # (strategy trades, equal weight, momentum, random)
    for t in decision_rows:
        eligible = [
            j for j in range(len(panel.symbols))
            if not math.isnan(preds[t, j]) and not math.isnan(panel.open[t + 1, j]) and not math.isnan(panel.open[t + 1 + HOLD, j])
        ]
        if len(eligible) < TOP_K * 2:
            continue
        picks = sorted(eligible, key=lambda j: preds[t, j], reverse=True)[:TOP_K]
        trades = window_trades(panel, t, picks)
        ew = window_return(window_trades(panel, t, eligible))
        pool = [j for j in eligible if not math.isnan(momentum_signal[t, j])]
        mom = window_return(window_trades(panel, t, sorted(pool, key=lambda j: momentum_signal[t, j], reverse=True)[:TOP_K]))
        draws = [window_return(window_trades(panel, t, [int(j) for j in rng.choice(eligible, TOP_K, replace=False)])) for _ in range(200)]
        rand = float(np.mean([value for value in draws if value is not None]))
        if window_return(trades) is None or ew is None or mom is None:
            continue
        windows.append((trades, ew, mom, rand))
    strategy = [window_return(trades) or 0.0 for trades, *_ in windows]
    equal = [ew for _, ew, _, _ in windows]
    excess = [ret - ew for ret, ew in zip(strategy, equal)]
    all_trades = [trade for trades, *_ in windows for trade in trades]
    by_symbol: dict[str, float] = {}
    for trade in all_trades:
        by_symbol[trade.symbol] = by_symbol.get(trade.symbol, 0.0) + trade.net_pnl
    best = max(by_symbol, key=by_symbol.get) if by_symbol else ""
    without = []
    for (trades, ew, _, _) in windows:
        ret = window_return([trade for trade in trades if trade.symbol != best])
        if ret is not None:
            without.append(ret - ew)
    lower, upper = block_bootstrap(excess)
    mean = lambda values: float(np.mean(values)) if values else float("nan")  # noqa: E731
    result = PeriodResult(
        name=name,
        windows=len(windows),
        strategy_mean=mean(strategy),
        equal_weight_mean=mean(equal),
        momentum_mean=mean([mom for _, _, mom, _ in windows]),
        random_mean=mean([rand for *_, rand in windows]),
        excess_mean=mean(excess),
        excess_lower_90=lower,
        excess_upper_90=upper,
        hit_rate=mean([1.0 if value > 0 else 0.0 for value in excess]),
        trades=len(all_trades),
        total_cost=sum(item.cost for item in all_trades),
        total_net_pnl=sum(item.net_pnl for item in all_trades),
        excess_without_best_symbol=mean(without),
        best_symbol=best,
    )
    result.passed = {
        "excess_positive_with_lower_bound": result.excess_mean > 0 and lower > 0,
        "beats_momentum": result.strategy_mean > result.momentum_mean,
        "beats_random": result.strategy_mean > result.random_mean,
        "not_one_stock": result.excess_without_best_symbol > 0,
    }
    return result


def rebalance_rows(panel: Panel, start: date, end: date) -> list[int]:
    rows = [t for t, day in enumerate(panel.dates) if start <= day <= end and t + 1 + HOLD < len(panel.dates)]
    return rows[::HOLD]


def run(snapshot: Path, *, score_oos: bool) -> dict[str, object]:
    """Develop A and B on 2024-04..2025-12, choose one, then (if asked) score 2026 once."""
    panel = load_panel(snapshot)
    X, names = build_features(panel)
    y = excess_labels(forward_returns(panel))
    dev_rows = rebalance_rows(panel, DEV_START, DEV_END)
    report: dict[str, object] = {"protocol": "services/quant/docs/ml-rank-protocol.md", "symbols": len(panel.symbols), "features": names}
    dev: dict[str, PeriodResult] = {}
    for model_name in ("A", "B"):
        preds = walk_forward_predictions(X, y, model_name, dev_rows[0], dev_rows[-1])
        dev[model_name] = score_period(panel, X, names, preds, dev_rows, f"development model {model_name}")
    chosen = "A" if dev["A"].excess_mean > dev["B"].excess_mean else "B"
    report["development"] = {key: value.__dict__ for key, value in dev.items()}
    report["chosen_model"] = chosen
    if score_oos:
        last_day = panel.dates[-1]
        oos_rows = rebalance_rows(panel, OOS_START, last_day)
        preds = walk_forward_predictions(X, y, chosen, oos_rows[0], oos_rows[-1])
        oos = score_period(panel, X, names, preds, oos_rows, f"out-of-sample model {chosen}")
        report["out_of_sample"] = oos.__dict__
        report["accepted"] = all(oos.passed.values())
    return report

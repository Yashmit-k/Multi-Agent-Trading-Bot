"""Quant-agent backtest and tuning, scored per services/quant/docs/agent-tuning-protocol.md.

Stage 1 computes the real Feature Engine features for every bar (cached per symbol and timeframe).
Stage 2 re-implements the 1.3.0 agent rules as array code with their constants exposed, and first
checks them against the real agents. Stage 3 selects on train, keeps on validate, weights, and scores
the final test once.

    python -m quant_agents.research.agent_tuning --workers 9
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from scipy.stats import rankdata

from quant_agents.research import exit_rules as er
from quant_agents.research import ml_ensemble as me

IST = er.IST
CACHE = er.ROOT / "datasets/research/agent_tuning"
TRAIN = (date(2024, 4, 1), date(2025, 6, 30))
VALIDATE = (date(2025, 7, 1), date(2025, 12, 31))
TEST = (date(2026, 1, 1), date(2026, 10, 5))
HORIZON_BARS = {"5m": 12, "1d": 1}
FEATURES = (
    "ema_12", "ema_26", "sma_10", "sma_20", "last_close", "vwap", "rsi_14", "macd", "macd_signal", "atr_14",
    "ema_gap_atr", "sma_gap_atr", "close_sma20_atr", "close_vwap_atr", "macd_gap_atr",
    "roc_10_z", "trend_strength_adx", "relative_strength_nifty",
    "bollinger_upper", "bollinger_lower",
    "last_volume", "volume_mean", "return_1", "relative_volume", "price_volume_corr",
)
INDEX_FEATURES = ("ema_12", "ema_26", "return_1")


# --- stage 1: features -----------------------------------------------------------------------------


def _candles(rows: list[dict]):  # type: ignore[no-untyped-def]
    from contracts.schemas.market import Candle

    return [Candle.model_validate(row) for row in rows if er.regular(er._ist(row["end"]).date())]


def _nifty_returns(frame: str) -> tuple[np.ndarray, np.ndarray]:
    bars = _candles(er._bars("NIFTY50", frame))
    ends = np.array([bar.end.timestamp() for bar in bars])
    closes = np.array([float(bar.close) for bar in bars])
    returns = np.full(len(bars), np.nan)
    returns[1:] = closes[1:] / closes[:-1] - 1
    return ends, returns


def _features_for(job: tuple[str, str]) -> str:
    symbol, frame = job
    target = CACHE / f"features-{symbol}-{frame}.npz"
    if target.exists():
        return str(target)
    import logging

    logging.disable(logging.WARNING)
    from contracts.enums import Timeframe
    from core_features.engine import build_feature_set

    timeframe = Timeframe.M5 if frame == "5m" else Timeframe.D1
    bars = _candles(er._bars(symbol, frame))
    index = symbol in ("NIFTY50", "INDIAVIX")
    nifty_ends, nifty_returns = (None, None) if index else _nifty_returns(frame)
    names = INDEX_FEATURES if index else FEATURES
    data = {name: np.full(len(bars), np.nan) for name in names}
    for i, bar in enumerate(bars):
        window = bars[max(0, i - 399) : i + 1] if frame == "5m" else bars[: i + 1]
        nifty = None
        if nifty_ends is not None:
            k = int(np.searchsorted(nifty_ends, bar.end.timestamp(), side="right")) - 1
            nifty = None if k < 0 or math.isnan(nifty_returns[k]) else float(nifty_returns[k])
        built = build_feature_set(symbol, timeframe, window, bar.end, nifty_return=nifty)
        if built is None:
            continue
        for name in names:
            value = built.features.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                data[name][i] = float(value)
    ends = np.array([bar.end.timestamp() for bar in bars])
    sessions = np.array([bar.end.astimezone(IST).date().toordinal() for bar in bars])
    closes = np.array([float(bar.close) for bar in bars])
    opens = np.array([float(bar.open) for bar in bars])
    highs = np.array([float(bar.high) for bar in bars])
    lows = np.array([float(bar.low) for bar in bars])
    clocks = np.array([bar.end.astimezone(IST).hour * 100 + bar.end.astimezone(IST).minute for bar in bars])
    np.savez_compressed(target, ends=ends, sessions=sessions, close=closes, open=opens, high=highs, low=lows, clock=clocks, **data)
    return str(target)


def stage_one(workers: int) -> None:
    er.split_snapshots()
    CACHE.mkdir(parents=True, exist_ok=True)
    jobs = [(name, frame) for frame in ("1d", "5m") for name in ("NIFTY50", "INDIAVIX", *er.stock_symbols())]
    with Pool(workers) as pool:
        for path in pool.imap_unordered(_features_for, jobs):
            print("features", Path(path).name, flush=True)


def load(symbol: str, frame: str) -> dict[str, np.ndarray]:
    with np.load(CACHE / f"features-{symbol}-{frame}.npz") as handle:
        return {key: handle[key] for key in handle.files}


# --- stage 2: agents as array code ---------------------------------------------------------------


def _score(votes: list[tuple[np.ndarray, float, np.ndarray]], present_ratio: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    """score_votes: signal = sum(v*w)/sum(w), confidence = engaged weight share x present ratio (over present votes)."""
    weight_sum = np.zeros(n)
    signed = np.zeros(n)
    engaged = np.zeros(n)
    for value, weight, present in votes:
        w = np.where(present, weight, 0.0)
        v = np.where(present, value, 0.0)
        weight_sum += w
        signed += v * w
        engaged += np.where(v != 0, w, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        signal = np.where(weight_sum > 0, signed / weight_sum, 0.0)
        confidence = np.where(weight_sum > 0, engaged / weight_sum * present_ratio, 0.0)
    return np.clip(signal, -1, 1), np.clip(confidence, 0, 1)


def _present_ratio(f: dict[str, np.ndarray], required: tuple[str, ...]) -> np.ndarray:
    return np.mean([~np.isnan(f[name]) for name in required], axis=0) if required else np.ones(len(f["close"]))


def _sign(x: np.ndarray, low: float = 0.0, high: float = 0.0) -> np.ndarray:
    return np.where(x > high, 1.0, np.where(x < low, -1.0, 0.0))


TECH_REQUIRED = ("ema_12", "ema_26", "sma_10", "sma_20", "last_close", "vwap", "rsi_14", "macd", "macd_signal")
TECH_GAPS = {
    "ema_trend": ("ema_gap_atr", 0.1, "ema_12", "ema_26", 0.15),
    "sma_trend": ("sma_gap_atr", 0.1, "sma_10", "sma_20", 0.15),
    "price_sma": ("close_sma20_atr", 0.25, "last_close", "sma_20", 0.15),
    "price_vwap": ("close_vwap_atr", 0.25, "last_close", "vwap", 0.2),
    "macd": ("macd_gap_atr", 0.02, "macd", "macd_signal", 0.2),
}


def technical(f: dict[str, np.ndarray], *, dead_scale: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    n = len(f["close"])
    votes = []
    for gap_name, band, a, b, weight in TECH_GAPS.values():
        gap = f[gap_name]
        has_gap = ~np.isnan(gap)
        band_value = band * dead_scale
        gap_vote = _sign(gap, -band_value, band_value) if dead_scale > 0 else _sign(gap)
        side_vote = _sign(f[a] - f[b])
        present = has_gap | (~np.isnan(f[a]) & ~np.isnan(f[b]))
        votes.append((np.where(has_gap, gap_vote, side_vote), weight, present))
    rsi = f["rsi_14"]
    votes.append((np.where(rsi < 30, 1.0, np.where(rsi > 70, -1.0, 0.0)), 0.15, ~np.isnan(rsi)))
    return _score(votes, _present_ratio(f, TECH_REQUIRED), n)


def momentum(f: dict[str, np.ndarray], *, noise_z: float = 0.5, adx_trend: float = 20.0) -> tuple[np.ndarray, np.ndarray]:
    n = len(f["close"])
    z = f["roc_10_z"]
    direction = np.where(np.isnan(z), 0.0, _sign(z, -noise_z, noise_z))
    adx = f["trend_strength_adx"]
    rel = f["relative_strength_nifty"]
    votes = [
        (direction, 0.45, ~np.isnan(z)),
        (np.where(adx >= adx_trend, direction, 0.0), 0.3, ~np.isnan(adx)),
        (_sign(rel), 0.25, ~np.isnan(rel)),
    ]
    return _score(votes, _present_ratio(f, ("roc_10_z",)), n)


def mean_reversion(f: dict[str, np.ndarray], *, adx_cut: float = 20.0) -> tuple[np.ndarray, np.ndarray]:
    n = len(f["close"])
    close, upper, lower, adx = f["last_close"], f["bollinger_upper"], f["bollinger_lower"], f["trend_strength_adx"]
    weak = np.isnan(adx) | (adx < adx_cut)
    votes = [
        (np.where(weak & (close < lower), 1.0, 0.0), 0.5, ~np.isnan(close) & ~np.isnan(lower)),
        (np.where(weak & (close > upper), -1.0, 0.0), 0.5, ~np.isnan(close) & ~np.isnan(upper)),
    ]
    return _score(votes, _present_ratio(f, ("last_close", "bollinger_upper", "bollinger_lower")), n)


def volume(f: dict[str, np.ndarray], *, surge: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    n = len(f["close"])
    lv, vm, ret = f["last_volume"], f["volume_mean"], f["return_1"]
    core = ~np.isnan(lv) & ~np.isnan(vm) & ~np.isnan(ret)
    direction = _sign(ret)
    heavy = lv > vm
    rel, corr = f["relative_volume"], f["price_volume_corr"]
    votes = [
        (np.where(heavy, direction, 0.0), 1.0, core),
        (np.where(rel > surge, direction, 0.0), 1.0, core & ~np.isnan(rel)),
        (np.where(rel > 3.0, direction, 0.0), 1.0, core & ~np.isnan(rel)),
        (np.where(heavy & (corr > 0.3), direction, 0.0), 1.0, core & ~np.isnan(corr)),
    ]
    return _score(votes, _present_ratio(f, ("last_volume", "volume_mean", "return_1")), n)


AGENTS = {"technical": technical, "momentum": momentum, "mean_reversion": mean_reversion, "volume": volume}
GRID: dict[str, list[dict[str, float]]] = {
    "technical": [{"dead_scale": s} for s in (0.0, 1.0, 2.0)],
    "momentum": [{"noise_z": z, "adx_trend": a} for z in (0.25, 0.5, 1.0) for a in (15.0, 20.0, 25.0)],
    "mean_reversion": [{"adx_cut": c} for c in (15.0, 20.0, 25.0, math.inf)],
    "volume": [{"surge": s} for s in (1.5, 2.0, 3.0)],
}
DEFAULTS = {"technical": {"dead_scale": 1.0}, "momentum": {"noise_z": 0.5, "adx_trend": 20.0}, "mean_reversion": {"adx_cut": 20.0}, "volume": {"surge": 2.0}}


def check_replication(frame: str, samples: int = 2000, seed: int = 0) -> dict[str, int]:
    """Compare the array agents with the real 1.3.0 agents on random bars. Returns mismatch counts."""
    import logging

    logging.disable(logging.WARNING)
    from contracts.enums import Timeframe
    from core_features.engine import build_feature_set
    from quant_agents.agents.mean_reversion import MeanReversionAgent
    from quant_agents.agents.momentum import MomentumAgent
    from quant_agents.agents.technical import TechnicalAgent
    from quant_agents.agents.volume import VolumeAgent
    from quant_agents.calendar.static_nse import StaticNseCalendar
    from quant_agents.clock import ReplayClock
    from quant_agents.feature_view import FeatureView
    from quant_agents.scoring import score_votes

    rng = random.Random(seed)
    timeframe = Timeframe.M5 if frame == "5m" else Timeframe.D1
    calendar = StaticNseCalendar()
    real = {"technical": TechnicalAgent, "momentum": MomentumAgent, "mean_reversion": MeanReversionAgent, "volume": VolumeAgent}
    mismatches = {name: 0 for name in real}
    symbols = er.stock_symbols()
    nifty_ends, nifty_returns = _nifty_returns(frame)
    per_symbol = max(1, samples // len(symbols))
    checked = 0
    for symbol in symbols:
        bars = _candles(er._bars(symbol, frame))
        f = load(symbol, frame)
        arrays = {name: AGENTS[name](f, **DEFAULTS[name]) for name in AGENTS}
        for i in rng.sample(range(60, len(bars)), min(per_symbol, len(bars) - 60)):
            window = bars[max(0, i - 399) : i + 1] if frame == "5m" else bars[: i + 1]
            k = int(np.searchsorted(nifty_ends, bars[i].end.timestamp(), side="right")) - 1
            nifty = None if k < 0 or math.isnan(nifty_returns[k]) else float(nifty_returns[k])
            built = build_feature_set(symbol, timeframe, window, bars[i].end, nifty_return=nifty)
            if built is None:
                continue
            checked += 1
            for name, cls in real.items():
                agent = cls(ReplayClock(bars[i].end), calendar)
                view = FeatureView(built)
                for feature in (*agent.required_features, *agent.optional_features):
                    view.get(feature)
                decision = agent.interpret(view, {})
                score = score_votes(decision.votes, required=agent.required_features, missing=view.missing)
                signal, confidence = arrays[name][0][i], arrays[name][1][i]
                if abs(score.signal - signal) > 1e-6 or abs(score.confidence - confidence) > 1e-6:
                    mismatches[name] += 1
    mismatches["checked"] = checked
    return mismatches


# --- stage 3: scoring ----------------------------------------------------------------------------


@dataclass
class Panel:
    frame: str
    symbols: list[str]
    stamps: np.ndarray  # sorted bar ends (epoch seconds)
    sessions: np.ndarray  # session ordinal per stamp
    clock: np.ndarray
    forward: np.ndarray  # stamps x symbols
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    features: dict[str, dict[str, np.ndarray]]  # symbol -> raw per-bar feature arrays
    index_of: dict[str, np.ndarray]  # symbol -> row index of each of its bars


def build_panel(frame: str) -> Panel:
    symbols = er.stock_symbols()
    feats = {symbol: load(symbol, frame) for symbol in symbols}
    stamps = np.unique(np.concatenate([f["ends"] for f in feats.values()]))
    pos = {value: k for k, value in enumerate(stamps)}
    shape = (len(stamps), len(symbols))
    forward = np.full(shape, np.nan)
    o, h, l, c = (np.full(shape, np.nan) for _ in range(4))
    sessions = np.zeros(len(stamps), dtype=int)
    clock = np.zeros(len(stamps), dtype=int)
    index_of: dict[str, np.ndarray] = {}
    step = HORIZON_BARS[frame]
    for j, symbol in enumerate(symbols):
        f = feats[symbol]
        rows = np.array([pos[value] for value in f["ends"]])
        index_of[symbol] = rows
        sessions[rows], clock[rows] = f["sessions"], f["clock"]
        o[rows, j], h[rows, j], l[rows, j], c[rows, j] = f["open"], f["high"], f["low"], f["close"]
        fwd = np.full(len(rows), np.nan)
        if len(rows) > step:
            later = f["close"][step:] / f["close"][:-step] - 1
            same = f["sessions"][step:] == f["sessions"][:-step] if frame == "5m" else np.ones(len(later), dtype=bool)
            fwd[:-step] = np.where(same, later, np.nan)
        forward[rows, j] = fwd
    return Panel(frame, symbols, stamps, sessions, clock, forward, o, h, l, c, feats, index_of)


def agent_matrix(panel: Panel, name: str, params: dict[str, float], *, invert: bool = False) -> tuple[np.ndarray, np.ndarray]:
    shape = (len(panel.stamps), len(panel.symbols))
    signal, confidence = np.full(shape, np.nan), np.full(shape, np.nan)
    for j, symbol in enumerate(panel.symbols):
        s, c = AGENTS[name](panel.features[symbol], **params)
        rows = panel.index_of[symbol]
        signal[rows, j], confidence[rows, j] = (-s if invert else s), c
    return signal, confidence


def _period_mask(panel: Panel, period: tuple[date, date]) -> np.ndarray:
    return (panel.sessions >= period[0].toordinal()) & (panel.sessions <= period[1].toordinal())


def cross_sectional_ic(effective: np.ndarray, forward: np.ndarray, rows: np.ndarray) -> np.ndarray:
    """Spearman correlation across stocks per row (NaN when fewer than 10 usable stocks or no variance)."""
    out = np.full(len(rows), np.nan)
    for k, r in enumerate(rows):
        x, y = effective[r], forward[r]
        ok = ~np.isnan(x) & ~np.isnan(y)
        if ok.sum() < 10:
            continue
        xr, yr = rankdata(x[ok]), rankdata(y[ok])
        if xr.std() == 0 or yr.std() == 0:
            continue
        out[k] = float(np.corrcoef(xr, yr)[0, 1])
    return out


def daily_series(values: np.ndarray, sessions: np.ndarray) -> np.ndarray:
    days = {}
    for value, day in zip(values, sessions):
        if not math.isnan(value):
            days.setdefault(day, []).append(value)
    return np.array([np.mean(days[d]) for d in sorted(days)])


def bootstrap_low(series: np.ndarray, quantile: float = 0.10) -> float:
    if len(series) < 10:
        return float("nan")
    rng = np.random.default_rng(0)
    means = [series[me.stationary_bootstrap_indices(len(series), 5.0, rng)].mean() for _ in range(2000)]
    return float(np.quantile(means, quantile))


def evaluate(panel: Panel, signal: np.ndarray, confidence: np.ndarray, period: tuple[date, date]) -> dict[str, float]:
    mask = _period_mask(panel, period)
    rows = np.where(mask)[0]
    effective = signal * confidence
    ic = cross_sectional_ic(effective, panel.forward, rows)
    daily = daily_series(ic, panel.sessions[rows])
    active = (signal[rows] != 0) & ~np.isnan(signal[rows]) & ~np.isnan(panel.forward[rows])
    s, fwd = signal[rows][active], panel.forward[rows][active]
    hits = ((s > 0) & (fwd > 0)) | ((s < 0) & (fwd < 0))
    usable = ~np.isnan(signal[rows])
    return {
        "mean_ic": float(np.nanmean(ic)) if np.isfinite(ic).any() else float("nan"),
        "daily_ic_low90": bootstrap_low(daily),
        "days": int(len(daily)),
        "hit_rate": float(hits.mean()) if len(s) else float("nan"),
        "mean_signed_bp": float((np.sign(s) * fwd).mean() * 10_000) if len(s) else float("nan"),
        "participation": float(active.sum() / max(1, usable.sum())),
        "active_signals": int(len(s)),
    }


def tune(panel: Panel) -> dict[str, object]:
    report: dict[str, object] = {}
    for name in AGENTS:
        candidates = []
        for params in GRID[name]:
            for invert in (False, True):
                s, c = agent_matrix(panel, name, params, invert=invert)
                candidates.append({"params": params, "inverted": invert, "train": evaluate(panel, s, c, TRAIN)})
        best = max(candidates, key=lambda item: item["train"]["mean_ic"] if math.isfinite(item["train"]["mean_ic"]) else -9)
        default = next(item for item in candidates if item["params"] == DEFAULTS[name] and not item["inverted"])
        s, c = agent_matrix(panel, name, best["params"], invert=best["inverted"])
        validation = evaluate(panel, s, c, VALIDATE)
        keep = bool(validation["mean_ic"] > 0 and validation["daily_ic_low90"] > 0)
        report[name] = {"default": default, "best": best, "validate": validation, "kept": keep, "grid": candidates}
        print(panel.frame, name, "best", best["params"], "inverted" if best["inverted"] else "", "train IC", round(best["train"]["mean_ic"], 4), "validate IC", round(validation["mean_ic"], 4), "keep", keep, flush=True)
    kept = {name: item for name, item in report.items() if item["kept"]}  # type: ignore[index]
    total = sum(max(0.0, item["best"]["train"]["mean_ic"]) for item in kept.values())  # type: ignore[index]
    weights = {name: (max(0.0, item["best"]["train"]["mean_ic"]) / total if total > 0 else 0.0) for name, item in kept.items()}  # type: ignore[index]
    report["weights"] = {name: weights.get(name, 0.0) for name in AGENTS}
    return report


def fused(panel: Panel, configs: dict[str, tuple[dict, bool]], weights: dict[str, float], *, old_rule: bool) -> tuple[np.ndarray, np.ndarray]:
    shape = (len(panel.stamps), len(panel.symbols))
    num, den_c, den_w = np.zeros(shape), np.zeros(shape), np.zeros(shape)
    for name, (params, invert) in configs.items():
        w = weights.get(name, 0.0)
        if w <= 0:
            continue
        s, c = agent_matrix(panel, name, params, invert=invert)
        ok = ~np.isnan(s)
        num += np.where(ok, w * s * c, 0.0)
        den_c += np.where(ok, w * c, 0.0)
        den_w += np.where(ok, w, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        signal = np.where(den_w > 0, (num / den_w) if old_rule else np.where(den_c > 0, num / den_c, 0.0), np.nan)
        confidence = np.where(den_w > 0, den_c / den_w, np.nan)
    return np.clip(signal, -1, 1), confidence


def trade(panel: Panel, signal: np.ndarray, confidence: np.ndarray, period: tuple[date, date]) -> dict[str, float]:
    """Live paper rules: enter at fused >= 0.2 & confidence >= 0.3 at the next open, -2%/+4%, signal exit, Rs 20k."""
    from core_api.strategy_lab import leg_charges

    mask = _period_mask(panel, period)
    rows_all = np.where(mask)[0]
    intraday = panel.frame == "5m"
    product = "MIS" if intraday else "CNC"
    slip = 0.0005
    session_pnl: dict[int, float] = {}
    trades = []
    for j in range(len(panel.symbols)):
        rows = [r for r in rows_all if not math.isnan(panel.close[r, j])]
        k = 0
        while k < len(rows) - 1:
            r = rows[k]
            if not (signal[r, j] >= 0.2 and confidence[r, j] >= 0.3):
                k += 1
                continue
            nxt = rows[k + 1]
            if intraday and (panel.sessions[nxt] != panel.sessions[r] or panel.clock[r] >= 1500):
                k += 1
                continue
            entry = panel.open[nxt, j] * (1 + slip)
            qty = int(20000 // entry)
            if qty < 1:
                k += 1
                continue
            stop, target = entry * 0.98, entry * 1.04
            exit_price, reason, m = None, "end", k + 1
            while m < len(rows):
                q = rows[m]
                if intraday and (panel.sessions[q] != panel.sessions[nxt] or panel.clock[q] > 1515):
                    q_prev = rows[m - 1]
                    exit_price, reason, m = panel.close[q_prev, j], "square_off", m - 1
                    break
                if panel.low[q, j] <= stop:
                    exit_price, reason = (stop if q == nxt else min(panel.open[q, j], stop)), "stop"
                    break
                if q != nxt and panel.high[q, j] >= target:
                    exit_price, reason = max(panel.open[q, j], target), "target"
                    break
                if signal[q, j] <= -0.2 and confidence[q, j] >= 0.3 and m + 1 < len(rows):
                    exit_price, reason, m = panel.open[rows[m + 1], j], "signal", m + 1
                    break
                m += 1
            if exit_price is None:
                m = len(rows) - 1
                exit_price = panel.close[rows[m], j]
            exit_price = exit_price * (1 - slip)
            net = (exit_price - entry) * qty - leg_charges(entry * qty, exit_price * qty, product)
            day = int(panel.sessions[rows[min(m, len(rows) - 1)]])
            session_pnl[day] = session_pnl.get(day, 0.0) + net
            trades.append((net, reason))
            k = m + 1
    days = sorted(set(int(d) for d in panel.sessions[rows_all]))
    series = np.array([session_pnl.get(d, 0.0) for d in days])
    nets = [t[0] for t in trades]
    return {
        "trades": len(trades),
        "total_net": float(sum(nets)),
        "win_rate": float(np.mean([n > 0 for n in nets])) if nets else float("nan"),
        "mean_net_per_trade": float(np.mean(nets)) if nets else float("nan"),
        "session_pnl_low90": bootstrap_low(series),
        "exits": {reason: sum(1 for t in trades if t[1] == reason) for reason in sorted({t[1] for t in trades})},
    }


def regime_filter(panel: Panel) -> dict[str, object]:
    nifty, vix = load("NIFTY50", panel.frame), load("INDIAVIX", panel.frame)
    n_pos = {value: k for k, value in enumerate(nifty["ends"])}
    v_pos = {value: k for k, value in enumerate(vix["ends"])}
    risk_off = np.zeros(len(panel.stamps), dtype=bool)
    for r, stamp in enumerate(panel.stamps):
        a, b = n_pos.get(stamp), v_pos.get(stamp)
        if a is not None and b is not None:
            risk_off[r] = bool(nifty["ema_12"][a] < nifty["ema_26"][a] and vix["return_1"][b] > 0)
    out = {}
    for label, period in (("train", TRAIN), ("validate", VALIDATE)):
        mask = _period_mask(panel, period)
        on = panel.forward[mask & risk_off]
        off = panel.forward[mask & ~risk_off]
        out[label] = {
            "risk_off_share": float((mask & risk_off).sum() / max(1, mask.sum())),
            "mean_forward_bp_risk_off": float(np.nanmean(on) * 10_000),
            "mean_forward_bp_other": float(np.nanmean(off) * 10_000),
        }
    return out


def run(workers: int) -> dict[str, object]:
    stage_one(workers)
    report: dict[str, object] = {"protocol": "services/quant/docs/agent-tuning-protocol.md", "periods": {"train": TRAIN, "validate": VALIDATE, "test": TEST}}
    report["replication"] = {frame: check_replication(frame) for frame in ("1d", "5m")}
    print("replication", report["replication"], flush=True)
    if any(count for frame in report["replication"].values() for name, count in frame.items() if name != "checked"):  # type: ignore[union-attr]
        report["stopped"] = "array agents do not reproduce the real agents"
        return report
    for frame, horizon in (("1d", "swing"), ("5m", "intraday")):
        panel = build_panel(frame)
        tuned = tune(panel)
        configs = {name: (tuned[name]["best"]["params"], tuned[name]["best"]["inverted"]) for name in AGENTS}  # type: ignore[index]
        defaults = {name: (DEFAULTS[name], False) for name in AGENTS}
        s_t, c_t = fused(panel, configs, tuned["weights"], old_rule=False)  # type: ignore[arg-type]
        s_d, c_d = fused(panel, defaults, {name: 1.0 for name in AGENTS}, old_rule=True)
        test = {
            "tuned": {"ic": evaluate(panel, s_t, c_t, TEST), "trading": trade(panel, s_t, c_t, TEST)},
            "baseline_1_3_0": {"ic": evaluate(panel, s_d, c_d, TEST), "trading": trade(panel, s_d, c_d, TEST)},
        }
        works = bool(
            test["tuned"]["ic"]["daily_ic_low90"] > 0
            and test["tuned"]["trading"]["total_net"] > 0
            and test["tuned"]["trading"]["session_pnl_low90"] > 0
        )
        report[horizon] = {
            "agents": {name: {k: v for k, v in tuned[name].items() if k != "grid"} for name in AGENTS},  # type: ignore[union-attr]
            "grids": {name: tuned[name]["grid"] for name in AGENTS},  # type: ignore[index]
            "weights": tuned["weights"],
            "regime_filter": regime_filter(panel),
            "test": test,
            "works": works,
        }
        print(horizon, "test", json.dumps(test, default=str), "works", works, flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path, default=er.ROOT / "services/quant/docs/results/agent-tuning-result.json")
    args = parser.parse_args()
    report = run(args.workers)
    args.out.write_text(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()

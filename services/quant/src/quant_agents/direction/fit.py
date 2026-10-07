"""One logistic regression per timeframe. Not wired into MlAgent."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

from core_features.engine import build_feature_set
from quant_agents.direction.inventory import EXCLUDED, IST, SymbolTape, load_tapes
from quant_agents.direction.rows import _candle, modeling_indexes
from quant_agents.direction.window import PURGE_BARS, model_version, window_bars
from quant_agents.ml.features import DIRECTION_COLUMNS, direction_row

TRAIN_LAST = date(2025, 6, 30)
VALID_LAST = date(2025, 12, 31)
WINSOR_COLUMNS = ("volume_ratio", "body_over_range")
BASELINE = ("last_close", "last_volume", "period_high", "period_low", "volume_mean", "vwap")
SESSIONS_72 = {
    date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5), date(2026, 8, 6), date(2026, 8, 7),
    date(2026, 8, 10), date(2026, 8, 11), date(2026, 8, 12), date(2026, 8, 13), date(2026, 8, 14),
    date(2026, 8, 17), date(2026, 8, 18), date(2026, 8, 19), date(2026, 8, 20), date(2026, 8, 21),
    date(2026, 8, 24), date(2026, 8, 25), date(2026, 8, 26), date(2026, 8, 27), date(2026, 8, 28),
    date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4),
    date(2026, 9, 7), date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10), date(2026, 9, 11),
    date(2026, 9, 15), date(2026, 9, 16), date(2026, 9, 17), date(2026, 9, 18), date(2026, 9, 21),
    date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 28),
    date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 5),
}
AUC_TRIGGER = {"5m": 0.55, "1d": 0.58}
BOOTSTRAP_DRAWS = 1000


def ist_day(stamp: datetime) -> date:
    return stamp.astimezone(IST).date()


def calendar_split(day: date) -> str:
    if day <= TRAIN_LAST:
        return "train"
    if day <= VALID_LAST:
        return "validation"
    return "test"


def purge_ends(tapes: dict[str, SymbolTape]) -> set[datetime]:
    ends = sorted(bar.end for tape in tapes.values() for bar in tape.bars)
    grouped: dict[str, list[datetime]] = {"validation": [], "test": []}
    seen: set[datetime] = set()
    for stamp in ends:
        if stamp in seen:
            continue
        seen.add(stamp)
        bucket = calendar_split(ist_day(stamp))
        if bucket in grouped:
            grouped[bucket].append(stamp)
    blocked: set[datetime] = set()
    for stamps in grouped.values():
        blocked.update(stamps[:PURGE_BARS])
    return blocked


def collect(tapes: dict[str, SymbolTape], *, purge: bool = True) -> dict[str, np.ndarray]:
    blocked = purge_ends(tapes) if purge else set()
    length = window_bars(next(tape.bars[0].timeframe for tape in tapes.values() if tape.bars))
    names = (
        "x", "baseline", "y", "day", "symbol", "first", "end", "future_end",
        "next_return", "minute", "weekday", "month",
    )
    frames: dict[str, list] = {name: [] for name in names}
    outliers: list[dict[str, object]] = []
    for symbol, tape in sorted(tapes.items()):
        if symbol == EXCLUDED or not tape.bars:
            continue
        candles = [_candle(bar) for bar in tape.bars]
        for index in modeling_indexes(tape, blocked):
            bar = tape.bars[index]
            future = tape.bars[index + 1]
            window = candles[index + 1 - length : index + 1]
            if any(item.end > bar.end for item in window):
                raise SystemExit(f"feature window passes {bar.end.isoformat()}")
            built = build_feature_set(bar.symbol, bar.timeframe, window, bar.end)
            if built is None:
                raise SystemExit(f"missing features at {bar.symbol} {bar.end.isoformat()}")
            features, reason = direction_row(
                dict(built.features),
                open_=float(bar.open),
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
            )
            if features is None:
                raise SystemExit(f"{reason} at a modeling row {bar.symbol} {bar.end.isoformat()}")
            change = float(features["return_1"])
            if abs(change) > 0.15:
                outliers.append({"symbol": symbol, "end": bar.end.isoformat(), "return_1": change})
            frames["x"].append([features[name] for name in DIRECTION_COLUMNS])
            frames["baseline"].append([float(built.features[name]) for name in BASELINE])
            frames["y"].append(1 if future.close > bar.close else 0)
            frames["day"].append(np.datetime64(bar.session_date.isoformat()))
            frames["symbol"].append(symbol)
            frames["first"].append(
                bar.timeframe == "5m" and tape.bars[index - 1].session_date != bar.session_date
            )
            frames["end"].append(bar.end)
            frames["future_end"].append(future.end)
            frames["next_return"].append(float(future.close / bar.close - 1))
            local = bar.end.astimezone(IST)
            frames["minute"].append(local.hour * 60 + local.minute)
            frames["weekday"].append(bar.session_date.weekday())
            frames["month"].append(bar.session_date.month)
    return {
        "x": np.asarray(frames["x"], dtype=np.float64),
        "baseline": np.asarray(frames["baseline"], dtype=np.float64),
        "y": np.asarray(frames["y"], dtype=np.int8),
        "day": np.asarray(frames["day"]),
        "symbol": np.asarray(frames["symbol"]),
        "first": np.asarray(frames["first"], dtype=bool),
        "end": np.asarray(frames["end"]),
        "future_end": np.asarray(frames["future_end"]),
        "next_return": np.asarray(frames["next_return"], dtype=np.float64),
        "minute": np.asarray(frames["minute"], dtype=np.int16),
        "weekday": np.asarray(frames["weekday"], dtype=np.int8),
        "month": np.asarray(frames["month"], dtype=np.int8),
        "outliers": outliers,
    }


def _winsor_bounds(train: np.ndarray) -> dict[str, tuple[float, float]]:
    bounds = {}
    for name in WINSOR_COLUMNS:
        column = DIRECTION_COLUMNS.index(name)
        low, high = np.quantile(train[:, column], [0.01, 0.99])
        bounds[name] = (float(low), float(high))
    return bounds


def _apply_winsor(values: np.ndarray, bounds: dict[str, tuple[float, float]]) -> np.ndarray:
    clipped = values.copy()
    for name, (low, high) in bounds.items():
        column = DIRECTION_COLUMNS.index(name)
        clipped[:, column] = np.clip(clipped[:, column], low, high)
    return clipped


def _fit_probabilities(x_train: np.ndarray, y_train: np.ndarray, x_valid: np.ndarray, y_valid: np.ndarray, x_test: np.ndarray) -> np.ndarray:
    scaler = StandardScaler()
    train = scaler.fit_transform(x_train)
    valid = scaler.transform(x_valid)
    test = scaler.transform(x_test)
    model = LogisticRegression(random_state=0, max_iter=500)
    model.fit(train, y_train)
    raw_valid = model.predict_proba(valid)[:, 1]
    raw_test = model.predict_proba(test)[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(raw_valid, y_valid)
    return calibrator.predict(raw_test)


def _metrics(y: np.ndarray, p: np.ndarray, train_rate: float) -> dict[str, object]:
    clipped = np.clip(p, 1e-6, 1 - 1e-6)
    train_constant = np.full(y.shape, train_rate)
    test_rate = float(y.mean()) if len(y) else 0.0
    test_constant = np.full(y.shape, np.clip(test_rate, 1e-6, 1 - 1e-6))
    model_loss = float(log_loss(y, clipped, labels=[0, 1]))
    train_loss = float(log_loss(y, train_constant, labels=[0, 1]))
    return {
        "rows": int(len(y)),
        "up": int(y.sum()),
        "log_loss": model_loss,
        "train_rate_log_loss": train_loss,
        "log_loss_minus_train_rate": model_loss - train_loss,
        "test_rate_log_loss": float(log_loss(y, test_constant, labels=[0, 1])),
        "accuracy": float(accuracy_score(y, clipped >= 0.5)),
        "majority_accuracy": float(max(test_rate, 1 - test_rate)),
        "auc": float(roc_auc_score(y, clipped)) if len(np.unique(y)) > 1 else None,
        "brier": float(brier_score_loss(y, clipped)),
        "calibration_curve": _curve(y, clipped),
    }


def _curve(y: np.ndarray, p: np.ndarray) -> list[dict[str, float]]:
    bins = np.linspace(0, 1, 11)
    curve = []
    for left, right in zip(bins[:-1], bins[1:], strict=True):
        mask = (p >= left) & (p < right if right < 1 else p <= right)
        if not np.any(mask):
            continue
        curve.append(
            {
                "bin_left": float(left),
                "bin_right": float(right),
                "mean_predicted": float(p[mask].mean()),
                "fraction_up": float(y[mask].mean()),
                "rows": int(mask.sum()),
            }
        )
    return curve


def _bootstrap(y: np.ndarray, p: np.ndarray, days: np.ndarray, train_rate: float, samples: int = BOOTSTRAP_DRAWS) -> dict[str, float]:
    clipped = np.clip(p, 1e-6, 1 - 1e-6)
    nll = -(y * np.log(clipped) + (1 - y) * np.log(1 - clipped))
    rate = float(np.clip(train_rate, 1e-6, 1 - 1e-6))
    base = -(y * np.log(rate) + (1 - y) * np.log(1 - rate))
    _unique, inverse = np.unique(days, return_inverse=True)
    order = np.argsort(inverse, kind="mergesort")
    inverse_sorted = inverse[order]
    cuts = np.flatnonzero(np.diff(inverse_sorted)) + 1
    starts = np.r_[0, cuts]
    nll_sums = np.add.reduceat(nll[order], starts)
    base_sums = np.add.reduceat(base[order], starts)
    counts = np.diff(np.r_[starts, len(inverse_sorted)]).astype(np.float64)
    rng = np.random.default_rng(0)
    pick = rng.integers(0, len(counts), size=(samples, len(counts)))
    totals = counts[pick].sum(axis=1)
    diffs = nll_sums[pick].sum(axis=1) / totals - base_sums[pick].sum(axis=1) / totals
    return {
        "samples": int(samples),
        "mean_log_loss_minus_train_rate": float(diffs.mean()),
        "p2_5": float(np.quantile(diffs, 0.025)),
        "p97_5": float(np.quantile(diffs, 0.975)),
    }


def _per_symbol(y: np.ndarray, p: np.ndarray, symbols: np.ndarray) -> list[dict[str, object]]:
    rows = []
    for symbol in sorted(set(symbols.tolist())):
        mask = symbols == symbol
        target = y[mask]
        score = p[mask]
        auc = None
        if len(np.unique(target)) > 1:
            auc = float(roc_auc_score(target, score))
        rows.append(
            {
                "symbol": symbol,
                "rows": int(mask.sum()),
                "accuracy": float(accuracy_score(target, score >= 0.5)),
                "auc": auc,
            }
        )
    return rows


def evaluate(frame: dict[str, np.ndarray], timeframe: str) -> dict[str, object]:
    days = [ist_day(stamp) for stamp in frame["end"]]
    day = np.array(days, dtype="datetime64[D]")
    split = np.array([calendar_split(item) for item in days])
    train = split == "train"
    valid = split == "validation"
    test = split == "test"
    bounds = _winsor_bounds(frame["x"][train])
    x = _apply_winsor(frame["x"], bounds)
    probability = _fit_probabilities(x[train], frame["y"][train], x[valid], frame["y"][valid], x[test])
    baseline_probability = _fit_probabilities(
        frame["baseline"][train],
        frame["y"][train],
        frame["baseline"][valid],
        frame["y"][valid],
        frame["baseline"][test],
    )
    train_rate = float(np.clip(frame["y"][train].mean(), 1e-6, 1 - 1e-6))
    y_test = frame["y"][test]
    full = _metrics(y_test, probability, train_rate)
    short = np.array(sorted(SESSIONS_72), dtype="datetime64[D]")
    without = ~np.isin(day[test], short)
    held_out = _metrics(y_test[without], probability[without], train_rate)
    first = frame["first"][test]
    trigger = full["auc"] is not None and full["auc"] > AUC_TRIGGER[timeframe]
    return {
        "model_version": model_version(timeframe),
        "model": "sklearn.linear_model.LogisticRegression",
        "calibration": "isotonic fit on validation only",
        "winsor_bounds": bounds,
        "train_up_rate": train_rate,
        "p_up_meaning": "probability the next valid candle closes higher, not the probability of a profitable trade",
        "signal_mapping_frozen": False,
        "auc_trigger": AUC_TRIGGER[timeframe],
        "auc_trigger_fired": trigger,
        "test_with_72_bar_sessions": full,
        "test_without_72_bar_sessions": held_out,
        "six_raw_column_baseline": _metrics(y_test, baseline_probability, train_rate),
        "day_bootstrap": _bootstrap(y_test, probability, frame["day"][test], train_rate),
        "first_bar_slice": _metrics(y_test[first], probability[first], train_rate) if np.any(first) else None,
        "per_symbol": _per_symbol(y_test, probability, frame["symbol"][test]),
    }


def return_outliers(tapes: dict[str, SymbolTape]) -> list[dict[str, object]]:
    found = []
    blocked = purge_ends(tapes)
    for symbol, tape in tapes.items():
        if symbol == EXCLUDED or len(tape.bars) < 2:
            continue
        for index in modeling_indexes(tape, blocked):
            previous = tape.bars[index - 1].close
            if previous == 0:
                continue
            change = float(tape.bars[index].close / previous - 1)
            if abs(change) > 0.15:
                found.append({"symbol": symbol, "end": tape.bars[index].end.isoformat(), "return_1": change})
    found.sort(key=lambda row: abs(float(row["return_1"])), reverse=True)
    return found

"""Re-audit of the 5-minute result. No gradient boosting and no test-set selection.

The next label is chosen from pre-specified candidates by uncalibrated validation
log-loss only. Test rows are not scored for that choice.
"""

from __future__ import annotations

from datetime import date

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from core_features.engine import build_feature_set
from quant_agents.direction.fit import (
    BOOTSTRAP_DRAWS,
    SESSIONS_72,
    _apply_winsor,
    _bootstrap,
    _winsor_bounds,
    ist_day,
)
from quant_agents.direction.inventory import EXCLUDED, SymbolTape
from quant_agents.direction.review import (
    TOD_BUCKETS,
    _fit_raw,
    _one_fold,
    _score,
    time_of_day_bucket,
)
from quant_agents.direction.rows import FIVE_MINUTES, _candle, modeling_indexes
from quant_agents.direction.window import window_bars
from quant_agents.ml.features import DIRECTION_COLUMNS, direction_row

# Cost ladder and label thresholds, stated before any measured edge.
COST_LADDER_BPS = (1.0, 2.0, 3.0, 5.0)
COST_THRESHOLD_BPS = 5.0
VOL_MULTIPLE = 0.25
TARGET_PREFERENCE = ("horizon_6", "horizon_12", "return_above_5bps", "volatility_scaled")
REVERSAL_COLUMNS = ("return_1", "close_position", "body_over_range")
Q3_START = date(2026, 7, 1)
AUGUST = date(2026, 8, 1)
OCTOBER = date(2026, 10, 1)


def freeze_target(validation_gap: dict[str, float]) -> str:
    """Most negative validation gap. A tie keeps the earlier name in TARGET_PREFERENCE."""
    return min(TARGET_PREFERENCE, key=lambda name: (validation_gap[name], TARGET_PREFERENCE.index(name)))


def final_two_usable(symbol: np.ndarray, day: np.ndarray, minute: np.ndarray) -> np.ndarray:
    """The last two rows of each symbol session in this scored set."""
    flag = np.zeros(len(symbol), dtype=bool)
    if len(symbol) == 0:
        return flag
    codes = np.unique(symbol, return_inverse=True)[1]
    day_int = day.astype("datetime64[D]").astype(np.int64)
    order = np.lexsort((minute, day_int, codes))
    sorted_codes = codes[order]
    sorted_days = day_int[order]
    change = np.flatnonzero((np.diff(sorted_codes) != 0) | (np.diff(sorted_days) != 0)) + 1
    starts = np.r_[0, change]
    ends = np.r_[change, len(order)]
    for start, end in zip(starts, ends, strict=True):
        flag[order[max(start, end - 2) : end]] = True
    return flag


def decile_edges(probability: np.ndarray, next_return: np.ndarray) -> list[dict[str, object]]:
    """Equal-count p_up deciles. Position is long when that row's p_up is at least 0.5."""
    order = np.argsort(probability, kind="mergesort")
    bins = np.array_split(order, 10)
    rows = []
    bps = next_return * 10000
    for number, index in enumerate(bins, start=1):
        if len(index) == 0:
            continue
        position = np.where(probability[index] >= 0.5, 1.0, -1.0)
        gross = float((position * bps[index]).mean())
        rows.append(
            {
                "decile": number,
                "rows": int(len(index)),
                "mean_p_up": float(probability[index].mean()),
                "mean_next_return_bps": float(bps[index].mean()),
                "gross_edge_bps": gross,
                "net_of_cost_bps": {str(cost): gross - cost for cost in COST_LADDER_BPS},
                "clears_cost_bps": [cost for cost in COST_LADDER_BPS if gross > cost],
            }
        )
    return rows


def bucket_edges(probability: np.ndarray, next_return: np.ndarray, minute: np.ndarray) -> list[dict[str, object]]:
    bps = next_return * 10000
    position = np.where(probability >= 0.5, 1.0, -1.0)
    names = np.array([time_of_day_bucket(int(value)) for value in minute])
    rows = []
    for name in [label for _left, _right, label in TOD_BUCKETS]:
        mask = names == name
        if not np.any(mask):
            continue
        gross = float((position[mask] * bps[mask]).mean())
        rows.append(
            {
                "bucket": name,
                "rows": int(mask.sum()),
                "mean_p_up": float(probability[mask].mean()),
                "mean_next_return_bps": float(bps[mask].mean()),
                "gross_edge_bps": gross,
                "net_of_cost_bps": {str(cost): gross - cost for cost in COST_LADDER_BPS},
                "clears_cost_bps": [cost for cost in COST_LADDER_BPS if gross > cost],
            }
        )
    return rows


def range_proxy(tapes: dict[str, SymbolTape]) -> dict[str, object]:
    """Median (high-low)/close of stored 5-minute bars. This is the bar range, not a quoted spread."""
    rows = []
    for symbol, tape in sorted(tapes.items()):
        if symbol == EXCLUDED or not tape.bars:
            continue
        ratios = np.array(
            [(float(bar.high) - float(bar.low)) / float(bar.close) for bar in tape.bars if bar.close != 0],
            dtype=np.float64,
        )
        rows.append(
            {
                "symbol": symbol,
                "bars": int(len(ratios)),
                "median_range_bps": float(np.median(ratios) * 10000),
            }
        )
    medians = np.array([row["median_range_bps"] for row in rows])
    return {
        "definition": "median (high-low)/close of each symbol's stored 5-minute bars, in bps. Bar range, not the bid-ask spread.",
        "symbols": len(rows),
        "median_across_symbols_bps": float(np.median(medians)),
        "mean_across_symbols_bps": float(medians.mean()),
        "min_bps": float(medians.min()),
        "max_bps": float(medians.max()),
        "per_symbol": rows,
    }


def period_slice(detail: dict[str, np.ndarray], train_rate: float, start: date, end: date) -> dict[str, object]:
    day = detail["day"]
    mask = (day >= np.datetime64(start)) & (day < np.datetime64(end))
    return _slice_metrics(detail, train_rate, mask, f"{start.isoformat()} to {end.isoformat()}")


def _slice_metrics(detail: dict[str, np.ndarray], train_rate: float, mask: np.ndarray, label: str) -> dict[str, object]:
    scored = _score(detail["y"][mask], detail["probability"][mask], train_rate)
    last_two = final_two_usable(detail["symbol"][mask], detail["day"][mask], detail["minute"][mask])
    kept = ~last_two
    without = _score(detail["y"][mask][kept], detail["probability"][mask][kept], train_rate)
    return {
        "period": label,
        "with_final_two_usable_bars": scored,
        "without_final_two_usable_bars": without,
        "final_two_rows": int(last_two.sum()),
    }


def short_session_window_check(tapes: dict[str, SymbolTape]) -> dict[str, object]:
    """Compare labels and features when 72-bar sessions are removed from the lookback."""
    length = window_bars("5m")
    retained = 0
    label_uses_short_session = 0
    windows_touching_short_session = 0
    feature_rows_compared = 0
    feature_rows_changed = 0
    max_abs_diff = 0.0
    for symbol, tape in sorted(tapes.items()):
        if symbol == EXCLUDED or not tape.bars:
            continue
        print(f"window check {symbol}", flush=True)
        bars = tape.bars
        short = {index for index, bar in enumerate(bars) if bar.session_date in SESSIONS_72}
        for index in modeling_indexes(tape):
            if bars[index].session_date in SESSIONS_72:
                continue
            retained += 1
            future = index + 1
            if future < len(bars) and bars[future].session_date in SESSIONS_72:
                label_uses_short_session += 1
            lookback = range(index + 1 - length, index + 1)
            if not any(item in short for item in lookback):
                continue
            windows_touching_short_session += 1
            original = _feature_vector(bars, list(lookback))
            alternate_index = _refilled_window(index, short, length)
            if alternate_index is None or original is None:
                feature_rows_changed += 1
                continue
            alternate = _feature_vector(bars, alternate_index)
            feature_rows_compared += 1
            if alternate is None:
                feature_rows_changed += 1
                continue
            diff = float(np.max(np.abs(original - alternate)))
            max_abs_diff = max(max_abs_diff, diff)
            if diff > 0:
                feature_rows_changed += 1
    return {
        "retained_modeling_rows_outside_72_bar_sessions": retained,
        "labels_whose_next_bar_is_inside_a_72_bar_session": label_uses_short_session,
        "windows_that_include_a_72_bar_session": windows_touching_short_session,
        "feature_rows_compared": feature_rows_compared,
        "feature_rows_changed_when_short_sessions_are_skipped": feature_rows_changed,
        "max_abs_feature_difference": max_abs_diff,
        "labels_identical": label_uses_short_session == 0,
        "features_identical": feature_rows_changed == 0,
    }


def validation_diagnosis(frame: dict[str, np.ndarray], train: np.ndarray, valid: np.ndarray) -> dict[str, object]:
    """Train-only logistics. Validation gap only, so this does not score the test set."""
    specs = {
        "return_1": ("return_1",),
        "return_1_close_position_body_over_range": REVERSAL_COLUMNS,
        "all_features": DIRECTION_COLUMNS,
    }
    report = {}
    for name, columns in specs.items():
        report[name] = _validation_fit(frame, train, valid, columns)
    signs = report["return_1_close_position_body_over_range"]["coefficients"]
    report["reading"] = (
        "A negative coefficient predicts a lower probability that the next bar closes up. "
        "Negative close_position or body_over_range is a one-bar reversal. "
        "A positive return_1 coefficient is continuation."
    )
    report["return_1_only_sign"] = _sign(report["return_1"]["coefficients"]["return_1"])
    report["return_1_sign_in_the_three_feature_model"] = _sign(signs["return_1"])
    report["close_position_sign"] = _sign(signs["close_position"])
    report["body_over_range_sign"] = _sign(signs["body_over_range"])
    return report


def candidate_targets(
    frame: dict[str, np.ndarray],
    forward_6: np.ndarray,
    forward_12: np.ndarray,
    train: np.ndarray,
    valid: np.ndarray,
) -> dict[str, object]:
    """Score pre-specified labels on validation. The test mask is not used."""
    if np.any(train & valid):
        raise SystemExit("train and validation overlap")
    if len(forward_6) != len(frame["y"]) or len(forward_12) != len(frame["y"]):
        raise SystemExit("forward-return rows do not match the feature frame")
    valid_days = [ist_day(stamp) for stamp, keep in zip(frame["end"], valid, strict=True) if keep]
    if valid_days and max(valid_days) > date(2025, 12, 31):
        raise SystemExit("validation candidate scoring reached a test date")
    moves = {
        "horizon_6": forward_6,
        "horizon_12": forward_12,
        "return_above_5bps": frame["next_return"],
        "volatility_scaled": frame["next_return"],
    }
    labels = {
        "horizon_6": _direction(forward_6),
        "horizon_12": _direction(forward_12),
        "return_above_5bps": _threshold(frame["next_return"], COST_THRESHOLD_BPS / 10000),
        "volatility_scaled": _threshold(frame["next_return"], VOL_MULTIPLE * frame["x"][:, DIRECTION_COLUMNS.index("atr_over_close")]),
    }
    gaps = {}
    rows = []
    for name in TARGET_PREFERENCE:
        scored = _label_gap(frame, labels[name], moves[name], train, valid, name)
        gaps[name] = scored["validation_gap"]
        rows.append(scored)
    return {
        "frozen_on": "validation",
        "test_scored": False,
        "feature_set": list(REVERSAL_COLUMNS),
        "thresholds_stated_first": {
            "return_above_5bps": COST_THRESHOLD_BPS,
            "volatility_scaled_multiple_of_atr_over_close": VOL_MULTIPLE,
        },
        "selection_rule": "Lowest uncalibrated validation log-loss gap. Ties keep horizon_6, horizon_12, return_above_5bps, then volatility_scaled. The 1-bar direction label is not a candidate.",
        "candidates": rows,
        "frozen_target": freeze_target(gaps),
    }


def _validation_fit(frame: dict[str, np.ndarray], train: np.ndarray, valid: np.ndarray, columns: tuple[str, ...]) -> dict[str, object]:
    picked = [DIRECTION_COLUMNS.index(name) for name in columns]
    winsor = _apply_winsor(frame["x"], _winsor_bounds(frame["x"][train]))
    values = winsor[:, picked]
    fitted = _fit_raw(values[train], frame["y"][train], (values[valid],))
    train_rate = float(frame["y"][train].mean())
    scored = _score(frame["y"][valid], fitted["raw"][0], train_rate)
    coefficients = {
        name: float(value)
        for name, value in zip(columns, fitted["model"].coef_[0], strict=True)
    }
    return {"validation": scored, "coefficients": coefficients}


def _label_gap(frame, label: np.ndarray, move: np.ndarray, train: np.ndarray, valid: np.ndarray, name: str) -> dict[str, object]:
    known = np.isfinite(label)
    train_rows = train & known
    valid_rows = valid & known
    if len(np.unique(label[train_rows])) < 2 or int(valid_rows.sum()) < 50:
        raise SystemExit(f"{name} does not have a usable validation label")
    y = label[train_rows].astype(np.int8)
    y_valid = label[valid_rows].astype(np.int8)
    picked = [DIRECTION_COLUMNS.index(column) for column in REVERSAL_COLUMNS]
    values = frame["x"][:, picked].copy()
    local = REVERSAL_COLUMNS.index("body_over_range")
    low, high = np.quantile(values[train_rows, local], [0.01, 0.99])
    values[:, local] = np.clip(values[:, local], low, high)
    fitted = _fit_raw(values[train_rows], y, (values[valid_rows],))
    train_rate = float(y.mean())
    scored = _score(y_valid, fitted["raw"][0], train_rate)
    return {
        "name": name,
        "train_rows": int(train_rows.sum()),
        "validation_rows": int(valid_rows.sum()),
        "validation_gap": scored["log_loss_minus_train_rate"],
        "validation_log_loss": scored["log_loss"],
        "validation_auc": scored["auc"],
        "mean_abs_labeled_move_bps": float(np.mean(np.abs(move[valid_rows])) * 10000),
        "coefficients": {
            column: float(value)
            for column, value in zip(REVERSAL_COLUMNS, fitted["model"].coef_[0], strict=True)
        },
    }


def _forward_returns(tapes: dict[str, SymbolTape]) -> dict[str, np.ndarray]:
    horizons = {6: [], 12: []}
    for symbol, tape in sorted(tapes.items()):
        if symbol == EXCLUDED or not tape.bars:
            continue
        bars = tape.bars
        for index in modeling_indexes(tape):
            horizons[6].append(_horizon_return(bars, index, 6))
            horizons[12].append(_horizon_return(bars, index, 12))
    return {
        "horizon_6": np.asarray(horizons[6], dtype=np.float64),
        "horizon_12": np.asarray(horizons[12], dtype=np.float64),
    }


def _horizon_return(bars, index: int, steps: int) -> float:
    cursor = index
    for _ in range(steps):
        nxt = cursor + 1
        if nxt >= len(bars) or bars[nxt].end - bars[cursor].end != FIVE_MINUTES:
            return np.nan
        cursor = nxt
    if bars[cursor].close == 0:
        return np.nan
    return float(bars[cursor].close / bars[index].close - 1)


def _direction(forward: np.ndarray) -> np.ndarray:
    label = np.full(forward.shape, np.nan)
    label[forward > 0] = 1
    label[forward < 0] = 0
    return label


def _threshold(forward: np.ndarray, limit: np.ndarray | float) -> np.ndarray:
    label = np.full(np.shape(forward), np.nan)
    label[forward > limit] = 1
    label[forward < -limit] = 0
    return label


def _feature_vector(bars, indexes: list[int]) -> np.ndarray | None:
    window = [_candle(bars[index]) for index in indexes]
    bar = bars[indexes[-1]]
    built = build_feature_set(bar.symbol, bar.timeframe, window, bar.end)
    if built is None:
        return None
    features, _reason = direction_row(
        dict(built.features),
        open_=float(bar.open),
        high=float(bar.high),
        low=float(bar.low),
        close=float(bar.close),
    )
    if features is None:
        return None
    return np.array([features[name] for name in DIRECTION_COLUMNS], dtype=np.float64)


def _refilled_window(index: int, short: set[int], length: int) -> list[int] | None:
    chosen = []
    cursor = index
    while cursor >= 0 and len(chosen) < length:
        if cursor not in short:
            chosen.append(cursor)
        cursor -= 1
    if len(chosen) < length:
        return None
    chosen.reverse()
    return chosen


def every_bar_edge(probability: np.ndarray, forward_return: np.ndarray) -> dict[str, object]:
    """Long when p_up is at least 0.5. Every finite forward return is a trade, including small ones."""
    known = np.isfinite(forward_return) & np.isfinite(probability)
    position = np.where(probability[known] >= 0.5, 1.0, -1.0)
    gross = float((position * forward_return[known] * 10000).mean()) if np.any(known) else None
    return _edge_block(gross, int(known.sum()), int((~known).sum()))


def three_class_edge(up_probability: np.ndarray, down_probability: np.ndarray, forward_return: np.ndarray) -> dict[str, object]:
    """Same every-bar rule: long when P(up) >= P(down). Flat predictions do not skip the bar."""
    known = np.isfinite(forward_return) & np.isfinite(up_probability) & np.isfinite(down_probability)
    position = np.where(up_probability[known] >= down_probability[known], 1.0, -1.0)
    gross = float((position * forward_return[known] * 10000).mean()) if np.any(known) else None
    return _edge_block(gross, int(known.sum()), int((~known).sum()))


STOP_SENTENCE = "no tradable edge at this horizon with OHLCV features"


def volatility_drop_share(frame: dict[str, np.ndarray], train: np.ndarray, valid: np.ndarray) -> dict[str, object]:
    """Share of rows the volatility-scaled label drops. The test split is not counted."""
    limit = VOL_MULTIPLE * frame["x"][:, DIRECTION_COLUMNS.index("atr_over_close")]
    kept = np.abs(frame["next_return"]) > limit
    report = {}
    for name, mask in (("train", train), ("validation", valid)):
        rows = int(mask.sum())
        retained = int((mask & kept).sum())
        report[name] = {
            "rows": rows,
            "kept": retained,
            "dropped": rows - retained,
            "share_dropped": (rows - retained) / rows if rows else None,
        }
    report["test_counted"] = False
    report["threshold"] = f"keep only when |next return| > {VOL_MULTIPLE} * atr_over_close"
    return report


def target_selection(
    frame: dict[str, np.ndarray],
    forward_6: np.ndarray,
    forward_12: np.ndarray,
    train: np.ndarray,
    valid: np.ndarray,
) -> dict[str, object]:
    """Validation-only target check. Log-loss is reported. Selection uses net bps at 2."""
    if np.any(train & valid):
        raise SystemExit("train and validation overlap")
    valid_days = [ist_day(stamp) for stamp, keep in zip(frame["end"], valid, strict=True) if keep]
    if valid_days and max(valid_days) > date(2025, 12, 31):
        raise SystemExit("target selection reached a test date")
    moves = {
        "horizon_6": forward_6,
        "horizon_12": forward_12,
        "return_above_5bps": frame["next_return"],
        "volatility_scaled": frame["next_return"],
    }
    limits = {
        "return_above_5bps": COST_THRESHOLD_BPS / 10000,
        "volatility_scaled": VOL_MULTIPLE * frame["x"][:, DIRECTION_COLUMNS.index("atr_over_close")],
    }
    labels = {
        "horizon_6": _direction(forward_6),
        "horizon_12": _direction(forward_12),
        "return_above_5bps": _threshold(frame["next_return"], limits["return_above_5bps"]),
        "volatility_scaled": _threshold(frame["next_return"], limits["volatility_scaled"]),
    }
    binary = []
    edges = []
    for name in TARGET_PREFERENCE:
        block = _binary_candidate(frame, labels[name], moves[name], train, valid, name)
        binary.append(block)
        edges.append(block["every_bar"])
    three = []
    for name, limit in limits.items():
        block = _three_class_candidate(frame, moves[name], limit, train, valid, f"three_class_{name}")
        three.append(block)
        edges.append(block["every_bar"])
    stopped = no_tradable_edge(edges)
    return {
        "frozen_target": None,
        "volatility_scaled_frozen": False,
        "test_scored": False,
        "selection_metric": "validation every-bar net edge at 2 bps",
        "bar_range_statistic": {
            "name": "median 5-minute bar range",
            "median_across_symbols_bps": 17.47973939297632,
            "definition": "Median (high-low)/close of each symbol's stored 5-minute bars, then the median across symbols. This is a range, not a spread.",
        },
        "cost_grid_bps": list(COST_LADDER_BPS),
        "volatility_scaled_drop_share": volatility_drop_share(frame, train, valid),
        "binary_candidates": binary,
        "three_class": three,
        "stopped": stopped,
        "decision": STOP_SENTENCE if stopped else "a candidate has positive validation net edge at 2 bps",
    }


def _binary_candidate(frame, label, move, train, valid, name: str) -> dict[str, object]:
    known = np.isfinite(label)
    train_rows = train & known
    valid_rows = valid & known
    y = label[train_rows].astype(np.int8)
    y_valid = label[valid_rows].astype(np.int8)
    values = _reversal_matrix(frame, train_rows)
    fitted = _fit_raw(values[train_rows], y, (values[valid_rows], values[valid]))
    train_rate = float(y.mean())
    scored = _score(y_valid, fitted["raw"][0], train_rate)
    return {
        "name": name,
        "validation_gap": scored["log_loss_minus_train_rate"],
        "validation_log_loss": scored["log_loss"],
        "validation_auc": scored["auc"],
        "day_bootstrap": _bootstrap(y_valid, fitted["raw"][0], frame["day"][valid_rows], train_rate, BOOTSTRAP_DRAWS),
        "every_bar": every_bar_edge(fitted["raw"][1], move[valid]),
    }


def _three_class_candidate(frame, move, limit, train, valid, name: str) -> dict[str, object]:
    path = np.isfinite(move)
    y = np.ones(len(move), dtype=np.int8)
    y[move < -limit] = 0
    y[move > limit] = 2
    values = _reversal_matrix(frame, train & path)
    model_fit = _fit_raw_classes(values[train & path], y[train & path], values[valid & path])
    classes = list(model_fit["model"].classes_)
    up = model_fit["proba"][:, classes.index(2)]
    down = model_fit["proba"][:, classes.index(0)]
    return {
        "name": name,
        "classes": "down, flat, up",
        "threshold": "5 bps" if np.ndim(limit) == 0 else f"{VOL_MULTIPLE} * atr_over_close",
        "validation_rows": int((valid & path).sum()),
        "validation_class_share": _class_share(y[valid & path]),
        "every_bar": three_class_edge(up, down, move[valid]),
    }


def _class_share(labels: np.ndarray) -> dict[str, float]:
    rows = len(labels)
    return {
        "down": float(np.mean(labels == 0)) if rows else None,
        "flat": float(np.mean(labels == 1)) if rows else None,
        "up": float(np.mean(labels == 2)) if rows else None,
    }


def _reversal_matrix(frame: dict[str, np.ndarray], train_rows: np.ndarray) -> np.ndarray:
    picked = [DIRECTION_COLUMNS.index(column) for column in REVERSAL_COLUMNS]
    values = frame["x"][:, picked].copy()
    local = REVERSAL_COLUMNS.index("body_over_range")
    low, high = np.quantile(values[train_rows, local], [0.01, 0.99])
    values[:, local] = np.clip(values[:, local], low, high)
    return values


def _fit_raw_classes(x_train: np.ndarray, y_train: np.ndarray, x_valid: np.ndarray) -> dict[str, object]:
    scaler = StandardScaler()
    train = scaler.fit_transform(x_train)
    model = LogisticRegression(random_state=0, max_iter=500)
    model.fit(train, y_train)
    proba = model.predict_proba(scaler.transform(x_valid))
    return {"model": model, "proba": proba}


def no_tradable_edge(edges: list[dict[str, object]]) -> bool:
    """True when every candidate's every-bar net edge at 2 bps is missing or not positive."""
    for edge in edges:
        net = edge.get("net_edge_bps", {})
        if net.get("2.0", -1) > 0:
            return False
    return True


def _edge_block(gross: float | None, trades: int, missing_forward: int) -> dict[str, object]:
    nets = None if gross is None else {str(cost): gross - cost for cost in COST_LADDER_BPS}
    return {
        "trades": trades,
        "bars_without_a_forward_path": missing_forward,
        "gross_edge_bps": gross,
        "net_edge_bps": nets,
        "positive_net_at_2_bps": False if gross is None else gross > 2.0,
    }


def _sign(value: float) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "zero"


def q3_reaudit(frame: dict[str, np.ndarray]) -> dict[str, object]:
    """Walk-forward probabilities for July versus the later short-session months."""
    day = np.array([ist_day(stamp) for stamp in frame["end"]], dtype="datetime64[D]")
    future_day = np.array([ist_day(stamp) for stamp in frame["future_end"]], dtype="datetime64[D]")
    q3 = _one_fold(frame, day, future_day, Q3_START, OCTOBER, "isotonic", keep_probabilities=True)
    q4 = _one_fold(frame, day, future_day, OCTOBER, date(2027, 1, 1), "isotonic", keep_probabilities=True)
    detail = q3["detail"]
    rate = float(q3["train_up_rate"])
    whole = _slice_metrics(detail, rate, np.ones(len(detail["y"]), dtype=bool), "2026 Q3 fold")
    july = period_slice(detail, rate, Q3_START, AUGUST)
    august_september = period_slice(detail, rate, AUGUST, OCTOBER)
    october_detail = q4["detail"]
    october = _slice_metrics(october_detail, float(q4["train_up_rate"]), np.ones(len(october_detail["y"]), dtype=bool), "2026-10 fold")
    return {
        "model": "walk-forward isotonic, the same fold that produced the 0.552 AUC",
        "q3_fold": {key: value for key, value in q3.items() if key != "detail"},
        "q3_with_and_without_final_two_bars": whole,
        "july": july,
        "august_through_september": august_september,
        "october_own_fold": {key: value for key, value in q4.items() if key != "detail"} | {"slice": october},
        "final_two_definition": "The last two modeling rows of each symbol session in the scored set. On a 75-bar session those bars end at 15:20 and 15:25 IST. On a 72-bar session they end at 15:05 and 15:10 IST.",
    }


def validation_economics(frame: dict[str, np.ndarray], train: np.ndarray, valid: np.ndarray) -> dict[str, object]:
    """Uncalibrated validation probabilities. Not a test-set ranking of deciles."""
    winsor = _apply_winsor(frame["x"], _winsor_bounds(frame["x"][train]))
    probability = _fit_raw(winsor[train], frame["y"][train], (winsor[valid],))["raw"][0]
    deciles = decile_edges(probability, frame["next_return"][valid])
    buckets = bucket_edges(probability, frame["next_return"][valid], frame["minute"][valid])
    return {
        "probability": "uncalibrated logistic fit on the fixed train split, scored on validation only",
        "position_rule": "long when p_up >= 0.5, otherwise short",
        "cost_ladder_bps": list(COST_LADDER_BPS),
        "deciles": deciles,
        "time_of_day": buckets,
        "any_decile_clears_cost_bps": {str(cost): any(cost in row["clears_cost_bps"] for row in deciles) for cost in COST_LADDER_BPS},
        "any_time_of_day_bucket_clears_cost_bps": {str(cost): any(cost in row["clears_cost_bps"] for row in buckets) for cost in COST_LADDER_BPS},
    }

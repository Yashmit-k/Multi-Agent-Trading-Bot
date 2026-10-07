"""Review of the logistic fits. No new model family and no test-set selection.

The daily primary probability is Platt scaling fit on validation. Ablation features
are chosen by uncalibrated validation log-loss. The walk-forward refits each quarter
on earlier rows only.
"""

from __future__ import annotations

from datetime import date

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

from quant_agents.direction.fit import (
    BOOTSTRAP_DRAWS,
    SESSIONS_72,
    WINSOR_COLUMNS,
    _apply_winsor,
    _bootstrap,
    _winsor_bounds,
    ist_day,
    purge_ends,
)
from quant_agents.direction.inventory import SymbolTape
from quant_agents.direction.window import PURGE_BARS
from quant_agents.ml.features import DIRECTION_COLUMNS

# Stated before any conditional next-bar return is computed.
ROUND_TRIP_COST_BPS = 5.0
PRIMARY_CALIBRATION = {"1d": "platt", "5m": "isotonic"}
TOD_BUCKETS = (
    (9 * 60 + 15, 10 * 60 + 15, "09:15-10:15"),
    (10 * 60 + 15, 11 * 60 + 15, "10:15-11:15"),
    (11 * 60 + 15, 12 * 60 + 15, "11:15-12:15"),
    (12 * 60 + 15, 13 * 60 + 15, "12:15-13:15"),
    (13 * 60 + 15, 14 * 60 + 15, "13:15-14:15"),
    (14 * 60 + 15, 15 * 60 + 15, "14:15-15:15"),
    (15 * 60 + 15, 15 * 60 + 30, "15:15-15:30"),
)


def split_keep(frame: dict[str, np.ndarray], tapes: dict[str, SymbolTape]) -> np.ndarray:
    """Drop the same purged timestamps the fixed train/validation/test split uses."""
    blocked = purge_ends(tapes)
    ends = frame["end"]
    futures = frame["future_end"]
    return np.fromiter(
        (end not in blocked and future not in blocked for end, future in zip(ends, futures, strict=True)),
        dtype=bool,
        count=len(ends),
    )


def take(frame: dict[str, np.ndarray], mask: np.ndarray) -> dict[str, np.ndarray]:
    return {
        key: value[mask]
        for key, value in frame.items()
        if isinstance(value, np.ndarray)
    }


def choose_candidate(validation_log_loss: dict[str, float], preference: tuple[str, ...]) -> str:
    """Lowest validation log-loss. A tie keeps the earlier name in preference."""
    return min(preference, key=lambda name: (validation_log_loss[name], preference.index(name)))


def fold_bounds(last: date, first: date = date(2025, 1, 1)) -> list[tuple[date, date]]:
    """Quarterly test windows from 2025-01-01 through the last session."""
    folds = []
    start = first
    while start <= last:
        end = _add_months(start, 3)
        folds.append((start, end))
        start = end
    return folds


def time_of_day_bucket(minute: int) -> str:
    for left, right, name in TOD_BUCKETS:
        if left < minute <= right:
            return name
    return "outside"


def reliability_table(y: np.ndarray, probability: np.ndarray) -> list[dict[str, object]]:
    """Ten equal bins on [0, 1], including bins with no rows."""
    clipped = np.clip(probability, 1e-6, 1 - 1e-6)
    edges = np.linspace(0, 1, 11)
    rows = []
    for left, right in zip(edges[:-1], edges[1:], strict=True):
        mask = (clipped >= left) & (clipped < right if right < 1 else clipped <= right)
        count = int(mask.sum())
        rows.append(
            {
                "bin_left": float(left),
                "bin_right": float(right),
                "rows": count,
                "mean_predicted": float(clipped[mask].mean()) if count else None,
                "fraction_up": float(y[mask].mean()) if count else None,
            }
        )
    return rows


def fixed_split_review(frame: dict[str, np.ndarray], timeframe: str) -> dict[str, object]:
    days = [ist_day(stamp) for stamp in frame["end"]]
    day = np.array(days, dtype="datetime64[D]")
    split = np.array(["train" if item <= date(2025, 6, 30) else "validation" if item <= date(2025, 12, 31) else "test" for item in days])
    train = split == "train"
    valid = split == "validation"
    test = split == "test"
    bounds = _winsor_bounds(frame["x"][train])
    x = _apply_winsor(frame["x"], bounds)
    fitted = _fit_raw(x[train], frame["y"][train], (x[valid], x[test]))
    raw = {"validation": fitted["raw"][0], "test": fitted["raw"][1]}
    methods = {}
    for name in ("uncalibrated", "platt", "isotonic"):
        methods[name] = {
            side: _side(
                frame["y"][{"validation": valid, "test": test}[side]],
                _apply_calibration(name, raw["validation"], frame["y"][valid], raw[side]),
                float(frame["y"][train].mean()),
                reliability=timeframe == "1d",
            )
            for side in ("validation", "test")
        }
    primary_name = PRIMARY_CALIBRATION[timeframe]
    primary_test = methods[primary_name]["test"]["probability"]
    train_rate = float(np.clip(frame["y"][train].mean(), 1e-6, 1 - 1e-6))
    y_test = frame["y"][test]
    short = np.array(sorted(SESSIONS_72), dtype="datetime64[D]")
    without = ~np.isin(day[test], short)
    report: dict[str, object] = {
        "primary_calibration": primary_name,
        "validation_scores_for_platt_and_isotonic_use_the_calibration_fit_rows": True,
        "winsor_bounds": {name: list(bounds[name]) for name in WINSOR_COLUMNS},
        "train_up_rate": train_rate,
        "train_rows": int(train.sum()),
        "validation_rows": int(valid.sum()),
        "test_rows": int(test.sum()),
        "methods": {
            name: {side: _public(block) for side, block in sides.items()}
            for name, sides in methods.items()
        },
        "primary_test_with_72_bar_sessions": _public(methods[primary_name]["test"]),
        "primary_test_without_72_bar_sessions": _score(y_test[without], primary_test[without], train_rate),
        "day_bootstrap": _bootstrap(y_test, primary_test, frame["day"][test], train_rate),
        "day_bootstrap_without_72_bar_sessions": _bootstrap(
            y_test[without], primary_test[without], frame["day"][test][without], train_rate
        ),
    }
    if timeframe == "1d":
        report["daily_status"] = "shown for review; not classified as a failed model from the isotonic log-loss"
        report["ablation"] = _ablation(
            x, frame, train, valid, test, train_rate,
            ("base", "day_of_week", "month", "day_of_week_and_month"),
            methods["uncalibrated"]["validation"]["log_loss"],
            _public(methods["platt"]["test"]),
            "platt",
        )
    else:
        column = DIRECTION_COLUMNS.index("return_1")
        only = _fit_raw(x[train][:, [column]], frame["y"][train], (x[valid][:, [column]], x[test][:, [column]]))
        only_valid = _apply_calibration("isotonic", only["raw"][0], frame["y"][valid], only["raw"][0])
        only_test = _apply_calibration("isotonic", only["raw"][0], frame["y"][valid], only["raw"][1])
        report["coefficients_standardized"] = [
            {"feature": name, "coefficient": float(value)}
            for name, value in zip(DIRECTION_COLUMNS, fitted["model"].coef_[0], strict=True)
        ]
        report["intercept"] = float(fitted["model"].intercept_[0])
        report["return_1_versus_all"] = {
            "definition": (
                "share_of_gain = (train_rate_log_loss - return_1_log_loss) / "
                "(train_rate_log_loss - all_features_log_loss). Pre-specified decomposition, not a feature selection."
            ),
            "validation": _gain_share(methods["isotonic"]["validation"], _score(frame["y"][valid], only_valid, train_rate)),
            "test": _gain_share(methods["isotonic"]["test"], _score(y_test, only_test, train_rate)),
        }
        months = np.array([f"{item.year:04d}-{item.month:02d}" for item in days])
        report["log_loss_gap_by_month"] = _grouped_gap(y_test, primary_test, months[test], train_rate)
        report["log_loss_gap_by_symbol"] = _grouped_gap(y_test, primary_test, frame["symbol"][test], train_rate)
        report["log_loss_gap_by_time_of_day"] = _grouped_gap(
            y_test,
            primary_test,
            np.array([time_of_day_bucket(int(minute)) for minute in frame["minute"][test]]),
            train_rate,
        )
        report["economics"] = _economics(primary_test, frame["next_return"][test])
        report["ablation"] = _ablation(
            x, frame, train, valid, test, train_rate,
            ("base", "time_of_day"),
            methods["uncalibrated"]["validation"]["log_loss"],
            _public(methods["isotonic"]["test"]),
            "isotonic",
        )
    report["coefficients_converged"] = bool(fitted["model"].n_iter_[0] < 500)
    return report


def walk_forward(frame: dict[str, np.ndarray], timeframe: str) -> dict[str, object]:
    """Expanding train, previous quarter for calibration only, next quarter scored once."""
    day = np.array([ist_day(stamp) for stamp in frame["end"]], dtype="datetime64[D]")
    future_day = np.array([ist_day(stamp) for stamp in frame["future_end"]], dtype="datetime64[D]")
    last = date.fromisoformat(str(day.max()))
    method = PRIMARY_CALIBRATION[timeframe]
    folds = []
    for test_start, test_end in fold_bounds(last):
        print(f"walk-forward {timeframe} {test_start.isoformat()}", flush=True)
        folds.append(_one_fold(frame, day, future_day, test_start, test_end, method))
    return {
        "independent_of_the_fixed_split": True,
        "uses_base_features": True,
        "calibration": method,
        "purge_bars": PURGE_BARS,
        "folds": folds,
    }


def _one_fold(frame, day, future_day, test_start: date, test_end: date, method: str, *, keep_probabilities: bool = False) -> dict[str, object]:
    cal_start = _add_months(test_start, -3)
    test_lo = np.datetime64(test_start)
    test_hi = np.datetime64(test_end)
    cal_lo = np.datetime64(cal_start)
    raw_test = (day >= test_lo) & (day < test_hi)
    raw_cal = (day >= cal_lo) & (day < test_lo)
    raw_train = day < cal_lo
    test_purge = _leading_ends(frame["end"][raw_test], PURGE_BARS)
    cal_purge = _leading_ends(frame["end"][raw_cal], PURGE_BARS)
    train = raw_train & ~_in_ends(frame["end"], cal_purge) & ~_in_ends(frame["future_end"], cal_purge) & (future_day < cal_lo)
    valid = raw_cal & ~_in_ends(frame["end"], cal_purge) & ~_in_ends(frame["future_end"], cal_purge) & (future_day < test_lo)
    test = raw_test & ~_in_ends(frame["end"], test_purge) & ~_in_ends(frame["future_end"], test_purge) & (future_day < test_hi)
    header = {
        "test_start": test_start.isoformat(),
        "test_end_exclusive": test_end.isoformat(),
        "train_rows": int(train.sum()),
        "calibration_rows": int(valid.sum()),
        "test_rows": int(test.sum()),
    }
    if min(int(train.sum()), int(valid.sum()), int(test.sum())) < 50 or len(np.unique(frame["y"][train])) < 2 or len(np.unique(frame["y"][valid])) < 2:
        return {**header, "skipped": True}
    bounds = _winsor_bounds(frame["x"][train])
    x = _apply_winsor(frame["x"], bounds)
    raw_valid, raw_test_p = _fit_raw(x[train], frame["y"][train], (x[valid], x[test]))["raw"]
    probability = _apply_calibration(method, raw_valid, frame["y"][valid], raw_test_p)
    train_rate = float(np.clip(frame["y"][train].mean(), 1e-6, 1 - 1e-6))
    scored = _score(frame["y"][test], probability, train_rate)
    scored["train_up_rate"] = train_rate
    if keep_probabilities:
        scored["detail"] = {
            "y": frame["y"][test],
            "probability": probability,
            "day": day[test],
            "minute": frame["minute"][test],
            "next_return": frame["next_return"][test],
            "symbol": frame["symbol"][test],
        }
    short = np.array(sorted(SESSIONS_72), dtype="datetime64[D]")
    without = ~np.isin(day[test], short)
    if int(without.sum()) != int(test.sum()) and int(without.sum()) >= 50:
        scored["log_loss_minus_train_rate_without_72_bar_sessions"] = _score(
            frame["y"][test][without], probability[without], train_rate
        )["log_loss_minus_train_rate"]
    return {**header, "skipped": False, **scored}


def _ablation(x, frame, train, valid, test, train_rate, preference, base_loss, base_test, calibration: str) -> dict[str, object]:
    """Pick a feature set on uncalibrated validation log-loss, then score test once."""
    losses = {"base": base_loss}
    fitted = {}
    y = frame["y"]
    for name in preference:
        if name == "base":
            continue
        matrix = np.column_stack([x, _extra_for(name, frame)])
        fitted[name] = _fit_raw(matrix[train], y[train], (matrix[valid],))
        losses[name] = _score(y[valid], fitted[name]["raw"][0], train_rate)["log_loss"]
    selected = choose_candidate(losses, preference)
    if selected == "base":
        return _ablation_report(preference, losses, selected, base_test, calibration)
    matrix = np.column_stack([x, _extra_for(selected, frame)])
    raw_test = fitted[selected]["model"].predict_proba(fitted[selected]["scaler"].transform(matrix[test]))[:, 1]
    probability = _apply_calibration(calibration, fitted[selected]["raw"][0], y[valid], raw_test)
    return _ablation_report(preference, losses, selected, _score(y[test], probability, train_rate), calibration)


def _ablation_report(preference, losses, selected, test_score, calibration: str) -> dict[str, object]:
    return {
        "selected_on": "uncalibrated validation log-loss",
        "calibrator_fit_after_selection": calibration,
        "candidates": [{"name": name, "validation_log_loss": losses[name]} for name in preference],
        "selected": selected,
        "test_evaluated_once": test_score,
    }


def _economics(probability: np.ndarray, next_return: np.ndarray) -> dict[str, object]:
    bps = next_return * 10000
    long = probability > 0.55
    short = probability < 0.45
    return {
        "descriptive_only": True,
        "cost_assumption_bps_round_trip": ROUND_TRIP_COST_BPS,
        "cost_note": "5 bps round trip, stated before these conditional means. Not measured from the tape.",
        "average_absolute_next_return_bps": float(np.abs(bps).mean()),
        "p_up_above_0_55": _side_economics(bps[long], sign=1),
        "p_up_below_0_45": _side_economics(bps[short], sign=-1),
    }


def _side_economics(bps: np.ndarray, sign: int) -> dict[str, object]:
    if len(bps) == 0:
        return {"rows": 0, "mean_next_return_bps": None, "mean_position_return_bps": None, "mean_position_return_minus_cost_bps": None}
    position = float(bps.mean() * sign)
    return {
        "rows": int(len(bps)),
        "mean_next_return_bps": float(bps.mean()),
        "mean_position_return_bps": position,
        "mean_position_return_minus_cost_bps": position - ROUND_TRIP_COST_BPS,
    }


def _grouped_gap(y: np.ndarray, probability: np.ndarray, keys: np.ndarray, train_rate: float) -> list[dict[str, object]]:
    rows = []
    for key in sorted(set(keys.tolist()), key=str):
        mask = keys == key
        if int(mask.sum()) < 2 or len(np.unique(y[mask])) < 2:
            continue
        scored = _score(y[mask], probability[mask], train_rate)
        rows.append({"key": str(key), **scored})
    return rows


def _gain_share(full: dict[str, object], only: dict[str, object]) -> dict[str, object]:
    full_gain = full["train_rate_log_loss"] - full["log_loss"]
    only_gain = only["train_rate_log_loss"] - only["log_loss"]
    share = None if abs(full_gain) < 1e-12 else only_gain / full_gain
    return {
        "all_features_log_loss": full["log_loss"],
        "return_1_log_loss": only["log_loss"],
        "train_rate_log_loss": full["train_rate_log_loss"],
        "all_features_gap": full["log_loss_minus_train_rate"],
        "return_1_gap": only["log_loss_minus_train_rate"],
        "share_of_gain": None if share is None else float(share),
    }


def _extra_for(name: str, frame: dict[str, np.ndarray]) -> np.ndarray | None:
    if name == "base":
        return None
    if name == "time_of_day":
        return _tod_columns(frame["minute"])
    return _calendar_columns(frame["weekday"], frame["month"], name)


def _tod_columns(minute: np.ndarray) -> np.ndarray:
    elapsed = minute.astype(np.float64) - (9 * 60 + 15)
    angle = 2 * np.pi * elapsed / (6 * 60 + 15)
    return np.column_stack([np.sin(angle), np.cos(angle)])


def _calendar_columns(weekday: np.ndarray, month: np.ndarray, name: str) -> np.ndarray:
    parts = []
    if name in ("day_of_week", "day_of_week_and_month"):
        angle = 2 * np.pi * weekday.astype(np.float64) / 5
        parts.extend((np.sin(angle), np.cos(angle)))
    if name in ("month", "day_of_week_and_month"):
        angle = 2 * np.pi * (month.astype(np.float64) - 1) / 12
        parts.extend((np.sin(angle), np.cos(angle)))
    return np.column_stack(parts)


def _fit_raw(x_train: np.ndarray, y_train: np.ndarray, others: tuple[np.ndarray, ...]) -> dict[str, object]:
    scaler = StandardScaler()
    train = scaler.fit_transform(x_train)
    model = LogisticRegression(random_state=0, max_iter=500)
    model.fit(train, y_train)
    raw = [model.predict_proba(scaler.transform(item))[:, 1] for item in others]
    return {"model": model, "scaler": scaler, "raw": raw}


def _apply_calibration(method: str, raw_valid: np.ndarray, y_valid: np.ndarray, raw_target: np.ndarray) -> np.ndarray:
    if method == "uncalibrated":
        return raw_target
    if method == "platt":
        model = LogisticRegression(random_state=0, max_iter=500)
        model.fit(_logit(raw_valid).reshape(-1, 1), y_valid)
        return model.predict_proba(_logit(raw_target).reshape(-1, 1))[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(raw_valid, y_valid)
    return calibrator.predict(raw_target)


def _side(y: np.ndarray, probability: np.ndarray, train_rate: float, *, reliability: bool) -> dict[str, object]:
    scored = _score(y, probability, train_rate)
    scored["probability"] = probability
    if reliability:
        scored["reliability"] = reliability_table(y, probability)
    return scored


def _public(block: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in block.items() if key != "probability"}


def _score(y: np.ndarray, probability: np.ndarray, train_rate: float) -> dict[str, object]:
    clipped = np.clip(probability, 1e-6, 1 - 1e-6)
    rate = float(np.clip(train_rate, 1e-6, 1 - 1e-6))
    model_loss = float(log_loss(y, clipped, labels=[0, 1]))
    train_loss = float(log_loss(y, np.full(y.shape, rate), labels=[0, 1]))
    return {
        "rows": int(len(y)),
        "log_loss": model_loss,
        "train_rate_log_loss": train_loss,
        "log_loss_minus_train_rate": model_loss - train_loss,
        "auc": float(roc_auc_score(y, clipped)) if len(np.unique(y)) > 1 else None,
        "brier": float(brier_score_loss(y, clipped)),
    }


def _logit(probability: np.ndarray) -> np.ndarray:
    clipped = np.clip(probability, 1e-6, 1 - 1e-6)
    return np.log(clipped / (1 - clipped))


def _leading_ends(ends: np.ndarray, count: int) -> set:
    found = []
    seen: set = set()
    for stamp in sorted(ends.tolist()):
        if stamp in seen:
            continue
        seen.add(stamp)
        found.append(stamp)
        if len(found) == count:
            break
    return set(found)


def _in_ends(stamps: np.ndarray, blocked: set) -> np.ndarray:
    if not blocked:
        return np.zeros(len(stamps), dtype=bool)
    return np.fromiter((stamp in blocked for stamp in stamps), dtype=bool, count=len(stamps))


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return date(year, month, 1)

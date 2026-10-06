"""Research-only relative features from Feature Engine columns.

Production MlAgent must not compute these ratios. They are not FeatureSet fields
until the engine emits them (see docs/feature-requests.md).
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

ENGINE_PREFIX = "feature_"

CURRENT_COLUMNS = (
    "feature_last_close",
    "feature_last_volume",
    "feature_period_high",
    "feature_period_low",
    "feature_volume_mean",
    "feature_vwap",
)

NEW_COLUMNS = (
    "return_1",
    "rsi_14",
    "volatility",
    "close_sma_10",
    "close_sma_20",
    "close_ema_12",
    "close_ema_26",
    "macd_over_close",
    "macd_signal_over_close",
    "atr_over_close",
    "bollinger_position",
    "close_vwap",
    "volume_ratio",
    "momentum_10_over_close",
)

REQUIRED_SOURCES = (
    "last_close",
    "sma_10",
    "sma_20",
    "ema_12",
    "ema_26",
    "macd",
    "macd_signal",
    "rsi_14",
    "atr_14",
    "vwap",
    "bollinger_lower",
    "bollinger_upper",
    "last_volume",
    "volume_mean",
    "return_1",
    "volatility",
    "momentum_10",
)

DENOMINATOR_SOURCES = (
    "last_close",
    "sma_10",
    "sma_20",
    "ema_12",
    "ema_26",
    "vwap",
    "volume_mean",
)

DROP_REASONS = (
    "missing_source",
    "zero_denominator",
    "flat_bollinger",
    "non_finite",
)


def engine_value(row: dict[str, Any], name: str) -> Any:
    if name in row and row[name] is not None:
        return row[name]
    keyed = f"{ENGINE_PREFIX}{name}"
    return row.get(keyed)


def _as_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _drop_reason(row: dict[str, Any]) -> str | None:
    sources: dict[str, float] = {}
    for name in REQUIRED_SOURCES:
        value = _as_float(engine_value(row, name))
        if value is None:
            return "missing_source"
        sources[name] = value
    for name in DENOMINATOR_SOURCES:
        if sources[name] == 0.0:
            return "zero_denominator"
    if sources["bollinger_upper"] == sources["bollinger_lower"]:
        return "flat_bollinger"
    return None


def relative_row(row: dict[str, Any]) -> dict[str, float]:
    close = _as_float(engine_value(row, "last_close"))
    sma_10 = _as_float(engine_value(row, "sma_10"))
    sma_20 = _as_float(engine_value(row, "sma_20"))
    ema_12 = _as_float(engine_value(row, "ema_12"))
    ema_26 = _as_float(engine_value(row, "ema_26"))
    macd = _as_float(engine_value(row, "macd"))
    macd_signal = _as_float(engine_value(row, "macd_signal"))
    atr = _as_float(engine_value(row, "atr_14"))
    lower = _as_float(engine_value(row, "bollinger_lower"))
    upper = _as_float(engine_value(row, "bollinger_upper"))
    vwap = _as_float(engine_value(row, "vwap"))
    volume = _as_float(engine_value(row, "last_volume"))
    volume_mean = _as_float(engine_value(row, "volume_mean"))
    momentum = _as_float(engine_value(row, "momentum_10"))
    payload = {
        "return_1": _as_float(engine_value(row, "return_1")),
        "rsi_14": _as_float(engine_value(row, "rsi_14")),
        "volatility": _as_float(engine_value(row, "volatility")),
        "close_sma_10": close / sma_10 - 1.0,
        "close_sma_20": close / sma_20 - 1.0,
        "close_ema_12": close / ema_12 - 1.0,
        "close_ema_26": close / ema_26 - 1.0,
        "macd_over_close": macd / close,
        "macd_signal_over_close": macd_signal / close,
        "atr_over_close": atr / close,
        "bollinger_position": (close - lower) / (upper - lower),
        "close_vwap": close / vwap - 1.0,
        "volume_ratio": volume / volume_mean,
        "momentum_10_over_close": momentum / close,
    }
    missing = [name for name in NEW_COLUMNS if name not in payload or payload[name] is None]
    if missing:
        raise SystemExit(f"NEW feature columns missing after transform: {missing}")
    for name, value in payload.items():
        if not math.isfinite(float(value)):
            raise SystemExit(f"NEW feature {name} is not finite")
    return {name: float(payload[name]) for name in NEW_COLUMNS}


def filter_new_eligible(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, float]], Counter]:
    kept: list[dict[str, Any]] = []
    matrix: list[dict[str, float]] = []
    dropped: Counter = Counter()
    for row in rows:
        reason = _drop_reason(row)
        if reason is not None:
            dropped[reason] += 1
            continue
        features = relative_row(row)
        if any(not math.isfinite(value) for value in features.values()):
            dropped["non_finite"] += 1
            continue
        kept.append(row)
        matrix.append(features)
    missing = [name for name in NEW_COLUMNS if name not in (matrix[0] if matrix else NEW_COLUMNS)]
    if matrix:
        for name in NEW_COLUMNS:
            if name not in matrix[0]:
                raise SystemExit(f"NEW feature columns missing after transform: {name}")
    elif missing:
        pass
    return kept, matrix, dropped


def current_matrix(rows: list[dict[str, Any]]) -> list[list[float]]:
    missing = [name for name in CURRENT_COLUMNS if any(row.get(name) is None for row in rows)]
    if missing and rows:
        bad = [name for name in CURRENT_COLUMNS if rows[0].get(name) is None]
        if bad:
            raise SystemExit(f"CURRENT columns missing: {bad}")
    return [[float(row[name]) for name in CURRENT_COLUMNS] for row in rows]


def new_matrix(feature_rows: list[dict[str, float]]) -> list[list[float]]:
    if feature_rows:
        absent = [name for name in NEW_COLUMNS if name not in feature_rows[0]]
        if absent:
            raise SystemExit(f"NEW feature columns missing after transform: {absent}")
    return [[float(item[name]) for name in NEW_COLUMNS] for item in feature_rows]

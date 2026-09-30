"""Point-in-time labelled rows. Labels use last_close at t+h compared to last_close at t."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

from contracts.enums import Timeframe
from contracts.schemas.feature_set import FeatureSet

FEATURE_COLUMNS = (
    "last_close",
    "sma_10",
    "sma_20",
    "ema_12",
    "ema_26",
    "rsi_14",
    "macd",
    "return_1",
    "volatility",
    "momentum_10",
    "last_volume",
    "volume_mean",
)


@dataclass(frozen=True, slots=True)
class DatasetResult:
    rows: list[dict[str, float]]
    labels: list[int]
    as_of_list: list[datetime]
    dropped_zero: int
    dropped_cutoff: int


def _scalar(features: dict[str, str | int | float | bool], name: str) -> float | None:
    raw = features.get(name)
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def build_dataset(
    provider: Any,
    *,
    symbol: str,
    timeframe: Timeframe,
    as_of_points: Sequence[datetime],
    label_horizon: int,
    training_data_cutoff: datetime,
    columns: Sequence[str] = FEATURE_COLUMNS,
) -> DatasetResult:
    if label_horizon < 1:
        raise ValueError("label_horizon must be >= 1")
    rows: list[dict[str, float]] = []
    labels: list[int] = []
    kept_times: list[datetime] = []
    dropped_zero = 0
    dropped_cutoff = 0
    points = list(as_of_points)
    for index, as_of in enumerate(points):
        future_index = index + label_horizon
        if future_index >= len(points):
            continue
        future_as_of = points[future_index]
        current: FeatureSet = provider.get_feature_set(symbol, timeframe, as_of)
        future: FeatureSet = provider.get_feature_set(symbol, timeframe, future_as_of)
        if future.source_data_timestamp > training_data_cutoff:
            dropped_cutoff += 1
            continue
        close_t = _scalar(current.features, "last_close")
        close_h = _scalar(future.features, "last_close")
        if close_t is None or close_h is None:
            continue
        if close_h == close_t:
            dropped_zero += 1
            continue
        label = 1 if close_h > close_t else 0
        row: dict[str, float] = {}
        complete = True
        for column in columns:
            value = _scalar(current.features, column)
            if value is None:
                complete = False
                break
            row[column] = value
        if not complete:
            continue
        rows.append(row)
        labels.append(label)
        kept_times.append(as_of)
    return DatasetResult(
        rows=rows,
        labels=labels,
        as_of_list=kept_times,
        dropped_zero=dropped_zero,
        dropped_cutoff=dropped_cutoff,
    )

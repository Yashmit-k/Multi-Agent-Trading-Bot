"""Snapshot labels. t+h is the h-th later bar that exists on the same symbol and timeframe.

Gaps (holidays, missing 5m bars) do not invent empty slots. Overnight 5m labels are dropped.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from contracts.enums import Timeframe
from contracts.schemas.market import Candle

from quant_agents.config import load_horizons_table

IST = ZoneInfo("Asia/Kolkata")
LABEL_VERSION = "1.0"


@dataclass
class LabelStats:
    dropped_equal: int = 0
    dropped_no_future: int = 0
    dropped_cutoff: int = 0
    dropped_overnight: int = 0
    labeled_up: int = 0
    labeled_down: int = 0
    skipped_features: int = 0
    last_future_end: str | None = None
    input_bars: int = 0


@dataclass(frozen=True, slots=True)
class LabelConfig:
    label_horizon: int
    training_data_cutoff: datetime
    cutoff_source: str
    training_data: str
    overnight_5m: str = "dropped"


def parse_label_horizon(raw: str | int | None = None) -> int:
    if raw is None or raw == "":
        env = os.environ.get("QUANT_LABEL_HORIZON", "").strip()
        if env:
            raw = env
        else:
            raw = load_horizons_table().get("label_horizon", 1)
    try:
        horizon = int(raw)
    except (TypeError, ValueError) as exc:
        raise SystemExit("QUANT_LABEL_HORIZON must be an integer >= 1") from exc
    if horizon < 1:
        raise SystemExit("QUANT_LABEL_HORIZON must be an integer >= 1")
    return horizon


def resolve_cutoff(
    *,
    cutoff: datetime | None = None,
    cutoff_source: str | None = None,
    training_data: str = "synthetic_fixture",
) -> tuple[datetime, str]:
    if cutoff is not None:
        if cutoff.tzinfo is None:
            raise SystemExit("training_data_cutoff must be timezone-aware")
        source = cutoff_source or "documented_split"
        if source not in {"explicit", "documented_split"}:
            raise SystemExit("cutoff_source must be explicit or documented_split")
        return cutoff, source
    env = os.environ.get("QUANT_TRAINING_DATA_CUTOFF", "").strip()
    if env:
        parsed = datetime.fromisoformat(env)
        if parsed.tzinfo is None:
            raise SystemExit("QUANT_TRAINING_DATA_CUTOFF must be timezone-aware")
        return parsed, "explicit"
    if training_data == "real_snapshot":
        raise SystemExit("QUANT_TRAINING_DATA_CUTOFF is required for real_snapshot")
    raise SystemExit("training_data_cutoff is required")


def session_date_ist(stamp: datetime):
    return stamp.astimezone(IST).date()


def _timeframe_of(bar: Candle) -> Timeframe:
    raw = bar.timeframe
    return raw if isinstance(raw, Timeframe) else Timeframe(str(raw))


def series_for(symbol: str, as_of: datetime, candles: tuple[Candle, ...] | list[Candle]) -> list[Candle]:
    current = next((bar for bar in candles if bar.symbol == symbol and bar.end == as_of), None)
    if current is None:
        return []
    timeframe = _timeframe_of(current)
    owned = [bar for bar in candles if bar.symbol == symbol and _timeframe_of(bar) == timeframe]
    owned.sort(key=lambda bar: bar.end)
    seen: dict[datetime, Candle] = {}
    for bar in owned:
        if bar.end in seen:
            raise ValueError(f"duplicate end {bar.end.isoformat()} for {symbol} {timeframe.value}")
        seen[bar.end] = bar
    return owned


def next_close_direction(symbol: str, as_of: datetime, candles: tuple[Candle, ...] | list[Candle]) -> int | None:
    """QUANT_LABELER entry. Uses process env; prefer make_labeler for isolated stats."""
    labeler, _stats, _config = make_labeler()
    return labeler(symbol, as_of, candles)


def make_labeler(
    *,
    label_horizon: int | None = None,
    cutoff: datetime | None = None,
    cutoff_source: str | None = None,
    training_data: str = "synthetic_fixture",
) -> tuple[Callable[..., int | None], LabelStats, LabelConfig]:
    horizon = parse_label_horizon(label_horizon)
    resolved_cutoff, source = resolve_cutoff(
        cutoff=cutoff,
        cutoff_source=cutoff_source,
        training_data=training_data,
    )
    config = LabelConfig(
        label_horizon=horizon,
        training_data_cutoff=resolved_cutoff,
        cutoff_source=source,
        training_data=training_data,
        overnight_5m="dropped",
    )
    stats = LabelStats()

    def labeler(symbol: str, as_of: datetime, candles: tuple[Candle, ...] | list[Candle]) -> int | None:
        series = series_for(symbol, as_of, candles)
        ends = [bar.end for bar in series]
        if as_of not in ends:
            stats.dropped_no_future += 1
            return None
        index = ends.index(as_of)
        future_index = index + config.label_horizon
        if future_index >= len(series):
            stats.dropped_no_future += 1
            return None
        current = series[index]
        future = series[future_index]
        if future.end > config.training_data_cutoff:
            stats.dropped_cutoff += 1
            return None
        if _timeframe_of(current) == Timeframe.M5 and session_date_ist(current.end) != session_date_ist(future.end):
            stats.dropped_overnight += 1
            return None
        if future.close == current.close:
            stats.dropped_equal += 1
            return None
        stats.last_future_end = future.end.isoformat()
        if future.close > current.close:
            stats.labeled_up += 1
            return 1
        stats.labeled_down += 1
        return 0

    return labeler, stats, config

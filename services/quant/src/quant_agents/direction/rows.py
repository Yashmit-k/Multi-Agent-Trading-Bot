"""Labels and trailing-window features for one symbol tape.

The label value comes from make_labeler. Drop reasons are classified here from the
same two bars so the report can check that the buckets sum to the row count.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from contracts.enums import Exchange, Timeframe
from contracts.schemas.market import Candle
from core_features.engine import build_feature_set
from quant_agents.labelers import make_labeler, session_date_ist
from quant_agents.ml.features import DIRECTION_COLUMNS, FORBIDDEN_X_COLUMNS, direction_row

from quant_agents.direction.inventory import StoredBar, SymbolTape
from quant_agents.direction.window import window_bars

BASELINE_COLUMNS = (
    "last_close",
    "last_volume",
    "period_high",
    "period_low",
    "volume_mean",
    "vwap",
)

FIVE_MINUTES = timedelta(minutes=5)


def next_step_ok(current: StoredBar, future: StoredBar | None) -> bool:
    """A 5-minute label is valid only when the next bar ends exactly five minutes later."""
    if future is None:
        return False
    if current.timeframe == "5m":
        return future.end - current.end == FIVE_MINUTES
    return True


def is_same_session_gap(current: StoredBar, future: StoredBar | None) -> bool:
    if future is None or current.timeframe != "5m":
        return False
    if current.session_date != future.session_date:
        return False
    return future.end - current.end != FIVE_MINUTES


def modeling_indexes(tape: SymbolTape, purged: set[datetime] | None = None) -> list[int]:
    """Rows that remain after warm-up, flat bars, the 5-minute rule, equals, and the purge."""
    if not tape.bars:
        return []
    blocked = purged or set()
    length = window_bars(tape.bars[0].timeframe)
    kept: list[int] = []
    for index, bar in enumerate(tape.bars):
        if index + 1 < length:
            continue
        future = tape.bars[index + 1] if index + 1 < len(tape.bars) else None
        if bar.high == bar.low or not next_step_ok(bar, future):
            continue
        if future is None or future.close == bar.close:
            continue
        if bar.end in blocked or (future.end in blocked):
            continue
        kept.append(index)
    return kept


def classify_pair(current: StoredBar, future: StoredBar | None, cutoff: datetime) -> str:
    """Same decisions as make_labeler, returned as a reason instead of None."""
    if future is None:
        return "no_next_bar"
    if future.end > cutoff:
        return "cutoff"
    if current.timeframe == "5m" and session_date_ist(current.end) != session_date_ist(future.end):
        return "cross_session"
    if future.close == current.close:
        return "equal"
    if future.close > current.close:
        return "up"
    return "down"


def label_counts(tape: SymbolTape, cutoff: datetime) -> Counter[str]:
    labeler, stats, _config = make_labeler(
        label_horizon=1,
        cutoff=cutoff,
        cutoff_source="explicit",
        training_data="synthetic_fixture",
    )
    counted: Counter[str] = Counter()
    bars = tape.bars
    for index, bar in enumerate(bars):
        future = bars[index + 1] if index + 1 < len(bars) else None
        reason = classify_pair(bar, future, cutoff)
        counted[reason] += 1
        pair = (bar, future) if future is not None else (bar,)
        value = labeler(bar.symbol, bar.end, [_candle(item) for item in pair])
        if reason in {"up", "down"}:
            if value != (1 if reason == "up" else 0):
                raise SystemExit(f"labeler disagreed with the report on {bar.symbol} {bar.end.isoformat()}")
        elif value is not None:
            raise SystemExit(f"labeler kept a row the report dropped on {bar.symbol} {bar.end.isoformat()}")
    expected = {
        "up": stats.labeled_up,
        "down": stats.labeled_down,
        "equal": stats.dropped_equal,
        "cross_session": stats.dropped_overnight,
        "no_next_bar": stats.dropped_no_future,
        "cutoff": stats.dropped_cutoff,
    }
    for name, total in expected.items():
        if counted[name] != total:
            raise SystemExit(f"{bar.symbol} {name} report {counted[name]} != labeler {total}")
    if sum(counted.values()) != len(bars):
        raise SystemExit(f"{tape.bars[0].symbol if bars else '?'} label buckets do not sum to rows")
    return counted


def feature_census(tape: SymbolTape) -> dict[str, object]:
    """Count warm-up and feature drops. Does not keep the matrix."""
    if not tape.bars:
        return _empty_census()
    length = window_bars(tape.bars[0].timeframe)
    candles = [_candle(bar) for bar in tape.bars]
    short_window = 0
    warmup_missing = 0
    feature_dropped: Counter[str] = Counter()
    kept = 0
    first_session = 0
    first_session_up = 0
    other_up = 0
    other_kept = 0
    for index, bar in enumerate(tape.bars):
        if index + 1 < length:
            short_window += 1
            continue
        window = candles[index + 1 - length : index + 1]
        built = build_feature_set(bar.symbol, bar.timeframe, window, bar.end)
        if built is None or built.source_data_timestamp != bar.end:
            warmup_missing += 1
            continue
        features, reason = direction_row(
            dict(built.features),
            open_=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
        )
        if features is None:
            feature_dropped[reason or "missing_source"] += 1
            continue
        _reject_leaky_keys(features)
        kept += 1
        is_open = bar.timeframe == "5m" and tape.bars[index - 1].session_date != bar.session_date
        future = tape.bars[index + 1] if index + 1 < len(tape.bars) else None
        went_up = future is not None and future.close > bar.close
        if is_open:
            first_session += 1
            first_session_up += int(went_up)
        else:
            other_kept += 1
            other_up += int(went_up)
    return {
        "window_bars": length,
        "rows": len(tape.bars),
        "short_window_dropped": short_window,
        "warmup_missing_engine_field": warmup_missing,
        "feature_dropped": dict(feature_dropped),
        "rows_remaining": kept,
        "first_bars_of_session": first_session,
        "first_bar_up_rate": _rate(first_session_up, first_session),
        "other_bar_up_rate": _rate(other_up, other_kept),
        "overnight_window": _overnight_note(tape.bars[0].timeframe),
    }


def leakage_cases(tape: SymbolTape, grid_starts: set[datetime]) -> list[int]:
    """Indexes near the ends, the session open, and bars beside a hole in this tape."""
    if not tape.bars:
        return []
    length = window_bars(tape.bars[0].timeframe)
    chosen: list[int] = []
    last = len(tape.bars) - 1
    if last >= length - 1:
        chosen.append(length - 1)
        chosen.append(last)
    for index, bar in enumerate(tape.bars):
        if index < length - 1:
            continue
        previous = tape.bars[index - 1]
        if previous.session_date != bar.session_date:
            chosen.append(index)
            if index + 1 <= last:
                chosen.append(index + 1)
            break
    for index, bar in enumerate(tape.bars):
        if index < length - 1:
            continue
        neighbour = bar.start + timedelta(minutes=5)
        if bar.timeframe == "5m" and neighbour not in grid_starts and _same_session_later(tape, index):
            chosen.append(index)
            break
    return list(dict.fromkeys(chosen))


def assert_window_leakage(tape: SymbolTape, indexes: list[int]) -> None:
    """Post-T bars must not change features at T, and no feature may see end > as_of."""
    if not tape.bars:
        return
    length = window_bars(tape.bars[0].timeframe)
    candles = [_candle(bar) for bar in tape.bars]
    for index in indexes:
        bar = tape.bars[index]
        if index + 1 < length:
            raise AssertionError("leakage sample is inside the warm-up")
        window = candles[index + 1 - length : index + 1]
        later = candles[index + 1 - length : min(len(candles), index + 6)]
        original = build_feature_set(bar.symbol, bar.timeframe, window, bar.end)
        extended = build_feature_set(bar.symbol, bar.timeframe, later, bar.end)
        if original is None or extended is None:
            raise AssertionError(f"missing features at {bar.end.isoformat()}")
        if original.features != extended.features:
            raise AssertionError(f"post-T bars changed features at {bar.end.isoformat()}")
        mutated = list(later)
        if index + 1 < len(candles):
            mutated[length] = _mutated(candles[index + 1])
            changed = build_feature_set(bar.symbol, bar.timeframe, mutated, bar.end)
            if changed is None or changed.features != original.features:
                raise AssertionError(f"a bar with end > as_of changed features at {bar.end.isoformat()}")
        features, reason = direction_row(
            dict(original.features),
            open_=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
        )
        if features is None:
            continue
        _reject_leaky_keys(features)
        if reason is not None:
            raise AssertionError(reason)


def _reject_leaky_keys(features: dict[str, float]) -> None:
    for name in features:
        if name in FORBIDDEN_X_COLUMNS or name.startswith("future_"):
            raise AssertionError(f"X contains {name}")
    if set(features) != set(DIRECTION_COLUMNS):
        raise AssertionError(f"unexpected X columns: {sorted(set(features) ^ set(DIRECTION_COLUMNS))}")


def _candle(bar: StoredBar) -> Candle:
    return Candle(
        symbol=bar.symbol,
        exchange=Exchange.NSE,
        timeframe=Timeframe(bar.timeframe),
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        start=bar.start,
        end=bar.end,
    )


def _mutated(bar: Candle) -> Candle:
    return bar.model_copy(update={"close": Decimal("999999.99"), "high": Decimal("999999.99")})


def _same_session_later(tape: SymbolTape, index: int) -> bool:
    if index + 1 >= len(tape.bars):
        return False
    return tape.bars[index].session_date == tape.bars[index + 1].session_date


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _overnight_note(timeframe: str) -> str:
    if timeframe == "5m":
        return (
            "A 5-minute trailing window crosses sessions. The 09:20 IST bar's window includes "
            "the previous day's bars, so return_1, window VWAP, and volatility span the overnight gap."
        )
    return "The daily window is a run of sessions. It does not contain an intraday overnight return."


def _empty_census() -> dict[str, object]:
    return {
        "window_bars": None,
        "rows": 0,
        "short_window_dropped": 0,
        "warmup_missing_engine_field": 0,
        "feature_dropped": {},
        "rows_remaining": 0,
        "first_bars_of_session": 0,
        "first_bar_up_rate": None,
        "other_bar_up_rate": None,
        "overnight_window": "",
    }


def far_cutoff(tape: SymbolTape) -> datetime:
    if not tape.bars:
        return datetime(2100, 1, 1, tzinfo=timezone.utc)
    return tape.bars[-1].end + timedelta(seconds=1)

"""Algorithm 1: a logistic filter for Today-Drop entries.

Strategy A (`baseline_today_drop`, delivery) has no fixed exit clock. It leaves
on a 3% stop or a 5% target. This module does not change that book. Its label
is a separate two-session research outcome. Event timing still follows the
Strategy A entry lock: one position per symbol, no pyramid, and the next
same-session 5-minute open is the only entry price.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from contracts.enums import Side
from contracts.schemas.market import Candle
from statistics import pstdev

from core_features.engine import FEATURE_VERSION, _ema, build_feature_set
from core_paper.backtest import exit_on_bar
from quant_agents.research.rebound import (
    MODES,
    PER_TRADE_CAP,
    _context_before,
    _state_for,
    daily_context,
    session_date,
    signal_window,
)

ALGORITHM_ID = "today_drop_ml_filter"
DATASET_VERSION = "today_drop_ml_filter_v1"
MODEL_VERSION = "algo1-logreg-v1"
PRIMARY_COST = 0.0002
SEED = 0
TRAIN_END = date(2025, 6, 30)
VALIDATION_END = date(2025, 12, 31)
MIN_SPLIT_ROWS = 30
MIN_TRAIN_ROWS = 100
MIN_CLASS = 30
# Fixed before any fit. These cutoffs are reporting rules, not a search.
AUC_INTEREST = 0.55
PR_LIFT = 0.02

ENGINE_COLUMNS = (
    "return_1",
    "rsi_14",
    "macd",
    "volatility",
    "relative_volume",
    "zscore_20",
    "roc_10",
    "atr_14",
    "distance_from_mean",
    "bollinger_pct_b",
)
EVENT_COLUMNS = ("drop_from_previous_close", "previous_daily_return")
FEATURE_COLUMNS = EVENT_COLUMNS + ENGINE_COLUMNS


def net_return(entry: float, exit_price: float, cost: float = PRIMARY_COST) -> float:
    """Long net return. `cost` is charged on entry notional and on exit notional."""
    if entry <= 0 or not math.isfinite(entry) or not math.isfinite(exit_price):
        raise ValueError("entry and exit must be finite and entry must be positive")
    gross = (exit_price - entry) / entry
    return gross - cost - (exit_price / entry) * cost


def _sessions(bars_1d: list[Candle], symbol: str) -> list[Candle]:
    chosen: list[Candle] = []
    for bar in sorted((item for item in bars_1d if item.symbol == symbol), key=lambda item: item.end):
        if chosen and session_date(chosen[-1].end) == session_date(bar.end):
            chosen[-1] = bar
            continue
        chosen.append(bar)
    return chosen


def outcome_bar(entry_session: date, sessions: list[Candle], horizon: int) -> Candle | None:
    """Close of the Nth completed daily session strictly after the entry session."""
    later = [bar for bar in sessions if session_date(bar.end) > entry_session]
    if len(later) < horizon:
        return None
    return later[horizon - 1]


@dataclass(frozen=True, slots=True)
class EntryEvent:
    symbol: str
    signal_time: datetime
    entry_time: datetime
    entry_bar_end: datetime
    entry_price: float
    previous_close: float
    drop_fraction: float
    entry_session: date
    previous_daily_return: float | None


def collect_events(symbol: str, bars_5m: list[Candle], bars_1d: list[Candle]) -> tuple[list[EntryEvent], dict[str, int]]:
    """Strategy A delivery entries, plus counts for bars that did not become entries."""
    bars = sorted((bar for bar in bars_5m if bar.symbol == symbol), key=lambda item: item.end)
    dates, closes, ema_at, streaks = daily_context(bar for bar in bars_1d if bar.symbol == symbol)
    contexts: dict[date, object] = {}
    counts = {
        "trigger_candidates": 0,
        "blocked_by_open_position": 0,
        "next_bar_other_session": 0,
        "next_bar_open_invalid": 0,
        "entry_below_one_share": 0,
        "entries": 0,
    }
    pending = None
    position_stop: Decimal | None = None
    position_target: Decimal | None = None
    position_entry_end: datetime | None = None
    events: list[EntryEvent] = []

    def context_for(day: date):
        found = contexts.get(day)
        if found is None:
            found = _context_before(day, dates, closes, ema_at, streaks)
            contexts[day] = found
        return found

    def prior_return(day: date) -> float | None:
        context = context_for(day)
        index = bisect_index(dates, day)
        if index < 1:
            return None
        previous = float(closes[index])
        before = float(closes[index - 1])
        if before == 0:
            return None
        return previous / before - 1.0

    for offset, bar in enumerate(bars):
        day = session_date(bar.end)
        state = _state_for(bar, context_for(day)) if signal_window(bar.end) and bar.close > 0 else None
        if pending is not None:
            signal, signal_day, drop_fraction, previous_close, daily_return = pending
            pending = None
            if session_date(bar.end) != signal_day:
                counts["next_bar_other_session"] += 1
            elif bar.open <= 0:
                counts["next_bar_open_invalid"] += 1
            elif int(PER_TRADE_CAP // bar.open) < 1:
                counts["entry_below_one_share"] += 1
            else:
                stop_pct, target_pct = MODES["delivery"]
                position_stop = bar.open * (Decimal(1) - stop_pct)
                position_target = bar.open * (Decimal(1) + target_pct)
                position_entry_end = bar.end
                events.append(
                    EntryEvent(
                        symbol=symbol,
                        signal_time=signal,
                        entry_time=bar.start,
                        entry_bar_end=bar.end,
                        entry_price=float(bar.open),
                        previous_close=previous_close,
                        drop_fraction=drop_fraction,
                        entry_session=signal_day,
                        previous_daily_return=daily_return,
                    )
                )
                counts["entries"] += 1
        if position_entry_end is not None and bar.end > position_entry_end:
            reason = exit_on_bar(Side.BUY, position_stop, position_target, bar)
            if reason in {"stop", "target"}:
                position_stop = None
                position_target = None
                position_entry_end = None
        drop = state is not None and state.today_drop_pct is not None and state.today_drop_pct <= Decimal("-1")
        if drop and state is not None and state.previous_close is not None:
            counts["trigger_candidates"] += 1
            if position_entry_end is not None or pending is not None:
                counts["blocked_by_open_position"] += 1
            else:
                pending = (
                    bar.end,
                    day,
                    float(state.today_drop_pct) / 100.0,
                    float(state.previous_close),
                    prior_return(day),
                )
        elif pending is None and offset == len(bars) - 1:
            pass
    if pending is not None:
        counts["next_bar_other_session"] += 1
    return events, counts


def bisect_index(dates: list[date], day: date) -> int:
    """Index of the last daily close strictly before `day`, or -1."""
    from bisect import bisect_left

    return bisect_left(dates, day) - 1


def label_event(event: EntryEvent, sessions: list[Candle]) -> dict | None:
    """Primary label uses the second later session. One-session net is diagnostic."""
    primary = outcome_bar(event.entry_session, sessions, 2)
    if primary is None or primary.close <= 0:
        return None
    secondary = outcome_bar(event.entry_session, sessions, 1)
    exit_price = float(primary.close)
    net = net_return(event.entry_price, exit_price)
    one_net = None if secondary is None or secondary.close <= 0 else net_return(event.entry_price, float(secondary.close))
    return {
        "net_return": net,
        "label": 1 if net > 0 else 0,
        "exit_price": exit_price,
        "outcome_session": session_date(primary.end),
        "one_session_net_return": one_net,
    }


def assign_split(entry_session: date, outcome_session: date) -> str:
    """Drop an event whose outcome session crosses into a later period."""
    if entry_session <= TRAIN_END:
        return "train" if outcome_session <= TRAIN_END else "purged_train"
    if entry_session <= VALIDATION_END:
        return "validation" if outcome_session <= VALIDATION_END else "purged_validation"
    return "evaluation"


def finite_feature(value: object, name: str) -> float:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"missing or non-numeric feature {name}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite feature {name}")
    return number


def _rsi_series(closes: list[float], length: int = 14) -> list[float | None]:
    values: list[float | None] = [None] * len(closes)
    if len(closes) <= length:
        return values
    deltas = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    gains = [max(delta, 0.0) for delta in deltas]
    losses = [max(-delta, 0.0) for delta in deltas]
    average_gain = sum(gains[:length]) / length
    average_loss = sum(losses[:length]) / length

    def _value(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0
        relative = gain / loss
        return 100 - (100 / (1 + relative))

    values[length] = _value(average_gain, average_loss)
    for index in range(length, len(deltas)):
        average_gain = ((average_gain * (length - 1)) + gains[index]) / length
        average_loss = ((average_loss * (length - 1)) + losses[index]) / length
        values[index + 1] = _value(average_gain, average_loss)
    return values


def _macd_series(closes: list[float]) -> list[float | None]:
    values: list[float | None] = [None] * len(closes)
    fast = _ema(closes, 12)
    slow = _ema(closes, 26)
    if not fast or not slow:
        return values
    offset = len(fast) - len(slow)
    line = [left - right for left, right in zip(fast[offset:], slow, strict=False)]
    for index, value in enumerate(line):
        values[25 + index] = value
    return values


def _atr_series(bars: list[Candle], length: int = 14) -> list[float | None]:
    values: list[float | None] = [None] * len(bars)
    if len(bars) <= length:
        return values
    ranges = []
    for index in range(1, len(bars)):
        high = float(bars[index].high)
        low = float(bars[index].low)
        previous = float(bars[index - 1].close)
        ranges.append(max(high - low, abs(high - previous), abs(low - previous)))
    value = sum(ranges[:length]) / length
    values[length] = value
    for index, true_range in enumerate(ranges[length:], start=length):
        value = ((value * (length - 1)) + true_range) / length
        values[index + 1] = value
    return values


def engine_features_for_prefixes(bars: list[Candle], needed: set[int] | None = None) -> list[dict[str, float]]:
    """Engine columns at each bar. A prefix matches `build_feature_set` on that prefix."""
    closes = [float(bar.close) for bar in bars]
    volumes = [bar.volume for bar in bars]
    rsi = _rsi_series(closes)
    macd = _macd_series(closes)
    atr = _atr_series(bars)
    volume_total = 0
    rows: list[dict[str, float]] = []
    for index, close in enumerate(closes):
        volume_total += volumes[index]
        if needed is not None and index not in needed:
            rows.append({})
            continue
        raw: dict[str, float] = {}
        if index >= 1 and closes[index - 1] != 0:
            raw["return_1"] = close / closes[index - 1] - 1
        if index >= 2:
            returns = [(closes[pos] / closes[pos - 1]) - 1 for pos in range(1, index + 1)]
            raw["volatility"] = pstdev(returns)
        if rsi[index] is not None:
            raw["rsi_14"] = float(rsi[index])
        if macd[index] is not None:
            raw["macd"] = float(macd[index])
        if atr[index] is not None:
            raw["atr_14"] = float(atr[index])
        if volume_total != 0:
            raw["relative_volume"] = volumes[index] / (volume_total / (index + 1))
        if index >= 19:
            window = closes[index - 19 : index + 1]
            mid = sum(window) / 20
            deviation = pstdev(window)
            if deviation != 0:
                raw["zscore_20"] = (close - mid) / deviation
            upper = mid + 2 * deviation
            lower = mid - 2 * deviation
            raw["distance_from_mean"] = close - mid
            if upper != lower:
                raw["bollinger_pct_b"] = (close - lower) / (upper - lower)
        if index >= 10 and closes[index - 10] != 0:
            raw["roc_10"] = close / closes[index - 10] - 1
        rows.append({name: round(float(value), 8) for name, value in raw.items()})
    return rows


def vector_from_engine(event: EntryEvent, engine: dict[str, float]) -> tuple[list[float] | None, str | None]:
    if event.previous_daily_return is None:
        return None, "missing_feature.previous_daily_return"
    values = {
        "drop_from_previous_close": event.drop_fraction,
        "previous_daily_return": event.previous_daily_return,
    }
    for name in ENGINE_COLUMNS:
        try:
            values[name] = finite_feature(engine.get(name), name)
        except ValueError:
            return None, f"missing_feature.{name}"
    return [values[name] for name in FEATURE_COLUMNS], None


def feature_row(event: EntryEvent, history: list[Candle]) -> tuple[list[float] | None, str | None]:
    """Features knowable at the trigger bar's end. The entry bar is not in `history`."""
    built = build_feature_set(event.symbol, "5m", history, event.signal_time)
    if built is None:
        return None, "missing_feature_history"
    if any(bar.end > event.signal_time for bar in history if bar.symbol == event.symbol):
        raise ValueError("feature history includes a bar after the trigger")
    values: dict[str, float] = {
        "drop_from_previous_close": event.drop_fraction,
    }
    if event.previous_daily_return is None:
        return None, "missing_feature.previous_daily_return"
    values["previous_daily_return"] = event.previous_daily_return
    for name in ENGINE_COLUMNS:
        raw = built.features.get(name)
        try:
            values[name] = finite_feature(raw, name)
        except ValueError:
            return None, f"missing_feature.{name}"
    return [values[name] for name in FEATURE_COLUMNS], None


def fit_pipeline(rows: list[list[float]], labels: list[int]) -> Pipeline:
    if len(rows) != len(labels) or len(set(labels)) < 2:
        raise ValueError("training requires both classes")
    model = Pipeline(
        steps=[
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(random_state=SEED, max_iter=1000, solver="lbfgs")),
        ]
    )
    model.fit(rows, labels)
    return model


def predict_probability(model: Pipeline, row: list[object]) -> float:
    values = [finite_feature(value, FEATURE_COLUMNS[index]) for index, value in enumerate(row)]
    if len(values) != len(FEATURE_COLUMNS):
        raise ValueError("feature row does not match the artifact column list")
    return float(model.predict_proba([values])[0][1])


def classification_report(labels: list[int], probabilities: list[float], baseline: float) -> dict:
    report: dict[str, object] = {
        "rows": len(labels),
        "positives": int(sum(labels)),
        "negatives": int(len(labels) - sum(labels)),
        "mean_probability": None if not probabilities else sum(probabilities) / len(probabilities),
    }
    if len(set(labels)) < 2 or not probabilities:
        report["roc_auc"] = None
        report["average_precision"] = None
        report["log_loss"] = None
        report["brier"] = None
        report["baseline_log_loss"] = None
        report["baseline_brier"] = None
        report["note"] = "undefined because a class is absent or the split is empty"
        return report
    constant = [baseline] * len(labels)
    report["roc_auc"] = float(roc_auc_score(labels, probabilities))
    report["average_precision"] = float(average_precision_score(labels, probabilities))
    report["log_loss"] = float(log_loss(labels, probabilities, labels=[0, 1]))
    report["brier"] = float(brier_score_loss(labels, probabilities))
    report["baseline_log_loss"] = float(log_loss(labels, constant, labels=[0, 1]))
    report["baseline_brier"] = float(brier_score_loss(labels, constant))
    return report


def select_threshold(probabilities: list[float], nets: list[float]) -> float:
    """Highest validation mean net return. Ties keep the higher threshold."""
    best_threshold = 0.5
    best_mean = None
    for step in range(0, 7):
        threshold = 0.5 + step * 0.05
        chosen = [net for probability, net in zip(probabilities, nets, strict=True) if probability >= threshold]
        if not chosen:
            continue
        mean = sum(chosen) / len(chosen)
        if best_mean is None or mean > best_mean or (mean == best_mean and threshold > best_threshold):
            best_mean = mean
            best_threshold = threshold
    return best_threshold


def equity_drawdown(nets: list[float]) -> float:
    """Peak-to-trough drop of an equal-weight cumulative net-return path."""
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in nets:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def cluster_mean_interval(by_symbol: dict[str, list[float]], *, draws: int = 200) -> dict[str, float] | None:
    import numpy as np

    symbols = [symbol for symbol, values in by_symbol.items() if values]
    if len(symbols) < 2:
        return None
    rng = np.random.default_rng(SEED)
    means: list[float] = []
    for _ in range(draws):
        picked = rng.choice(symbols, size=len(symbols), replace=True)
        pooled = [value for symbol in picked for value in by_symbol[str(symbol)]]
        if pooled:
            means.append(sum(pooled) / len(pooled))
    if not means:
        return None
    means.sort()
    return {"p05": means[int(0.05 * (len(means) - 1))], "p50": means[len(means) // 2], "p95": means[int(0.95 * (len(means) - 1))]}

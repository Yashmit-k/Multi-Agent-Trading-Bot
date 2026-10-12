"""Synthetic checks for the Today-Drop ML filter. No snapshot and no holdout."""

import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from contracts.enums import Timeframe
from contracts.schemas.market import Candle

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "quant" / "src"))

from quant_agents.ml.registry import ModelRegistry
from quant_agents.research.rebound import simulate_symbol
from quant_agents.research.today_drop_ml_filter import (
    FEATURE_COLUMNS,
    FEATURE_VERSION,
    assign_split,
    collect_events,
    engine_features_for_prefixes,
    feature_row,
    finite_feature,
    fit_pipeline,
    label_event,
    net_return,
    outcome_bar,
    predict_probability,
    select_threshold,
)
from core_features.engine import build_feature_set
from quant_agents.ml.artifact import write_artifact

IST = ZoneInfo("Asia/Kolkata")


def _at(day: str, hour: int, minute: int) -> datetime:
    local = datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00").replace(tzinfo=IST)
    return local.astimezone(timezone.utc)


def _bar(timeframe: str, start: datetime, open_: str, close: str, *, volume: int = 100, high: str | None = None, low: str | None = None) -> Candle:
    end = start + (timedelta(minutes=5) if timeframe == "5m" else timedelta(hours=6, minutes=15))
    opened = Decimal(open_)
    closed = Decimal(close)
    return Candle(
        symbol="ABC",
        exchange="NSE",
        timeframe=Timeframe(timeframe),
        open=opened,
        high=Decimal(high) if high is not None else max(opened, closed),
        low=Decimal(low) if low is not None else min(opened, closed),
        close=Decimal(close),
        volume=volume,
        start=start,
        end=end,
    )


def _daily(day: str, close: str) -> Candle:
    return _bar("1d", _at(day, 9, 15), close, close)


def _five(day: str, hour: int, minute: int, open_: str, close: str, *, volume: int = 100) -> Candle:
    return _bar("5m", _at(day, hour, minute), open_, close, volume=volume)


def test_trigger_uses_previous_close_and_next_open() -> None:
    daily = [_daily("2024-06-03", "100"), _daily("2024-06-04", "90"), _daily("2024-06-05", "110"), _daily("2024-06-06", "100")]
    bars = [
        _five("2024-06-04", 9, 15, "100", "98.5"),
        _five("2024-06-04", 9, 20, "97", "97", volume=999),
        _five("2024-06-04", 9, 25, "96", "96"),
    ]
    events, counts = collect_events("ABC", bars, daily)
    strategy = [
        trade
        for trade in simulate_symbol("ABC", bars, daily, variants=("baseline_today_drop",), modes=("delivery",))
        if trade["exit_reason"] != "unresolved" or trade["entry_price"] is not None
    ]
    assert counts["entries"] == 1
    assert counts["blocked_by_open_position"] >= 1
    assert events[0].entry_price == 97.0
    assert events[0].previous_close == 100.0
    assert events[0].signal_time == bars[0].end
    assert events[0].entry_time == bars[1].start
    assert len(strategy) == 1
    assert float(strategy[0]["entry_price"]) == events[0].entry_price


def test_other_session_entry_is_excluded() -> None:
    daily = [_daily("2024-06-03", "100"), _daily("2024-06-04", "90")]
    bars = [_five("2024-06-04", 14, 55, "99", "98"), _five("2024-06-05", 9, 15, "97", "97")]
    events, counts = collect_events("ABC", bars, daily)
    assert events == []
    assert counts["next_bar_other_session"] == 1


def test_two_session_label_and_cost() -> None:
    daily = [_daily("2024-06-03", "100"), _daily("2024-06-04", "90"), _daily("2024-06-05", "110"), _daily("2024-06-06", "100")]
    bars = [_five("2024-06-04", 9, 15, "100", "98"), _five("2024-06-04", 9, 20, "97", "97")]
    event = collect_events("ABC", bars, daily)[0][0]
    labeled = label_event(event, daily)
    assert labeled is not None
    assert labeled["outcome_session"] == date(2024, 6, 6)
    assert labeled["exit_price"] == 100.0
    assert labeled["net_return"] == net_return(97.0, 100.0)
    assert labeled["label"] == 1
    assert labeled["one_session_net_return"] == net_return(97.0, 110.0)
    assert outcome_bar(event.entry_session, daily, 2).close == Decimal("100")


def test_features_stop_at_the_trigger_and_reject_missing_history() -> None:
    opening = _at("2024-06-07", 9, 15)
    bars = []
    for index in range(30):
        close = 103 + (index % 3) * 0.4
        bars.append(_bar("5m", opening + timedelta(minutes=5 * index), str(close), str(close), volume=10 + index))
    trigger = _bar("5m", opening + timedelta(minutes=5 * 30), "103", "98", volume=50)
    entry = _bar("5m", opening + timedelta(minutes=5 * 31), "97.5", "97.5", volume=999999)
    bars.extend([trigger, entry])
    daily = [
        _daily("2024-06-03", "100"),
        _daily("2024-06-04", "101"),
        _daily("2024-06-05", "102"),
        _daily("2024-06-06", "103"),
        _daily("2024-06-07", "90"),
        _daily("2024-06-10", "100"),
        _daily("2024-06-11", "101"),
    ]
    events, _counts = collect_events("ABC", bars, daily)
    assert events
    event = events[0]
    history = [bar for bar in bars if bar.end <= event.signal_time]
    row, reason = feature_row(event, history)
    assert reason is None and row is not None
    assert len(row) == len(FEATURE_COLUMNS)
    short, short_reason = feature_row(event, history[:5])
    assert short is None and short_reason.startswith("missing_feature.")
    try:
        feature_row(event, history + [entry])
    except ValueError as exc:
        assert "after the trigger" in str(exc)
    else:
        raise AssertionError("entry bar was accepted as a feature")


def test_prefix_features_match_the_feature_engine() -> None:
    start = _at("2024-06-07", 9, 15)
    bars = []
    for index in range(40):
        close = 100 + (index % 7) * 0.3
        bars.append(_bar("5m", start + timedelta(minutes=5 * index), str(close), str(close + 0.1), volume=20 + index))
    cached = engine_features_for_prefixes(bars)
    for index in (20, 27, 39):
        built = build_feature_set("ABC", "5m", bars[: index + 1], bars[index].end)
        assert built is not None
        for name in (
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
        ):
            if name in built.features:
                assert cached[index][name] == built.features[name]


def test_split_purges_overlapping_outcomes() -> None:
    assert assign_split(date(2025, 6, 30), date(2025, 6, 30)) == "train"
    assert assign_split(date(2025, 6, 27), date(2025, 7, 1)) == "purged_train"
    assert assign_split(date(2025, 7, 1), date(2025, 7, 3)) == "validation"
    assert assign_split(date(2026, 1, 2), date(2026, 1, 6)) == "evaluation"


def test_scaler_fits_training_rows_only_and_is_deterministic() -> None:
    rows = [[float(index), float(index % 3)] + [0.1] * (len(FEATURE_COLUMNS) - 2) for index in range(40)]
    labels = [1 if index % 2 == 0 else 0 for index in range(40)]
    first = fit_pipeline(rows[:24], labels[:24])
    second = fit_pipeline(rows[:24], labels[:24])
    assert first.named_steps["scale"].n_samples_seen_ == 24
    assert predict_probability(first, rows[30]) == predict_probability(second, rows[30])
    assert select_threshold([0.2, 0.8, 0.9], [-0.1, 0.2, -0.05]) == 0.8


def test_artifact_hash_and_missing_feature_skip(tmp_path: Path) -> None:
    rows = [[0.01] * len(FEATURE_COLUMNS) for _ in range(20)]
    labels = [1 if index < 8 else 0 for index in range(20)]
    model = fit_pipeline(rows, labels)
    directory = tmp_path / "algo1"
    write_artifact(
        directory,
        model=model,
        model_version="algo1-logreg-v1",
        feature_version=FEATURE_VERSION,
        timeframe="5m",
        training_data_cutoff=datetime(2025, 6, 30, tzinfo=timezone.utc),
        trained_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
        label_horizon=2,
        embargo_bars=2,
        feature_columns=FEATURE_COLUMNS,
        training_data="nifty50_research_only",
        diagnostics={"research_only": True, "algorithm_id": "today_drop_ml_filter"},
    )
    loaded = ModelRegistry(directory).load(directory)
    assert loaded.manifest["feature_columns"] == list(FEATURE_COLUMNS)
    assert loaded.manifest["sha256"]
    try:
        finite_feature(float("nan"), "rsi_14")
    except ValueError:
        pass
    else:
        raise AssertionError("non-finite feature was accepted")
    paper = Path(__file__).resolve().parents[1] / "services" / "quant" / "src" / "quant_agents" / "paper.py"
    assert "today_drop_ml_filter" not in paper.read_text(encoding="utf-8")

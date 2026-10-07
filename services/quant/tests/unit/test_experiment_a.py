from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from quant_agents.ml.experiment_a import assign_splits, per_symbol_table, timestamp_splits
from quant_agents.ml.features import CURRENT_COLUMNS, NEW_COLUMNS, filter_new_eligible, relative_row


UTC = UTC


def _full_features(**overrides: float) -> dict[str, object]:
    base = {
        "feature_last_close": 100.0,
        "feature_last_volume": 10.0,
        "feature_period_high": 110.0,
        "feature_period_low": 90.0,
        "feature_volume_mean": 8.0,
        "feature_vwap": 101.0,
        "feature_sma_10": 98.0,
        "feature_sma_20": 97.0,
        "feature_ema_12": 99.0,
        "feature_ema_26": 96.0,
        "feature_macd": 0.4,
        "feature_macd_signal": 0.2,
        "feature_rsi_14": 55.0,
        "feature_atr_14": 1.5,
        "feature_bollinger_lower": 94.0,
        "feature_bollinger_upper": 106.0,
        "feature_return_1": 0.01,
        "feature_volatility": 0.02,
        "feature_momentum_10": 2.0,
    }
    base.update(overrides)
    return base


def _row(symbol: str, day: int, label: int, *, future_offset: int = 1, **overrides: float) -> dict[str, object]:
    start = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
    end = start + timedelta(days=day)
    future = start + timedelta(days=day + future_offset)
    payload = {
        "symbol": symbol,
        "end": end.isoformat(),
        "future_end": future.isoformat(),
        "label": label,
        "timeframe": "1d",
    }
    payload.update(_full_features(**overrides))
    return payload


def test_incomplete_warmup_dropped() -> None:
    incomplete = _row("AAA", 0, 1)
    del incomplete["feature_volatility"]
    complete = _row("AAA", 1, 0)
    kept, matrix, dropped = filter_new_eligible([incomplete, complete])
    assert dropped["missing_source"] == 1
    assert len(kept) == 1
    assert list(matrix[0]) == list(NEW_COLUMNS)


def test_relative_columns_present() -> None:
    features = relative_row(_row("AAA", 0, 1))
    assert set(features) == set(NEW_COLUMNS)
    assert features["close_sma_10"] == pytest.approx(100 / 98 - 1)


def test_shared_end_not_in_two_splits() -> None:
    rows = [_row("AAA", day, day % 2) for day in range(20)] + [_row("BBB", day, 1 - day % 2) for day in range(20)]
    train, valid, test, _, _, _ = assign_splits(rows, cutoff=datetime(2026, 1, 1, tzinfo=UTC))
    ends = (
        {str(r["end"]) for r in train},
        {str(r["end"]) for r in valid},
        {str(r["end"]) for r in test},
    )
    assert not (ends[0] & ends[1])
    assert not (ends[0] & ends[2])
    assert not (ends[1] & ends[2])
    shared = [r for r in train + valid if r["end"] == train[0]["end"]]
    symbols = {r["symbol"] for r in shared}
    assert symbols <= {"AAA", "BBB"}
    for row in shared:
        assert row in train


def test_train_row_future_end_equal_validation_start_removed() -> None:
    rows = [_row("AAA", day, day % 2) for day in range(20)]
    unique = timestamp_splits([str(r["end"]) for r in rows])
    validation_start = unique[0]
    victim = next(r for r in rows if r["end"] < validation_start)
    victim["future_end"] = validation_start
    train, _, _, purged, vs, _ = assign_splits(rows, cutoff=datetime(2026, 1, 1, tzinfo=UTC))
    assert vs == validation_start
    assert purged["train_cross"] >= 1
    assert all(r["future_end"] != vs for r in train)


def test_no_inf_nan_after_normalize() -> None:
    features = relative_row(_row("AAA", 0, 1))
    assert all(value == value and abs(value) != float("inf") for value in features.values())


def test_current_and_new_identical_ids() -> None:
    rows = [_row("AAA", day, day % 2) for day in range(20)]
    kept, matrix, _ = filter_new_eligible(rows)
    assert len(kept) == len(matrix)
    assert [f"{r['symbol']}|{r['end']}" for r in kept] == [f"{r['symbol']}|{r['end']}" for r in kept]
    train, valid, test, _, _, _ = assign_splits(kept, cutoff=datetime(2026, 1, 1, tzinfo=UTC))
    current_ids = [(r["symbol"], r["end"], int(r["label"])) for r in train + valid + test]
    new_ids = [(r["symbol"], r["end"], int(r["label"])) for r in train + valid + test]
    assert current_ids == new_ids


def test_per_symbol_auc_na_single_class() -> None:
    rows = [_row("AAA", 0, 1), _row("AAA", 1, 1)]
    table = per_symbol_table(rows, [1, 1], [0.6, 0.7])
    assert table[0]["roc_auc"] == "N/A"


def test_zero_denominator_dropped() -> None:
    row = _row("AAA", 0, 1, **{"feature_sma_10": 0.0})
    kept, _, dropped = filter_new_eligible([row])
    assert kept == []
    assert dropped["zero_denominator"] == 1


def test_missing_volatility_dropped() -> None:
    row = _row("AAA", 0, 1)
    del row["feature_volatility"]
    _, _, dropped = filter_new_eligible([row])
    assert dropped["missing_source"] == 1

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from quant_agents.dataset import filter_candles
from quant_agents.labelers import LABEL_VERSION
from quant_agents.ml.experiment import (
    REQUIRED_LOG_KEYS,
    previous_bar_predictions,
    run_experiment,
    score_split,
    train_majority,
)
from quant_agents.ml.splits import WalkForwardSplitter
from contracts.enums import Exchange, Timeframe
from contracts.schemas.market import Candle
from decimal import Decimal


def _write_parquet(path: Path, *, timeframe: str, n: int = 40, symbols: tuple[str, ...] | None = None) -> None:
    start = datetime(2024, 1, 2, 10, 0, tzinfo=UTC)
    names = symbols or ("RELIANCE",)
    rows = []
    for index in range(n):
        stamp = start + timedelta(days=index)
        future = stamp + timedelta(days=1)
        rows.append(
            {
                "symbol": names[index % len(names)],
                "timeframe": timeframe,
                "end": stamp.isoformat(),
                "future_end": future.isoformat(),
                "feature_last_close": float(100 + index % 7),
                "feature_rsi_14": float(40 + (index % 5)),
                "label": index % 2,
            }
        )
    table = pa.Table.from_pylist(rows)
    metadata = {
        b"snapshot_id": b"tiny-fixture",
        b"candle_sha256": b"abc123",
        b"feature_version": b"1.0.0",
        b"dataset_schema_version": b"1.0",
        b"label_version": LABEL_VERSION.encode(),
        b"timeframe": timeframe.encode(),
        b"training_data": b"real_snapshot",
        b"cutoff_source": b"explicit",
        b"training_data_cutoff": b"2026-09-01T10:00:00+00:00",
        b"label_horizon": b"1",
    }
    table = table.replace_schema_metadata(metadata)
    pq.write_table(table, path)


def test_chronological_and_walk_forward_do_not_peek_future(tmp_path: Path) -> None:
    parquet = tmp_path / "tiny-1d.parquet"
    _write_parquet(parquet, timeframe="1d")
    record = run_experiment(parquet, tmp_path / "baseline-1d", tmp_path / "log.jsonl")
    train_end = record["training_period"]["end"]
    valid_start = record["validation_period"]["start"]
    test_start = record["test_period"]["start"]
    assert train_end < valid_start
    assert valid_start < test_start
    assert "start_index" in record["split"]["train"]
    for fold in record["metrics"]["walk_forward"]:
        assert fold["train_period"]["end"] <= fold["validation_period"]["start"]


def test_walk_forward_index_embargo() -> None:
    splitter = WalkForwardSplitter(train_size=8, test_size=4, label_horizon=1)
    for train, test in splitter.split(40):
        assert test.start >= train.stop + 1


def test_experiment_log_keys_and_two_timeframe_artifacts(tmp_path: Path) -> None:
    log_path = tmp_path / "experiments" / "log.jsonl"
    daily = tmp_path / "tiny-1d.parquet"
    five = tmp_path / "tiny-5m.parquet"
    _write_parquet(daily, timeframe="1d")
    _write_parquet(five, timeframe="5m")
    run_experiment(daily, tmp_path / "artifacts" / "baseline-1d", log_path)
    run_experiment(five, tmp_path / "artifacts" / "baseline-5m", log_path)
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    for key in REQUIRED_LOG_KEYS:
        assert key in first
    assert first["label_version"] == "1.0"
    assert first["model_version"] == "1.0.0-baseline"
    assert "git_dirty" in first
    daily_manifest = json.loads((tmp_path / "artifacts" / "baseline-1d" / "manifest.json").read_text(encoding="utf-8"))
    five_manifest = json.loads((tmp_path / "artifacts" / "baseline-5m" / "manifest.json").read_text(encoding="utf-8"))
    assert daily_manifest["timeframe"] == "1d"
    assert five_manifest["timeframe"] == "5m"
    assert daily_manifest["label_version"] == "1.0"
    assert daily_manifest["snapshot_sha256"] == "abc123"
    assert (tmp_path / "artifacts" / "baseline-1d" / "model.joblib").is_file()
    assert (tmp_path / "artifacts" / "baseline-5m" / "model.joblib").is_file()


def test_majority_uses_train_labels_only() -> None:
    assert train_majority([0, 0, 1]) == 0
    assert train_majority([1, 1, 1, 0]) == 1


def test_previous_bar_does_not_leak_across_interleaved_symbols() -> None:
    rows = [
        {"symbol": "AAA", "end": "2024-01-01T10:00:00+00:00", "label": 1},
        {"symbol": "BBB", "end": "2024-01-01T10:00:00+00:00", "label": 0},
        {"symbol": "AAA", "end": "2024-01-02T10:00:00+00:00", "label": 1},
        {"symbol": "BBB", "end": "2024-01-02T10:00:00+00:00", "label": 0},
    ]
    preds = previous_bar_predictions(rows, fallback=0)
    assert preds[0] == 0
    assert preds[1] == 0
    assert preds[2] == 1
    assert preds[3] == 0


def test_score_split_fails_on_single_class() -> None:
    with pytest.raises(SystemExit, match="single class"):
        score_split([1, 1, 1], [1, 1, 1], [0.9, 0.8, 0.7], name="validation")


def test_missing_future_end_fails_cutoff_check(tmp_path: Path) -> None:
    parquet = tmp_path / "bad.parquet"
    _write_parquet(parquet, timeframe="1d", n=40)
    table = pq.read_table(parquet)
    rows = table.to_pylist()
    for row in rows:
        row["future_end"] = ""
    table = pa.Table.from_pylist(rows).replace_schema_metadata(table.schema.metadata)
    pq.write_table(table, parquet)
    with pytest.raises(SystemExit, match="future_end"):
        run_experiment(parquet, tmp_path / "out", tmp_path / "log.jsonl")


def test_end_before_filters_by_candle_end() -> None:
    t0 = datetime(2024, 6, 3, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(days=1)
    candles = (
        Candle(
            symbol="TCS",
            exchange=Exchange.NSE,
            timeframe=Timeframe.D1,
            open=Decimal("10"),
            high=Decimal("11"),
            low=Decimal("9"),
            close=Decimal("10"),
            volume=1,
            start=t0 - timedelta(hours=6),
            end=t0,
        ),
        Candle(
            symbol="TCS",
            exchange=Exchange.NSE,
            timeframe=Timeframe.D1,
            open=Decimal("11"),
            high=Decimal("12"),
            low=Decimal("10"),
            close=Decimal("11"),
            volume=1,
            start=t1 - timedelta(hours=6),
            end=t1,
        ),
    )
    kept = filter_candles(candles, end_before=t1)
    assert len(kept) == 1
    assert kept[0].end == t0

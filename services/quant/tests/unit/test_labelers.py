from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from contracts.enums import Exchange, Timeframe
from contracts.schemas.market import Candle

from quant_agents.dataset import build_rows
from quant_agents.labelers import (
    IST,
    make_labeler,
    parse_label_horizon,
    resolve_cutoff,
    series_for,
    session_date_ist,
)
from quant_agents.ml.artifact import read_manifest, write_artifact
from quant_agents.ml.model import make_model

UTC = timezone.utc


def _bar(
    symbol: str,
    end: datetime,
    close: str,
    *,
    timeframe: Timeframe = Timeframe.D1,
    start: datetime | None = None,
) -> Candle:
    price = Decimal(close)
    open_at = start or end - timedelta(hours=6)
    return Candle(
        symbol=symbol,
        exchange=Exchange.NSE,
        timeframe=timeframe,
        open=price,
        high=price + Decimal("1"),
        low=price - Decimal("1"),
        close=price,
        volume=100,
        start=open_at,
        end=end,
    )


def test_parse_label_horizon_rejects_bad_values() -> None:
    with pytest.raises(SystemExit):
        parse_label_horizon("0")
    with pytest.raises(SystemExit):
        parse_label_horizon("x")


def test_real_snapshot_requires_cutoff() -> None:
    with pytest.raises(SystemExit, match="QUANT_TRAINING_DATA_CUTOFF"):
        resolve_cutoff(training_data="real_snapshot")


def test_equal_close_dropped() -> None:
    t0 = datetime(2024, 6, 3, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(days=1)
    candles = [_bar("TCS", t0, "10"), _bar("TCS", t1, "10")]
    labeler, stats, _ = make_labeler(cutoff=t1, cutoff_source="documented_split")
    assert labeler("TCS", t0, candles) is None
    assert stats.dropped_equal == 1


def test_last_bar_without_future_excluded() -> None:
    t0 = datetime(2024, 6, 3, 10, 0, tzinfo=UTC)
    candles = [_bar("TCS", t0, "10")]
    labeler, stats, _ = make_labeler(cutoff=t0, cutoff_source="documented_split")
    assert labeler("TCS", t0, candles) is None
    assert stats.dropped_no_future == 1


def test_label_past_cutoff_excluded() -> None:
    t0 = datetime(2024, 6, 3, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(days=1)
    candles = [_bar("TCS", t0, "10"), _bar("TCS", t1, "11")]
    labeler, stats, _ = make_labeler(cutoff=t0, cutoff_source="documented_split")
    assert labeler("TCS", t0, candles) is None
    assert stats.dropped_cutoff == 1


def test_horizon_two_uses_second_later_bar() -> None:
    t0 = datetime(2024, 6, 3, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(days=1)
    t2 = t0 + timedelta(days=2)
    candles = [_bar("TCS", t0, "10"), _bar("TCS", t1, "9"), _bar("TCS", t2, "12")]
    labeler, stats, config = make_labeler(label_horizon=2, cutoff=t2, cutoff_source="documented_split")
    assert config.label_horizon == 2
    assert labeler("TCS", t0, candles) == 1
    assert stats.labeled_up == 1


def test_interleaved_timeframes_do_not_cross() -> None:
    d0 = datetime(2024, 6, 3, 10, 0, tzinfo=UTC)
    m0 = datetime(2024, 6, 3, 4, 0, tzinfo=UTC)
    d1 = datetime(2024, 6, 4, 10, 0, tzinfo=UTC)
    candles = [
        _bar("TCS", d0, "10", timeframe=Timeframe.D1),
        _bar("TCS", m0, "99", timeframe=Timeframe.M5, start=m0 - timedelta(minutes=5)),
        _bar("TCS", d1, "11", timeframe=Timeframe.D1),
    ]
    labeler, _stats, _ = make_labeler(cutoff=d1, cutoff_source="documented_split")
    assert labeler("TCS", d0, candles) == 1
    series = series_for("TCS", d0, candles)
    assert [bar.timeframe for bar in series] == [Timeframe.D1, Timeframe.D1]


def test_duplicate_end_fails() -> None:
    t0 = datetime(2024, 6, 3, 10, 0, tzinfo=UTC)
    candles = [_bar("TCS", t0, "10"), _bar("TCS", t0, "11")]
    with pytest.raises(ValueError, match="duplicate end"):
        series_for("TCS", t0, candles)


def test_overnight_5m_dropped() -> None:
    late = datetime(2024, 6, 3, 9, 45, tzinfo=UTC)
    nxt = datetime(2024, 6, 4, 3, 45, tzinfo=UTC)
    candles = [
        _bar("TCS", late, "10", timeframe=Timeframe.M5, start=late - timedelta(minutes=5)),
        _bar("TCS", nxt, "11", timeframe=Timeframe.M5, start=nxt - timedelta(minutes=5)),
    ]
    labeler, stats, _ = make_labeler(cutoff=nxt, cutoff_source="documented_split")
    assert labeler("TCS", late, candles) is None
    assert stats.dropped_overnight == 1


def test_ist_session_times() -> None:
    start = datetime(2026, 6, 25, 3, 45, tzinfo=UTC)
    end = datetime(2026, 6, 25, 10, 0, tzinfo=UTC)
    assert start.astimezone(IST).hour == 9
    assert start.astimezone(IST).minute == 15
    assert end.astimezone(IST).hour == 15
    assert end.astimezone(IST).minute == 30
    assert session_date_ist(end).isoformat() == "2026-06-25"


def test_two_runs_report_identical_counts() -> None:
    t0 = datetime(2024, 6, 3, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(days=1)
    t2 = t0 + timedelta(days=2)
    candles = [_bar("TCS", t0, "10"), _bar("TCS", t1, "11"), _bar("TCS", t2, "10")]
    first = make_labeler(cutoff=t2, cutoff_source="documented_split")
    second = make_labeler(cutoff=t2, cutoff_source="documented_split")
    for stamp in (t0, t1, t2):
        first[0]("TCS", stamp, candles)
        second[0]("TCS", stamp, candles)
    assert first[1] == second[1]


def _write_snap(directory: Path, candles: list[Candle]) -> Path:
    import hashlib
    import json

    directory.mkdir(parents=True, exist_ok=True)
    lines = []
    for bar in candles:
        payload = {
            "close": float(bar.close),
            "end": bar.end.isoformat(),
            "exchange": "NSE",
            "high": float(bar.high),
            "low": float(bar.low),
            "open": float(bar.open),
            "start": bar.start.isoformat(),
            "symbol": bar.symbol,
            "timeframe": bar.timeframe.value,
            "volume": int(bar.volume),
        }
        lines.append(json.dumps(payload, sort_keys=True))
    body = "\n".join(lines) + "\n"
    (directory / "candles.jsonl").write_text(body, encoding="utf-8")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    manifest = {
        "candle_sha256": digest,
        "snapshot_id": digest,
        "timeframes": ["1d"],
        "universe": "NIFTY50",
        "symbols": [],
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return directory


def test_inspect_output_matches_stats(tmp_path: Path) -> None:
    t0 = datetime(2024, 6, 3, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(days=1)
    t2 = t0 + timedelta(days=2)
    t3 = t0 + timedelta(days=3)
    candles = [
        _bar("TCS", t0, "10"),
        _bar("TCS", t1, "11"),
        _bar("TCS", t2, "11"),
        _bar("TCS", t3, "9"),
    ]
    snap = _write_snap(tmp_path / "snap", candles)
    rows, metadata, stats = build_rows(
        snap,
        timeframe=Timeframe.D1,
        cutoff=t3,
        cutoff_source="documented_split",
        training_data="synthetic_fixture",
    )
    labels = [int(row["label"]) for row in rows]
    assert labels.count(1) == stats.labeled_up
    assert labels.count(0) == stats.labeled_down
    assert all(datetime.fromisoformat(str(row["end"])).tzinfo is not None for row in rows)
    assert "TCS" in {row["symbol"] for row in rows}
    last_as_of = max(datetime.fromisoformat(str(row["end"])) for row in rows)
    assert last_as_of < t3
    assert metadata["cutoff_source"] == "documented_split"
    assert metadata["survivorship_bias"] == "current_nifty50_constituents"


def test_mutating_future_bar_does_not_change_features(tmp_path: Path) -> None:
    import json

    t0 = datetime(2024, 6, 3, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(days=1)
    snap = _write_snap(tmp_path / "snap", [_bar("TCS", t0, "10"), _bar("TCS", t1, "11")])
    before, _, _ = build_rows(
        snap,
        timeframe=Timeframe.D1,
        cutoff=t1,
        cutoff_source="documented_split",
    )
    path = snap / "candles.jsonl"
    mutated = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["end"].startswith("2024-06-04"):
            row["close"] = 1.0
            row["open"] = 1.0
            row["high"] = 2.0
            row["low"] = 0.5
        mutated.append(json.dumps(row, sort_keys=True))
    path.write_text("\n".join(mutated) + "\n", encoding="utf-8")
    after, _, _ = build_rows(
        snap,
        timeframe=Timeframe.D1,
        cutoff=t1,
        cutoff_source="documented_split",
    )
    feat = lambda row: {key: value for key, value in row.items() if key.startswith("feature_")}
    assert feat(before[0]) == feat(after[0])
    assert before[0]["label"] != after[0]["label"]


def test_model_manifest_omits_non_explicit_cutoff(tmp_path: Path) -> None:
    cutoff = datetime(2024, 3, 15, 10, 0, tzinfo=UTC)
    model = make_model()
    model.fit([[0.0] * 13, [1.0] * 13], [0, 1])
    write_artifact(
        tmp_path,
        model=model,
        model_version="1.0.0-baseline",
        feature_version="1.0.0",
        timeframe="1d",
        training_data_cutoff=cutoff,
        trained_at=cutoff,
        label_horizon=1,
        embargo_bars=1,
        diagnostics={},
        cutoff_source="documented_split",
        training_data="synthetic_fixture",
    )
    manifest = read_manifest(tmp_path / "manifest.json")
    assert "training_data_cutoff" not in manifest
    assert manifest["survivorship_bias"] == "current_nifty50_constituents"
    assert manifest["prices_adjusted"] == "unspecified"
    assert manifest["baseline"] is True
    assert manifest["label_version"] == "1.0"

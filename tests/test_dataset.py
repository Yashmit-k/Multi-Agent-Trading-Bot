"""Dataset rows. Features stop at T. The labeler may read the next bar."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq

from contracts.enums import Exchange, Timeframe
from contracts.schemas.market import Candle
from core_db.repository import CoreRepository
from core_features.engine import FEATURE_VERSION
from core_market_data.snapshot import export_snapshot
from quant_agents.dataset import DATASET_SCHEMA_VERSION, build_dataset, build_rows, load_labeler, resolve_snapshot_path
from quant_agents.history import replay_from_settings
from quant_agents.service import create_app
from quant_agents.settings import QuantSettings
from contracts.enums import TradingMode

UTC = timezone.utc
FIRST = datetime(2024, 6, 3, 10, 0, tzinfo=UTC)
SECOND = FIRST + timedelta(days=1)


def _bar(symbol: str, end: datetime, close: str) -> Candle:
    price = Decimal(close)
    return Candle(
        symbol=symbol,
        exchange=Exchange.NSE,
        timeframe=Timeframe.D1,
        open=price - Decimal("1"),
        high=price + Decimal("1"),
        low=price - Decimal("2"),
        close=price,
        volume=100,
        start=end - timedelta(hours=6),
        end=end,
    )


def _label_next_close(symbol: str, as_of: datetime, candles) -> str | None:
    later = sorted(
        (bar for bar in candles if bar.symbol == symbol and bar.timeframe == Timeframe.D1 and bar.end > as_of),
        key=lambda bar: bar.end,
    )
    if not later:
        return None
    return format(later[0].close, "f")


def _snapshot(repository: CoreRepository, directory: Path) -> Path:
    repository.upsert_candles(
        [
            _bar("TCS", FIRST, "10"),
            _bar("TCS", SECOND, "11"),
            _bar("RELIANCE", FIRST, "100"),
            _bar("RELIANCE", SECOND, "110"),
        ]
    )
    export_snapshot(repository, directory, as_of=SECOND + timedelta(days=1), symbols=("RELIANCE", "TCS"))
    return directory


def test_incomplete_label_windows_are_dropped_and_rows_are_sorted(repository: CoreRepository, tmp_path: Path) -> None:
    snapshot = _snapshot(repository, tmp_path / "snap")
    out = tmp_path / "training.parquet"
    written = build_dataset(snapshot, out, _label_next_close)
    assert written == 2
    table = pq.read_table(out)
    symbols = table.column("symbol").to_pylist()
    assert symbols == ["RELIANCE", "TCS"]
    assert [Decimal(item) for item in table.column("label").to_pylist()] == [Decimal("110"), Decimal("11")]
    metadata = {key.decode(): value.decode() for key, value in table.schema.metadata.items()}
    assert metadata["feature_version"] == FEATURE_VERSION
    assert metadata["dataset_schema_version"] == DATASET_SCHEMA_VERSION
    assert metadata["label_version"] == "1.0"
    assert metadata["timeframe"] == "1d,5m"
    assert metadata["snapshot_id"] == metadata["candle_sha256"]
    assert len(metadata["snapshot_id"]) == 64


def test_mutating_a_future_bar_does_not_change_features(repository: CoreRepository, tmp_path: Path) -> None:
    snapshot = _snapshot(repository, tmp_path / "snap")
    before, _, _ = build_rows(snapshot, _label_next_close)
    path = snapshot / "candles.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    mutated = []
    for line in lines:
        row = json.loads(line)
        if row["symbol"] == "RELIANCE" and row["end"].startswith("2024-06-04"):
            row["open"] = 999999.99
            row["high"] = 1000000.99
            row["low"] = 999998.99
            row["close"] = 999999.99
        mutated.append(json.dumps(row))
    path.write_text("\n".join(mutated) + "\n", encoding="utf-8")
    after, _, _ = build_rows(snapshot, _label_next_close)
    reliance_before = next(row for row in before if row["symbol"] == "RELIANCE")
    reliance_after = next(row for row in after if row["symbol"] == "RELIANCE")
    before_features = {key: value for key, value in reliance_before.items() if key.startswith("feature_")}
    after_features = {key: value for key, value in reliance_after.items() if key.startswith("feature_")}
    assert before_features == after_features
    assert reliance_before["label"] != reliance_after["label"]


def test_snapshot_flag_beats_the_env_var(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("QUANT_SNAPSHOT_PATH", str(tmp_path / "from-env"))
    chosen = resolve_snapshot_path(str(tmp_path / "from-flag"))
    assert chosen == tmp_path / "from-flag"
    try:
        load_labeler("")
    except SystemExit as exc:
        assert "Dev 2" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_historical_mode_does_not_need_zerodha(repository: CoreRepository, tmp_path: Path, monkeypatch) -> None:
    snapshot = _snapshot(repository, tmp_path / "snap")
    monkeypatch.delenv("ZERODHA_API_KEY", raising=False)
    monkeypatch.delenv("ZERODHA_API_SECRET", raising=False)
    monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)
    settings = QuantSettings(
        data_source="historical",
        trading_mode=TradingMode.BACKTEST,
        log_level="INFO",
        artifact_dir=None,
        horizons_path=None,
        snapshot_path=str(snapshot),
    )
    replay = replay_from_settings(settings)
    quote = replay.get_quote("RELIANCE", FIRST)
    assert quote.last_price == Decimal("100")
    app = create_app(settings)
    assert app.state.market_data is not None

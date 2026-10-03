"""Build one training parquet from a candle snapshot. The label function belongs to Dev 2.

The labeler may read candles after T. The feature engine may never see past T.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from contracts.enums import Timeframe
from contracts.schemas.feature_set import FeatureSet
from contracts.schemas.market import Candle
from core_features.engine import FEATURE_VERSION, build_feature_set
from core_market_data.replay import HistoricalReplayMarketDataProvider
from core_market_data.snapshot import load_snapshot

DATASET_SCHEMA_VERSION = "1.0"

Labeler = Callable[[str, datetime, tuple[Candle, ...] | list[Candle]], object | None]


def resolve_snapshot_path(flag: str | None, env: str | None = None) -> Path:
    """The --snapshot flag wins. QUANT_SNAPSHOT_PATH is only the default."""
    chosen = flag if flag else env if env is not None else os.environ.get("QUANT_SNAPSHOT_PATH", "")
    if not chosen:
        raise SystemExit("pass --snapshot or set QUANT_SNAPSHOT_PATH")
    return Path(chosen)


def load_labeler(spec: str | None = None) -> Labeler:
    raw = spec if spec is not None else os.environ.get("QUANT_LABELER", "")
    if not raw or ":" not in raw:
        raise SystemExit("QUANT_LABELER must be module:function; Dev 2 supplies the label")
    module_name, function_name = raw.split(":", 1)
    module = importlib.import_module(module_name)
    function = getattr(module, function_name)
    return function


def build_rows(snapshot_dir: Path, labeler: Labeler) -> tuple[list[dict[str, object]], dict[str, str]]:
    snapshot = load_snapshot(snapshot_dir)
    replay = HistoricalReplayMarketDataProvider.from_snapshot(snapshot_dir, _ceiling(snapshot.candles))
    rows: list[dict[str, object]] = []
    for bar in snapshot.candles:
        moment = bar.end
        visible = replay.get_candles(bar.symbol, bar.timeframe, _floor(), moment)
        features = build_feature_set(bar.symbol, bar.timeframe, visible, moment)
        if features is None:
            continue
        label = labeler(bar.symbol, moment, snapshot.candles)
        if label is None:
            continue
        rows.append(_row(bar, features, label))
    rows.sort(key=lambda item: (str(item["symbol"]), str(item["timeframe"]), str(item["end"])))
    manifest = snapshot.manifest
    metadata = {
        "snapshot_id": str(manifest["snapshot_id"]),
        "candle_sha256": str(manifest["candle_sha256"]),
        "feature_version": FEATURE_VERSION,
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "timeframe": ",".join(str(item) for item in manifest["timeframes"]),
    }
    return rows, metadata


def write_parquet(rows: list[dict[str, object]], metadata: dict[str, str], out: Path) -> None:
    table = pa.Table.from_pylist(rows)
    encoded = {key.encode("utf-8"): value.encode("utf-8") for key, value in metadata.items()}
    table = table.replace_schema_metadata(encoded)
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out)


def build_dataset(snapshot_dir: Path, out: Path, labeler: Labeler) -> int:
    rows, metadata = build_rows(snapshot_dir, labeler)
    write_parquet(rows, metadata, out)
    return len(rows)


def _row(bar: Candle, features: FeatureSet, label: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "symbol": bar.symbol,
        "timeframe": bar.timeframe.value if isinstance(bar.timeframe, Timeframe) else str(bar.timeframe),
        "end": bar.end.isoformat(),
        "label": str(label),
    }
    for name in sorted(features.features):
        payload[f"feature_{name}"] = features.features[name]
    return payload


def _ceiling(candles: tuple[Candle, ...]) -> datetime:
    from datetime import timezone

    if not candles:
        return datetime.now(timezone.utc)
    return max(bar.end for bar in candles)


def _floor() -> datetime:
    from datetime import timezone

    return datetime.min.replace(tzinfo=timezone.utc)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build a training parquet from a candle snapshot")
    parser.add_argument("--snapshot", default=None)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    snapshot = resolve_snapshot_path(args.snapshot)
    written = build_dataset(snapshot, args.out, load_labeler())
    print(written)

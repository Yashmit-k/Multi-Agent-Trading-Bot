"""Build one training parquet from a candle snapshot.

The labeler may read candles after T. The feature engine may never see past T.
t+h is the h-th later bar that exists on the same (symbol, timeframe) series.
"""

from __future__ import annotations

import importlib
import os
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from contracts.enums import Timeframe
from contracts.schemas.feature_set import FeatureSet
from contracts.schemas.market import Candle
from core_features.engine import FEATURE_VERSION, build_feature_set
from core_market_data.replay import HistoricalReplayMarketDataProvider
from core_market_data.snapshot import load_snapshot

from quant_agents.labelers import LABEL_VERSION, LabelConfig, LabelStats, make_labeler

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


def bind_configured_labeler(
    spec: str | None = None,
    *,
    cutoff: datetime | None = None,
    cutoff_source: str | None = None,
    training_data: str = "synthetic_fixture",
    label_horizon: int | None = None,
) -> tuple[Labeler, LabelStats, LabelConfig | None]:
    raw = spec if spec is not None else os.environ.get("QUANT_LABELER", "quant_agents.labelers:next_close_direction")
    if raw.endswith(":next_close_direction"):
        return make_labeler(
            label_horizon=label_horizon,
            cutoff=cutoff,
            cutoff_source=cutoff_source,
            training_data=training_data,
        )
    return load_labeler(raw), LabelStats(), None


def _parse_end_before(raw: str | datetime | None) -> datetime | None:
    if raw is None or raw == "":
        return None
    stamp = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
    if stamp.tzinfo is None:
        raise SystemExit("--end-before must be timezone-aware")
    return stamp


def filter_candles(
    candles: tuple[Candle, ...] | list[Candle],
    *,
    timeframe: Timeframe | None = None,
    symbol: str | None = None,
    end_before: datetime | None = None,
) -> tuple[Candle, ...]:
    selected = tuple(candles)
    if timeframe is not None:
        selected = tuple(bar for bar in selected if _bar_timeframe(bar) == timeframe)
    if symbol:
        selected = tuple(bar for bar in selected if bar.symbol == symbol)
    if end_before is not None:
        selected = tuple(bar for bar in selected if bar.end < end_before)
    return selected


def build_rows(
    snapshot_dir: Path,
    labeler: Labeler | None = None,
    *,
    timeframe: Timeframe | None = None,
    cutoff: datetime | None = None,
    cutoff_source: str | None = None,
    training_data: str = "synthetic_fixture",
    label_horizon: int | None = None,
    symbol: str | None = None,
    end_before: datetime | str | None = None,
) -> tuple[list[dict[str, object]], dict[str, str], LabelStats]:
    snapshot = load_snapshot(snapshot_dir)
    stats: LabelStats
    config: LabelConfig | None
    bound = labeler
    if bound is None:
        bound, stats, config = bind_configured_labeler(
            cutoff=cutoff,
            cutoff_source=cutoff_source,
            training_data=training_data,
            label_horizon=label_horizon,
        )
    else:
        stats = LabelStats()
        config = None
    range_end = _parse_end_before(end_before)
    candles = filter_candles(
        snapshot.candles,
        timeframe=timeframe,
        symbol=symbol,
        end_before=range_end,
    )
    stats.input_bars = len(candles)
    replay = HistoricalReplayMarketDataProvider.from_snapshot(snapshot_dir, _ceiling(snapshot.candles))
    rows: list[dict[str, object]] = []
    for bar in candles:
        moment = bar.end
        visible = replay.get_candles(bar.symbol, bar.timeframe, _floor(), moment)
        features = build_feature_set(bar.symbol, bar.timeframe, visible, moment)
        if features is None:
            stats.skipped_features += 1
            continue
        label = bound(bar.symbol, moment, candles)
        if label is None:
            continue
        rows.append(_row(bar, features, label, future_end=stats.last_future_end))
    rows.sort(key=lambda item: (str(item["symbol"]), str(item["timeframe"]), str(item["end"])))
    metadata = _metadata(snapshot.manifest, stats, config, timeframe, training_data)
    return rows, metadata, stats


def write_parquet(rows: list[dict[str, object]], metadata: dict[str, str], out: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    if not rows:
        raise SystemExit("parquet has no rows")
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    table = pa.table({key: [row.get(key) for row in rows] for key in keys})
    encoded = {key.encode("utf-8"): value.encode("utf-8") for key, value in metadata.items()}
    table = table.replace_schema_metadata(encoded)
    out.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=out.parent, prefix=f".{out.name}.", suffix=".tmp", delete=False)
    temp_path = Path(handle.name)
    handle.close()
    try:
        pq.write_table(table, temp_path)
        os.replace(temp_path, out)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise


def build_dataset(
    snapshot_dir: Path,
    out: Path,
    labeler: Labeler | None = None,
    *,
    timeframe: Timeframe | None = None,
    cutoff: datetime | None = None,
    cutoff_source: str | None = None,
    training_data: str = "synthetic_fixture",
    label_horizon: int | None = None,
    symbol: str | None = None,
    end_before: datetime | str | None = None,
) -> int:
    rows, metadata, _stats = build_rows(
        snapshot_dir,
        labeler,
        timeframe=timeframe,
        cutoff=cutoff,
        cutoff_source=cutoff_source,
        training_data=training_data,
        label_horizon=label_horizon,
        symbol=symbol,
        end_before=end_before,
    )
    write_parquet(rows, metadata, out)
    return len(rows)


def _metadata(
    manifest: dict[str, object],
    stats: LabelStats,
    config: LabelConfig | None,
    timeframe: Timeframe | None,
    training_data: str,
) -> dict[str, str]:
    if timeframe is not None:
        tf = timeframe.value
    else:
        raw = manifest.get("timeframes") or []
        tf = ",".join(str(item) for item in raw)
    payload = {
        "snapshot_id": str(manifest.get("snapshot_id", "")),
        "candle_sha256": str(manifest.get("candle_sha256", "")),
        "feature_version": FEATURE_VERSION,
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "label_version": LABEL_VERSION,
        "timeframe": tf,
        "training_data": training_data,
        "baseline": "true",
        "prices_adjusted": "unspecified",
        "survivorship_bias": "current_nifty50_constituents",
        "overnight_5m": "dropped",
        "t_plus_h": "next_existing_bar_same_symbol_timeframe",
        "dropped_equal": str(stats.dropped_equal),
        "dropped_no_future": str(stats.dropped_no_future),
        "dropped_cutoff": str(stats.dropped_cutoff),
        "dropped_overnight": str(stats.dropped_overnight),
        "labeled_up": str(stats.labeled_up),
        "labeled_down": str(stats.labeled_down),
        "input_bars": str(stats.input_bars),
        "skipped_features": str(stats.skipped_features),
        "kept_rows": str(stats.labeled_up + stats.labeled_down),
    }
    if config is not None:
        payload["label_horizon"] = str(config.label_horizon)
        payload["cutoff_source"] = config.cutoff_source
        payload["training_data_cutoff"] = config.training_data_cutoff.isoformat()
    return payload


def _bar_timeframe(bar: Candle) -> Timeframe:
    raw = bar.timeframe
    return raw if isinstance(raw, Timeframe) else Timeframe(str(raw))


def _row(bar: Candle, features: FeatureSet, label: object, *, future_end: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "symbol": bar.symbol,
        "timeframe": bar.timeframe.value if isinstance(bar.timeframe, Timeframe) else str(bar.timeframe),
        "end": bar.end.isoformat(),
        "future_end": future_end or "",
        "label": str(label),
    }
    for name in sorted(features.features):
        payload[f"feature_{name}"] = features.features[name]
    return payload


def _ceiling(candles: tuple[Candle, ...]) -> datetime:
    if not candles:
        return datetime.now(timezone.utc)
    return max(bar.end for bar in candles)


def _floor() -> datetime:
    return datetime.min.replace(tzinfo=timezone.utc)


def main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Build a training parquet from a candle snapshot")
    parser.add_argument("--snapshot", default=None)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--timeframe", required=True, help="Single timeframe, e.g. 1d or 5m")
    parser.add_argument("--training-data", default="real_snapshot")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--end-before", default=None, help="Exclusive filter on candle end (timezone-aware ISO)")
    args = parser.parse_args()
    snapshot = resolve_snapshot_path(args.snapshot)
    rows, metadata, stats = build_rows(
        snapshot,
        timeframe=Timeframe(args.timeframe),
        training_data=args.training_data,
        symbol=args.symbol,
        end_before=args.end_before,
    )
    write_parquet(rows, metadata, args.out)
    print(
        json.dumps(
            {
                "kept": len(rows),
                "input_bars": stats.input_bars,
                "skipped_features": stats.skipped_features,
                "dropped_equal": stats.dropped_equal,
                "dropped_no_future": stats.dropped_no_future,
                "dropped_cutoff": stats.dropped_cutoff,
                "dropped_overnight": stats.dropped_overnight,
                "labeled_up": stats.labeled_up,
                "labeled_down": stats.labeled_down,
                "out": str(args.out),
            }
        )
    )


if __name__ == "__main__":
    main()

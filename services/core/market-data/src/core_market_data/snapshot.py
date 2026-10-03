"""Credential-free candle snapshot. The candle file hash does not depend on created_at."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from contracts.enums import Timeframe
from contracts.schemas.market import Candle
from core_db.repository import CoreRepository
from core_db.seed import SEED_PATH

SCHEMA_VERSION = "1.0"
UNIVERSE = "NIFTY50"
SNAPSHOT_TIMEFRAMES = (Timeframe.D1, Timeframe.M5)
_FORBIDDEN = ("ZERODHA", "api_key", "api_secret", "access_token", "instrument_token")


@dataclass(frozen=True, slots=True)
class CandleSnapshot:
    directory: Path
    manifest: dict[str, object]
    candles: tuple[Candle, ...]


def seed_symbols(path: Path = SEED_PATH) -> tuple[str, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        names = [row["symbol"].strip().upper() for row in csv.DictReader(handle) if row["symbol"].strip()]
    return tuple(names)


def export_snapshot(
    repository: CoreRepository,
    directory: Path,
    *,
    as_of: datetime,
    created_at: datetime | None = None,
    symbols: tuple[str, ...] | None = None,
) -> CandleSnapshot:
    """Write candles.jsonl and manifest.json. Rows are ordered so the hash is stable."""
    directory.mkdir(parents=True, exist_ok=True)
    names = symbols if symbols is not None else seed_symbols()
    moment = _aware(as_of)
    selected: list[Candle] = []
    for symbol in names:
        for timeframe in SNAPSHOT_TIMEFRAMES:
            for bar in repository.stored_candles(symbol, timeframe):
                if bar.end <= moment:
                    selected.append(bar)
    selected.sort(key=lambda bar: (bar.symbol, bar.timeframe.value, bar.end))
    candle_path = directory / "candles.jsonl"
    body = "".join(_line(bar) for bar in selected)
    candle_path.write_text(body, encoding="utf-8")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": digest,
        "created_at": _aware(created_at or datetime.now(timezone.utc)).isoformat(),
        "universe": UNIVERSE,
        "timeframes": [item.value for item in SNAPSHOT_TIMEFRAMES],
        "candle_sha256": digest,
        "symbols": [_symbol_entry(symbol, selected) for symbol in names],
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return CandleSnapshot(directory=directory, manifest=manifest, candles=tuple(selected))


def load_snapshot(directory: Path) -> CandleSnapshot:
    folder = Path(directory)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    candles: list[Candle] = []
    raw = (folder / "candles.jsonl").read_text(encoding="utf-8")
    for line in raw.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line, parse_float=Decimal, parse_int=int)
        candles.append(
            Candle(
                symbol=payload["symbol"],
                exchange=payload["exchange"],
                timeframe=payload["timeframe"],
                open=Decimal(payload["open"]),
                high=Decimal(payload["high"]),
                low=Decimal(payload["low"]),
                close=Decimal(payload["close"]),
                volume=int(payload["volume"]),
                start=datetime.fromisoformat(payload["start"]),
                end=datetime.fromisoformat(payload["end"]),
            )
        )
    return CandleSnapshot(directory=folder, manifest=manifest, candles=tuple(candles))


def _symbol_entry(symbol: str, candles: list[Candle]) -> dict[str, object]:
    owned = [bar for bar in candles if bar.symbol == symbol]
    return {
        "symbol": symbol,
        "count": len(owned),
        "first_bar": _aware(owned[0].start).isoformat() if owned else None,
        "last_bar": _aware(owned[-1].end).isoformat() if owned else None,
    }


def _line(bar: Candle) -> str:
    fields = [
        ("close", _number(bar.close)),
        ("end", json.dumps(_aware(bar.end).isoformat())),
        ("exchange", json.dumps(bar.exchange.value)),
        ("high", _number(bar.high)),
        ("low", _number(bar.low)),
        ("open", _number(bar.open)),
        ("start", json.dumps(_aware(bar.start).isoformat())),
        ("symbol", json.dumps(bar.symbol)),
        ("timeframe", json.dumps(bar.timeframe.value)),
        ("volume", str(int(bar.volume))),
    ]
    body = ",".join(f"{json.dumps(key)}:{value}" for key, value in fields)
    return "{" + body + "}\n"


def _number(value: Decimal) -> str:
    return format(value, "f")


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def main() -> None:
    import argparse
    import os

    from core_db.repository import CoreRepository
    from core_db.session import create_schema

    parser = argparse.ArgumentParser(description="Export a NIFTY 50 candle snapshot")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    repository = CoreRepository(create_schema(os.environ.get("DATABASE_URL", "sqlite:///./core.db")))
    snapshot = export_snapshot(repository, args.out, as_of=datetime.now(timezone.utc))
    print(snapshot.manifest["snapshot_id"])


if __name__ == "__main__":
    main()

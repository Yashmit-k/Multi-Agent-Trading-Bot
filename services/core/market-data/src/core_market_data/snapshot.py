"""Credential-free candle snapshot. The candle file hash does not depend on created_at."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from contracts.enums import Timeframe
from contracts.schemas.market import Candle
from core_db.repository import CoreRepository
from core_db.seed import SEED_PATH

SCHEMA_VERSION = "1.0"
UNIVERSE = "NIFTY50"
SNAPSHOT_TIMEFRAMES = (Timeframe.D1, Timeframe.M5)
IST = ZoneInfo("Asia/Kolkata")
_FORBIDDEN = ("ZERODHA", "api_key", "api_secret", "access_token", "instrument_token")


@dataclass(frozen=True, slots=True)
class CandleSnapshot:
    directory: Path
    manifest: dict[str, object]
    candles: tuple[Candle, ...]


def seed_symbols(path: Path = SEED_PATH) -> tuple[str, ...]:
    """Names in the frozen research universe.

    A listing that opens after 2024-01-01 is a later member of the live
    universe. It stays out of this tuple, so research snapshots keep the
    original fifty names, including TATAMOTORS with zero bars.
    """
    anchor = datetime(2024, 1, 1, tzinfo=timezone.utc)
    names: list[str] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            symbol = row["symbol"].strip().upper()
            if not symbol:
                continue
            opened = datetime.fromisoformat(row["effective_from"].strip())
            if opened.tzinfo is None:
                opened = opened.replace(tzinfo=timezone.utc)
            if opened > anchor:
                continue
            names.append(symbol)
    return tuple(names)


def export_snapshot(
    repository: CoreRepository,
    directory: Path,
    *,
    as_of: datetime,
    created_at: datetime | None = None,
    symbols: tuple[str, ...] | None = None,
    timeframes: tuple[Timeframe, ...] | None = None,
) -> CandleSnapshot:
    """Write candles.jsonl and manifest.json. Rows are ordered so the hash is stable."""
    directory.mkdir(parents=True, exist_ok=True)
    names = symbols if symbols is not None else seed_symbols()
    frames = timeframes if timeframes is not None else SNAPSHOT_TIMEFRAMES
    moment = _aware(as_of)
    selected: list[Candle] = []
    for symbol in names:
        for timeframe in frames:
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
        "snapshot_id": _snapshot_id(frames, selected),
        "created_at": _aware(created_at or datetime.now(timezone.utc)).isoformat(),
        "universe": UNIVERSE,
        "timeframes": [item.value for item in frames],
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


def _snapshot_id(timeframes: tuple[Timeframe, ...], candles: list[Candle]) -> str:
    names = "_".join(item.value for item in timeframes)
    if not candles:
        return f"nifty50_{names}_empty"
    latest = max(bar.end for bar in candles).astimezone(IST)
    return f"nifty50_{names}_{latest.strftime('%Y%m%d')}"


def validate_snapshot(directory: Path, *, window_start: datetime, window_end: datetime) -> list[str]:
    """Problems in an exported folder. An empty list means the folder is ready to share."""
    folder = Path(directory)
    problems: list[str] = []
    manifest_text = (folder / "manifest.json").read_text(encoding="utf-8")
    candle_text = (folder / "candles.jsonl").read_text(encoding="utf-8")
    blob = manifest_text + candle_text
    for secret in _FORBIDDEN:
        if secret.lower() in blob.lower():
            problems.append(f"forbidden text {secret}")
    manifest = json.loads(manifest_text)
    digest = hashlib.sha256(candle_text.encode("utf-8")).hexdigest()
    if manifest.get("candle_sha256") != digest:
        problems.append("candle_sha256 does not match candles.jsonl")
    names = seed_symbols()
    listed = {item["symbol"]: item for item in manifest["symbols"]}
    if set(listed) != set(names):
        problems.append("manifest symbols are not the seed universe")
    if listed.get("TATAMOTORS", {}).get("count") != 0:
        problems.append("TATAMOTORS has candles")
    seen: set[tuple[str, str, str]] = set()
    counts: dict[str, int] = {name: 0 for name in names}
    start = _aware(window_start)
    end = _aware(window_end)
    for line in candle_text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        symbol = str(row["symbol"])
        if symbol == "TMPV" or symbol not in counts:
            problems.append(f"unexpected symbol {symbol}")
            continue
        key = (symbol, str(row["timeframe"]), str(row["start"]))
        if key in seen:
            problems.append(f"duplicate {key}")
        seen.add(key)
        counts[symbol] += 1
        bar_start = datetime.fromisoformat(str(row["start"]))
        bar_end = datetime.fromisoformat(str(row["end"]))
        if bar_start < start or bar_end > end:
            problems.append(f"{symbol} bar outside the window")
        open_ = Decimal(str(row["open"]))
        high = Decimal(str(row["high"]))
        low = Decimal(str(row["low"]))
        close = Decimal(str(row["close"]))
        if low > open_ or low > close or high < open_ or high < close or int(row["volume"]) < 0:
            problems.append(f"{symbol} OHLC is invalid")
    for symbol, entry in listed.items():
        if entry["count"] != counts[symbol]:
            problems.append(f"{symbol} count {entry['count']} != {counts[symbol]}")
    return problems


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
    parser.add_argument("--timeframe", action="append", choices=["1d", "5m"], default=None)
    args = parser.parse_args()
    frames = tuple(Timeframe(item) for item in args.timeframe) if args.timeframe else None
    repository = CoreRepository(create_schema(os.environ.get("DATABASE_URL", "sqlite:///./core.db")))
    snapshot = export_snapshot(repository, args.out, as_of=datetime.now(timezone.utc), timeframes=frames)
    print(snapshot.manifest["snapshot_id"])


if __name__ == "__main__":
    main()

"""Build NIFTY50 and INDIAVIX candles from the context snapshot at read time.

The files keep the exchange names, which contain spaces. Those names are not symbols.
Oil & Gas is not invented when it is absent.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from contracts.enums import Exchange, Timeframe
from contracts.schemas.market import Candle

_ALIASES = {"NIFTY 50": "NIFTY50", "INDIA VIX": "INDIAVIX"}


def context_root() -> Path | None:
    here = Path.cwd()
    for parent in (here, *here.parents):
        candidate = parent / "snapshots" / "context_through_20261005"
        if candidate.is_dir():
            return candidate
    return None


def load_index_bars(timeframe: Timeframe, as_of: datetime) -> dict[str, list[Candle]]:
    root = context_root()
    if root is None:
        return {}
    folder = "5m" if timeframe == Timeframe.M5 else "1D"
    path = root / folder / "candles.jsonl"
    if not path.is_file():
        return {}
    moment = as_of.astimezone(timezone.utc)
    grouped: dict[str, list[Candle]] = {"NIFTY50": [], "INDIAVIX": []}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if '"NIFTY 50"' not in line and '"INDIA VIX"' not in line:
                continue
            raw = json.loads(line)
            alias = _ALIASES.get(str(raw.get("symbol")))
            if alias is None:
                continue
            end = datetime.fromisoformat(str(raw["end"]))
            if end.astimezone(timezone.utc) > moment:
                continue
            grouped[alias].append(
                Candle(
                    symbol=alias,
                    exchange=Exchange.NSE,
                    timeframe=timeframe,
                    open=Decimal(str(raw["open"])),
                    high=Decimal(str(raw["high"])),
                    low=Decimal(str(raw["low"])),
                    close=Decimal(str(raw["close"])),
                    volume=int(raw.get("volume") or 0),
                    start=datetime.fromisoformat(str(raw["start"])),
                    end=end,
                )
            )
    return {name: bars for name, bars in grouped.items() if bars}

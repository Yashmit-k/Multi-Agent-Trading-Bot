"""Load universe_membership_seed.csv into instruments and universe_membership."""

import csv
from datetime import datetime, timezone
from pathlib import Path

from core_db.repository import CoreRepository

SEED_PATH = Path(__file__).resolve().parents[2] / "seeds" / "universe_membership_seed.csv"


def _parse_time(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def load_seed(repository: CoreRepository, path: Path = SEED_PATH) -> int:
    loaded = 0
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            instrument = repository.upsert_instrument(symbol=row["symbol"], exchange="NSE", trading_symbol=row["symbol"])
            opened = _parse_time(row["effective_from"])
            if opened is None:
                raise ValueError(f"{row['symbol']} is missing effective_from")
            repository.sync_membership(
                instrument.instrument_id,
                row["universe"].strip(),
                opened,
                _parse_time(row["effective_to"]),
            )
            loaded += 1
    return loaded

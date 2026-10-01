"""CSV loader for PAPER/SHADOW/LIVE fundamentals. Never used in BACKTEST."""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path

from contracts.schemas.fundamental import FundamentalDataPoint

from intelligence_agents.fundamentals.store import FundamentalStore


def load_csv(store: FundamentalStore, path: str | Path) -> int:
    text = Path(path).read_text(encoding="utf-8")
    return load_csv_text(store, text)


def load_csv_text(store: FundamentalStore, text: str) -> int:
    reader = csv.DictReader(StringIO(text))
    inserted = 0
    for row in reader:
        point = FundamentalDataPoint(
            symbol=row["symbol"].strip().upper(),
            metric=row["metric"].strip(),
            value=Decimal(row["value"]),
            unit=row.get("unit") or "INR",
            period=row["period"].strip(),
            announced_at=datetime.fromisoformat(row["announced_at"]),
            available_at=datetime.fromisoformat(row["available_at"]),
            source=row.get("source") or "csv",
            source_id=row["source_id"].strip(),
            metadata={"csv": True},
        )
        if store.insert(point):
            inserted += 1
    return inserted

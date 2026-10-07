"""Append-only fundamental store. Restatements are new rows."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from contracts.pit import filter_available
from contracts.schemas.fundamental import FundamentalDataPoint
from contracts.time import require_aware


class FundamentalStore(Protocol):
    def insert(self, point: FundamentalDataPoint) -> bool: ...
    def points_for(self, symbol: str, as_of: datetime) -> list[FundamentalDataPoint]: ...


def _row_to_point(row: sqlite3.Row) -> FundamentalDataPoint:
    return FundamentalDataPoint.model_validate(
        {
            "symbol": row["symbol"],
            "metric": row["metric"],
            "value": row["value"],
            "unit": row["unit"],
            "period": row["period"],
            "announced_at": row["announced_at"],
            "available_at": row["available_at"],
            "source": row["source"],
            "source_id": row["source_id"],
            "metadata": json.loads(row["metadata"]),
        }
    )


class SqliteFundamentalStore:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fundamentals (
                source_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                metric TEXT NOT NULL,
                value TEXT NOT NULL,
                unit TEXT NOT NULL,
                period TEXT NOT NULL,
                announced_at TEXT NOT NULL,
                available_at TEXT NOT NULL,
                source TEXT NOT NULL,
                metadata TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def insert(self, point: FundamentalDataPoint) -> bool:
        existing = self._conn.execute(
            "SELECT 1 FROM fundamentals WHERE source_id = ?",
            (point.source_id,),
        ).fetchone()
        if existing is not None:
            return False
        payload = point.model_dump(mode="json")
        self._conn.execute(
            """
            INSERT INTO fundamentals (
                source_id, symbol, metric, value, unit, period,
                announced_at, available_at, source, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["source_id"],
                payload["symbol"],
                payload["metric"],
                str(payload["value"]),
                payload["unit"],
                payload["period"],
                payload["announced_at"],
                payload["available_at"],
                payload["source"],
                json.dumps(payload["metadata"]),
            ),
        )
        self._conn.commit()
        return True

    def points_for(self, symbol: str, as_of: datetime) -> list[FundamentalDataPoint]:
        require_aware(as_of, "as_of")
        needle = symbol.strip().upper()
        rows = self._conn.execute(
            "SELECT * FROM fundamentals WHERE symbol = ?",
            (needle,),
        ).fetchall()
        points = [_row_to_point(row) for row in rows]
        return filter_available(points, as_of)


@dataclass
class MemoryFundamentalStore:
    _points: list[FundamentalDataPoint] = field(default_factory=list)

    def insert(self, point: FundamentalDataPoint) -> bool:
        if any(existing.source_id == point.source_id for existing in self._points):
            return False
        self._points.append(point)
        return True

    def points_for(self, symbol: str, as_of: datetime) -> list[FundamentalDataPoint]:
        needle = symbol.strip().upper()
        return filter_available(
            [point for point in self._points if point.symbol == needle],
            as_of,
        )

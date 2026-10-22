"""Point-in-time fundamentals. Visibility uses available_at, never announced_at."""

from __future__ import annotations

from datetime import datetime

from contracts.schemas.fundamental import FundamentalDataPoint
from contracts.time import require_aware

from intelligence_agents.fundamentals.store import FundamentalStore


class IntelligenceFundamentalProvider:
    def __init__(self, store: FundamentalStore) -> None:
        self._store = store

    def get_fundamentals(self, symbol: str, as_of: datetime) -> list[FundamentalDataPoint]:
        aware = require_aware(as_of, "as_of")
        return self._store.points_for(symbol, aware)


def latest_by_metric(points) -> dict:  # type: ignore[no-untyped-def]
    """The newest point per metric: latest available_at, then latest period. Never insertion order."""
    latest: dict = {}
    for point in sorted(points, key=lambda item: (item.available_at, item.period)):
        latest[point.metric] = point
    return latest

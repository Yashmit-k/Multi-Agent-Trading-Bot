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

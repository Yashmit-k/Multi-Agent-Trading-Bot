"""Historical market data for Dev 2. This module does not read Zerodha credentials."""

from __future__ import annotations

from datetime import datetime, timezone

from core_market_data.replay import HistoricalReplayMarketDataProvider
from core_market_data.snapshot import load_snapshot
from quant_agents.settings import QuantSettings


def replay_from_settings(settings: QuantSettings) -> HistoricalReplayMarketDataProvider:
    if settings.data_source != "historical":
        raise RuntimeError("historical replay requires QUANT_DATA_SOURCE=historical")
    if not settings.snapshot_path:
        raise RuntimeError("QUANT_SNAPSHOT_PATH is required for historical mode")
    snapshot = load_snapshot(settings.snapshot_path)
    ceiling = max((bar.end for bar in snapshot.candles), default=datetime.now(timezone.utc))
    return HistoricalReplayMarketDataProvider.from_snapshot(settings.snapshot_path, ceiling)

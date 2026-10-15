"""Real prices for the intelligence agents, read from Core (Zerodha candles stored by the collector).

Replaces the fixture price provider in live modes. A quote is the close of the
latest completed bar ending at or before ``as_of``: the 5-minute bar first,
falling back to the daily bar. Nothing after ``as_of`` is ever returned.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import httpx
from contracts.enums import Exchange, Timeframe
from contracts.schemas.market import Candle, Quote


class CoreMarketDataProvider:
    def __init__(self, base_url: str, token: str, *, client: httpx.Client | None = None, timeout: float = 5.0) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client = client or httpx.Client(timeout=timeout)

    def _bars(self, symbol: str, timeframe: str, as_of: datetime, last: int) -> list[Candle]:
        response = self._client.get(
            f"{self._base}/api/v1/market/candles/{symbol}",
            params={"timeframe": timeframe, "as_of": as_of.isoformat(), "last": str(last)},
            headers=self._headers,
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        bars = [Candle.model_validate(item) for item in response.json()]
        return [bar for bar in bars if bar.end <= as_of]

    def get_quote(self, symbol: str, as_of: datetime) -> Quote:
        for timeframe in (Timeframe.M5.value, Timeframe.D1.value):
            try:
                bars = self._bars(symbol, timeframe, as_of, 1)
            except httpx.HTTPError as exc:
                raise LookupError(f"core_price_unavailable:{symbol}") from exc
            if bars and Decimal(bars[-1].close) > 0:
                bar = bars[-1]
                return Quote(symbol=bar.symbol, exchange=Exchange.NSE, timestamp=bar.end, last_price=bar.close, volume=int(bar.volume))
        raise LookupError(f"no_core_price:{symbol}")

    def get_candles(self, symbol: str, timeframe: Timeframe | str, start: datetime, end: datetime) -> list[Candle]:
        value = timeframe.value if isinstance(timeframe, Timeframe) else str(timeframe)
        return [bar for bar in self._bars(symbol, value, end, 5000) if bar.start >= start]

    def get_latest_candle(self, symbol: str, timeframe: Timeframe | str) -> Candle:
        value = timeframe.value if isinstance(timeframe, Timeframe) else str(timeframe)
        bars = self._bars(symbol, value, datetime.now().astimezone(), 1)
        if not bars:
            raise LookupError(f"no_core_candle:{symbol}")
        return bars[-1]

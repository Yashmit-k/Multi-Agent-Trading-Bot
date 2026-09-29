"""Zerodha market-data adapter. Order-type names are not translated here."""

import os
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from contracts.enums import Timeframe
from contracts.schemas.market import Candle, Quote
from core_db.repository import CoreRepository


class ZerodhaUnavailable(RuntimeError):
    """Raised when broker credentials or a client are absent."""


class KiteMarketClient(Protocol):
    def instruments(self, exchange: str) -> list[dict[str, object]]:
        """Return broker instrument rows."""

    def quote(self, key: str) -> dict[str, object]:
        """Return one quote payload."""


class ZerodhaMarketDataProvider:
    """NSE instrument sync and quotes. Rate limiting is a later requirement."""

    def __init__(self, repository: CoreRepository, client: KiteMarketClient | None = None) -> None:
        self._repository = repository
        self._client = client

    @classmethod
    def from_env(cls, repository: CoreRepository) -> "ZerodhaMarketDataProvider":
        return cls(repository, client=None)

    def available(self) -> bool:
        return self._client is not None

    def credentials_present(self) -> bool:
        return bool(os.environ.get("ZERODHA_API_KEY") and os.environ.get("ZERODHA_ACCESS_TOKEN"))

    def sync_instruments(self) -> int:
        client = self._require()
        written = 0
        for row in client.instruments("NSE"):
            symbol = str(row["tradingsymbol"])
            self._repository.upsert_instrument(
                symbol=symbol,
                exchange="NSE",
                trading_symbol=symbol,
                instrument_token=int(row["instrument_token"]),
            )
            written += 1
        return written

    def get_quote(self, symbol: str, as_of: datetime) -> Quote:
        del as_of
        client = self._require()
        payload = client.quote(f"NSE:{symbol.strip().upper()}")
        return Quote(
            symbol=symbol.strip().upper(),
            exchange="NSE",
            timestamp=datetime.fromisoformat(str(payload["timestamp"])),
            last_price=Decimal(str(payload["last_price"])),
            volume=int(payload["volume"]),
        )

    def get_candles(self, symbol: str, timeframe: Timeframe | str, start: datetime, end: datetime) -> list[Candle]:
        del symbol, timeframe, start, end
        self._require()
        raise ZerodhaUnavailable("Historical candle download requires rate-limit handling and is deferred.")

    def get_latest_candle(self, symbol: str, timeframe: Timeframe | str) -> Candle:
        del symbol, timeframe
        self._require()
        raise ZerodhaUnavailable("Latest candle download requires rate-limit handling and is deferred.")

    def _require(self) -> KiteMarketClient:
        if self._client is None:
            raise ZerodhaUnavailable("Zerodha credentials are not configured")
        return self._client

"""Replay stored NSE data without returning anything after as_of."""

from datetime import datetime

from contracts.enums import Timeframe
from contracts.schemas.market import Candle, Quote
from core_db.repository import CoreRepository


class HistoricalReplayMarketDataProvider:
    def __init__(self, repository: CoreRepository, as_of: datetime) -> None:
        self._repository = repository
        self._as_of = as_of

    def get_quote(self, symbol: str, as_of: datetime) -> Quote:
        moment = min(as_of, self._as_of)
        ticks = self._repository.ticks_until(f"NSE:{symbol.strip().upper()}", moment)
        if ticks:
            last = ticks[-1]
            return Quote(
                symbol=last.symbol,
                exchange="NSE",
                timestamp=last.timestamp,
                last_price=last.price,
                volume=last.volume,
            )
        candles = self._repository.candles_until(symbol, Timeframe.D1, moment)
        if not candles:
            raise LookupError(symbol)
        bar = candles[-1]
        return Quote(symbol=bar.symbol, exchange=bar.exchange, timestamp=bar.end, last_price=bar.close, volume=bar.volume)

    def get_candles(self, symbol: str, timeframe: Timeframe | str, start: datetime, end: datetime) -> list[Candle]:
        moment = min(end, self._as_of)
        return self._repository.candles_until(symbol, timeframe, moment, start=start, end=moment)

    def get_latest_candle(self, symbol: str, timeframe: Timeframe | str) -> Candle:
        candles = self._repository.candles_until(symbol, timeframe, self._as_of)
        if not candles:
            raise LookupError(symbol)
        return candles[-1]

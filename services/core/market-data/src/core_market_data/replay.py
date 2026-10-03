"""Replay stored NSE data. A bar is knowable only when its end is at or before as_of.

Filtering on start would admit a candle that started before as_of and ended after it.
That bar is not knowable yet, so visibility uses end only.
"""

from datetime import datetime, timezone
from pathlib import Path

from contracts.enums import Timeframe
from contracts.schemas.market import Candle, Quote
from core_db.repository import CoreRepository
from core_market_data.snapshot import CandleSnapshot, load_snapshot


class HistoricalReplayMarketDataProvider:
    def __init__(self, repository: CoreRepository | None, as_of: datetime, *, candles: tuple[Candle, ...] | None = None) -> None:
        self._repository = repository
        self._as_of = _aware(as_of)
        self._candles = candles
        self.snapshot: CandleSnapshot | None = None

    @classmethod
    def from_snapshot(cls, path: str | Path, as_of: datetime) -> "HistoricalReplayMarketDataProvider":
        snapshot = load_snapshot(Path(path))
        provider = cls(None, as_of, candles=snapshot.candles)
        provider.snapshot = snapshot
        return provider

    def get_quote(self, symbol: str, as_of: datetime) -> Quote:
        moment = min(_aware(as_of), self._as_of)
        if self._repository is not None:
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
        candles = self._visible(symbol, Timeframe.D1, datetime.min.replace(tzinfo=timezone.utc), moment)
        if not candles:
            raise LookupError(symbol)
        bar = candles[-1]
        return Quote(symbol=bar.symbol, exchange=bar.exchange, timestamp=bar.end, last_price=bar.close, volume=bar.volume)

    def get_candles(self, symbol: str, timeframe: Timeframe | str, start: datetime, end: datetime) -> list[Candle]:
        """Bars whose end is inside (start, min(end, as_of)]. start is not a visibility test."""
        moment = min(_aware(end), self._as_of)
        return self._visible(symbol, timeframe, _aware(start), moment)

    def get_latest_candle(self, symbol: str, timeframe: Timeframe | str) -> Candle:
        candles = self._visible(symbol, timeframe, datetime.min.replace(tzinfo=timezone.utc), self._as_of)
        if not candles:
            raise LookupError(symbol)
        return candles[-1]

    def _visible(self, symbol: str, timeframe: Timeframe | str, start: datetime, moment: datetime) -> list[Candle]:
        parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
        name = symbol.strip().upper()
        if self._candles is not None:
            pool = self._candles
        elif self._repository is not None:
            pool = self._repository.candles_until(name, parsed, moment)
        else:
            pool = ()
        visible = [
            bar
            for bar in pool
            if bar.symbol == name and bar.timeframe == parsed and start < bar.end <= moment
        ]
        visible.sort(key=lambda bar: bar.end)
        return visible


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)

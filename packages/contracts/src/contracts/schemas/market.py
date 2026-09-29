"""Market data shapes returned by MarketDataProvider."""

from typing import Self

from pydantic import AwareDatetime, model_validator

from contracts.enums import Exchange, Timeframe
from contracts.schemas.common import ContractModel, NonNegativeInt, PositiveDecimal, Symbol


class Quote(ContractModel):
    """Last traded price visible at timestamp."""

    symbol: Symbol
    exchange: Exchange
    timestamp: AwareDatetime
    last_price: PositiveDecimal
    volume: NonNegativeInt


class Candle(ContractModel):
    """One OHLCV bar. end is the time the bar became knowable."""

    symbol: Symbol
    exchange: Exchange
    timeframe: Timeframe
    open: PositiveDecimal
    high: PositiveDecimal
    low: PositiveDecimal
    close: PositiveDecimal
    volume: NonNegativeInt
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def _ohlc(self) -> Self:
        if self.end <= self.start:
            raise ValueError("candle end must be after start")
        if self.high < self.low:
            raise ValueError("high cannot be below low")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("open and close must sit inside the high-low range")
        return self

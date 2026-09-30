"""Wrap providers and record (provider, method, symbol, requested_time)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from contracts.enums import Timeframe
from contracts.interfaces import AgentContext
from contracts.schemas.feature_set import FeatureSet
from contracts.schemas.fundamental import FundamentalDataPoint
from contracts.schemas.market import Candle, Quote
from contracts.schemas.news_article import NewsArticle
from contracts.schemas.portfolio import PortfolioSnapshot


@dataclass(frozen=True, slots=True)
class ProviderCall:
    provider: str
    method: str
    symbol: str
    requested_time: datetime


class RecordingProvider:
    def __init__(self, inner: Any, name: str, calls: list[ProviderCall]) -> None:
        self._inner = inner
        self._name = name
        self._calls = calls

    def get_feature_set(self, symbol: str, timeframe: Timeframe | str, as_of: datetime) -> FeatureSet:
        self._calls.append(ProviderCall(self._name, "get_feature_set", symbol, as_of))
        return self._inner.get_feature_set(symbol, timeframe, as_of)

    def get_quote(self, symbol: str, as_of: datetime) -> Quote:
        self._calls.append(ProviderCall(self._name, "get_quote", symbol, as_of))
        return self._inner.get_quote(symbol, as_of)

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe | str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        self._calls.append(ProviderCall(self._name, "get_candles", symbol, end))
        return self._inner.get_candles(symbol, timeframe, start, end)

    def get_latest_candle(self, symbol: str, timeframe: Timeframe | str) -> Candle:
        self._calls.append(ProviderCall(self._name, "get_latest_candle", symbol, datetime.min))
        return self._inner.get_latest_candle(symbol, timeframe)

    def get_articles(self, symbol: str, as_of: datetime) -> list[NewsArticle]:
        self._calls.append(ProviderCall(self._name, "get_articles", symbol, as_of))
        return self._inner.get_articles(symbol, as_of)

    def get_fundamentals(self, symbol: str, as_of: datetime) -> list[FundamentalDataPoint]:
        self._calls.append(ProviderCall(self._name, "get_fundamentals", symbol, as_of))
        return self._inner.get_fundamentals(symbol, as_of)


class ForbiddenMarketData:
    def get_quote(self, symbol: str, as_of: datetime) -> Quote:
        raise AssertionError("quant agents must not call market_data_provider")

    def get_candles(self, symbol: str, timeframe: Timeframe | str, start: datetime, end: datetime) -> list[Candle]:
        raise AssertionError("quant agents must not call market_data_provider")

    def get_latest_candle(self, symbol: str, timeframe: Timeframe | str) -> Candle:
        raise AssertionError("quant agents must not call market_data_provider")


def AuditingContext(
    *,
    feature_provider: Any,
    news_provider: Any,
    fundamental_provider: Any,
    configuration: dict[str, Any],
    market_data_provider: Any | None = None,
    current_portfolio_snapshot: PortfolioSnapshot | None = None,
    calls: list[ProviderCall] | None = None,
) -> tuple[AgentContext, list[ProviderCall]]:
    bucket = calls if calls is not None else []
    market = market_data_provider if market_data_provider is not None else ForbiddenMarketData()
    context = AgentContext(
        market_data_provider=RecordingProvider(market, "market", bucket),
        feature_provider=RecordingProvider(feature_provider, "feature", bucket),
        news_provider=RecordingProvider(news_provider, "news", bucket),
        fundamental_provider=RecordingProvider(fundamental_provider, "fundamental", bucket),
        configuration=configuration,
        current_portfolio_snapshot=current_portfolio_snapshot,
    )
    return context, bucket

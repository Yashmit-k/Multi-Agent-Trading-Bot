"""Guard providers so BACKTEST fails closed on future-dated rows."""

from __future__ import annotations

from datetime import datetime

from contracts.enums import Timeframe, TradingMode
from contracts.schemas.feature_set import FeatureSet
from contracts.schemas.fundamental import FundamentalDataPoint
from contracts.schemas.market import Candle, Quote
from contracts.schemas.news_article import NewsArticle
from contracts.time import require_aware

from intelligence_agents.errors import LeakageError


class LeakageGuard:
    def __init__(self, inner: object, mode: TradingMode) -> None:
        self._inner = inner
        self._mode = mode

    def get_articles(self, symbol: str, as_of: datetime) -> list[NewsArticle]:
        aware = require_aware(as_of, "as_of")
        articles = self._inner.get_articles(symbol, aware)  # type: ignore[attr-defined]
        if self._mode is TradingMode.BACKTEST:
            for article in articles:
                if article.published_at > aware or article.retrieved_at > aware:
                    raise LeakageError("news published_at/retrieved_at after as_of")
        return articles

    def get_fundamentals(self, symbol: str, as_of: datetime) -> list[FundamentalDataPoint]:
        aware = require_aware(as_of, "as_of")
        points = self._inner.get_fundamentals(symbol, aware)  # type: ignore[attr-defined]
        if self._mode is TradingMode.BACKTEST:
            for point in points:
                if point.available_at > aware:
                    raise LeakageError("fundamental available_at after as_of")
        return points

    def get_quote(self, symbol: str, as_of: datetime) -> Quote:
        aware = require_aware(as_of, "as_of")
        quote = self._inner.get_quote(symbol, aware)  # type: ignore[attr-defined]
        if self._mode is TradingMode.BACKTEST and quote.timestamp > aware:
            raise LeakageError("quote.timestamp after as_of")
        return quote

    def get_candles(self, symbol: str, timeframe: Timeframe | str, start: datetime, end: datetime) -> list[Candle]:
        return self._inner.get_candles(symbol, timeframe, start, end)  # type: ignore[attr-defined]

    def get_latest_candle(self, symbol: str, timeframe: Timeframe | str) -> Candle:
        return self._inner.get_latest_candle(symbol, timeframe)  # type: ignore[attr-defined]

    def get_feature_set(self, symbol: str, timeframe: Timeframe | str, as_of: datetime) -> FeatureSet:
        return self._inner.get_feature_set(symbol, timeframe, as_of)  # type: ignore[attr-defined]

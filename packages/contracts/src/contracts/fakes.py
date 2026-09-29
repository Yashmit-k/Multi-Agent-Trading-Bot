"""Deterministic stand-ins for Dev 1 and Dev 2.

These classes implement the provider protocols with the fixture dataset.
They do not call a broker, a database, or another agent.
"""

from datetime import datetime

from contracts.enums import Timeframe
from contracts.fixtures import (
    articles_for,
    candles_between,
    feature_set_for,
    fundamentals_for,
    latest_candle,
    quote_for,
)
from contracts.schemas.agent_signal import AgentSignal
from contracts.schemas.feature_set import FeatureSet
from contracts.schemas.fundamental import FundamentalDataPoint
from contracts.schemas.market import Candle, Quote
from contracts.schemas.news_article import NewsArticle
from contracts.schemas.submission import SubmissionResult


class FakeMarketDataProvider:
    """In-memory NSE daily bars. The same inputs always return the same bars."""

    def get_quote(self, symbol: str, as_of: datetime) -> Quote:
        return quote_for(symbol, as_of)

    def get_candles(self, symbol: str, timeframe: Timeframe | str, start: datetime, end: datetime) -> list[Candle]:
        return candles_between(symbol, timeframe, start, end)

    def get_latest_candle(self, symbol: str, timeframe: Timeframe | str) -> Candle:
        return latest_candle(symbol, timeframe)


class FakeFeatureProvider:
    """Serves FeatureSet values. Callers must not recompute indicators themselves."""

    def get_feature_set(self, symbol: str, timeframe: Timeframe | str, as_of: datetime) -> FeatureSet:
        return feature_set_for(symbol, timeframe, as_of)


class FakeNewsProvider:
    """Returns articles that were published and retrieved at or before as_of."""

    def get_articles(self, symbol: str, as_of: datetime) -> list[NewsArticle]:
        return articles_for(symbol, as_of)


class FakeFundamentalProvider:
    """Returns fundamental rows with available_at <= as_of."""

    def get_fundamentals(self, symbol: str, as_of: datetime) -> list[FundamentalDataPoint]:
        return fundamentals_for(symbol, as_of)


class FakeSignalSink:
    """Records signals in memory and rejects a repeated signal_id."""

    def __init__(self) -> None:
        self.submitted: list[AgentSignal] = []

    def submit(self, signal: AgentSignal) -> SubmissionResult:
        if any(existing.signal_id == signal.signal_id for existing in self.submitted):
            return SubmissionResult(
                accepted=False,
                signal_id=signal.signal_id,
                duplicate=True,
                message="duplicate signal_id",
            )
        self.submitted.append(signal)
        return SubmissionResult(
            accepted=True,
            signal_id=signal.signal_id,
            duplicate=False,
            message="accepted",
        )

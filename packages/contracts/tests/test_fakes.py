"""Deterministic fake providers."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from contracts.enums import Timeframe
from contracts.fakes import (
    FakeFeatureProvider,
    FakeFundamentalProvider,
    FakeMarketDataProvider,
    FakeNewsProvider,
    FakeSignalSink,
)
from contracts.fixtures import FIXTURE_AS_OF, FIXTURE_SYMBOLS, sample_agent_signal
from contracts.interfaces import (
    AgentContext,
    FeatureProvider,
    FundamentalProvider,
    MarketDataProvider,
    NewsProvider,
    SignalSink,
)


def test_fake_market_data_is_deterministic() -> None:
    left = FakeMarketDataProvider()
    right = FakeMarketDataProvider()
    start = datetime(2024, 5, 1, tzinfo=timezone.utc)
    end = FIXTURE_AS_OF
    assert left.get_quote("RELIANCE", FIXTURE_AS_OF).last_price == Decimal("2927.00")
    assert left.get_quote("RELIANCE", FIXTURE_AS_OF).volume == 104000
    assert left.get_quote("RELIANCE", FIXTURE_AS_OF).timestamp == FIXTURE_AS_OF
    for symbol in FIXTURE_SYMBOLS:
        assert left.get_quote(symbol, FIXTURE_AS_OF) == right.get_quote(symbol, FIXTURE_AS_OF)
        assert left.get_candles(symbol, Timeframe.D1, start, end) == right.get_candles(
            symbol, "1d", start, end
        )
        assert left.get_latest_candle(symbol, Timeframe.D1) == right.get_latest_candle(symbol, Timeframe.D1)


def test_quote_hides_the_bar_until_it_closes() -> None:
    provider = FakeMarketDataProvider()
    before_close = FIXTURE_AS_OF - timedelta(minutes=1)
    earlier = provider.get_quote("TCS", before_close)
    closed = provider.get_quote("TCS", FIXTURE_AS_OF)
    assert earlier.timestamp == datetime(2024, 5, 31, 10, 0, tzinfo=timezone.utc)
    assert closed.timestamp == FIXTURE_AS_OF
    assert earlier.last_price != closed.last_price


def test_feature_news_and_signal_sink_are_deterministic() -> None:
    features = FakeFeatureProvider()
    news = FakeNewsProvider()
    first = features.get_feature_set("ICICIBANK", Timeframe.D1, FIXTURE_AS_OF)
    second = features.get_feature_set("ICICIBANK", Timeframe.D1, FIXTURE_AS_OF)
    assert first == second
    assert news.get_articles("HDFCBANK", FIXTURE_AS_OF) == news.get_articles("HDFCBANK", FIXTURE_AS_OF)
    assert len(news.get_articles("HDFCBANK", FIXTURE_AS_OF)) == 1
    sink = FakeSignalSink()
    signal = sample_agent_signal("INFY")
    accepted = sink.submit(signal)
    duplicate = sink.submit(signal)
    assert accepted.accepted and not accepted.duplicate
    assert duplicate.duplicate and not duplicate.accepted


def test_fakes_match_provider_protocols() -> None:
    assert isinstance(FakeMarketDataProvider(), MarketDataProvider)
    assert isinstance(FakeFeatureProvider(), FeatureProvider)
    assert isinstance(FakeNewsProvider(), NewsProvider)
    assert isinstance(FakeFundamentalProvider(), FundamentalProvider)
    assert isinstance(FakeSignalSink(), SignalSink)


def test_agent_context_rejects_execution_credentials() -> None:
    with pytest.raises(ValueError, match="execution credentials"):
        AgentContext(
            market_data_provider=FakeMarketDataProvider(),
            feature_provider=FakeFeatureProvider(),
            news_provider=FakeNewsProvider(),
            fundamental_provider=FakeFundamentalProvider(),
            configuration={"api_key": "secret"},
        )

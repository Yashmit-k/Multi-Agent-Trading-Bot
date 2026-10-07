"""Shared test constructors. Imported by unit tests only."""

from datetime import datetime

from contracts.fakes import FakeFeatureProvider, FakeMarketDataProvider
from contracts.fixtures import FIXTURE_AS_OF
from contracts.interfaces import AgentContext

from intelligence_agents.clock import ReplayClock
from intelligence_agents.fundamentals.provider import IntelligenceFundamentalProvider
from intelligence_agents.fundamentals.store import MemoryFundamentalStore
from intelligence_agents.news.fixtures import load_fundamental_fixtures, load_news_fixtures
from intelligence_agents.news.provider import IntelligenceNewsProvider
from intelligence_agents.news.store import MemoryNewsStore


def make_stores(now: datetime | None = None):
    news = MemoryNewsStore()
    funds = MemoryFundamentalStore()
    load_news_fixtures(news, now=now or FIXTURE_AS_OF)
    load_fundamental_fixtures(funds)
    return news, funds


def make_context(news, funds, extra=None) -> AgentContext:
    config = {"horizon": "SWING"}
    if extra:
        config.update(extra)
    return AgentContext(
        market_data_provider=FakeMarketDataProvider(),
        feature_provider=FakeFeatureProvider(),
        news_provider=IntelligenceNewsProvider(news),
        fundamental_provider=IntelligenceFundamentalProvider(funds),
        configuration=config,
    )


CLOCK = ReplayClock(FIXTURE_AS_OF)

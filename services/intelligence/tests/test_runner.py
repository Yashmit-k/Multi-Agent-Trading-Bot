from datetime import datetime, timezone

import pytest
from contracts.enums import TradingMode
from contracts.fakes import FakeFeatureProvider, FakeMarketDataProvider, FakeSignalSink
from contracts.fixtures import FIXTURE_AS_OF
from contracts.interfaces import AgentContext
from contracts.schemas.news_article import NewsArticle
from contracts.fixtures import content_hash

from intelligence_agents.agents.news import NewsAgent
from intelligence_agents.clock import ReplayClock
from intelligence_agents.errors import ConfigError, LeakageError
from intelligence_agents.llm.cost import CostTracker
from intelligence_agents.llm.fixture import FixtureLLMProvider
from intelligence_agents.llm.router import LLMRouter
from intelligence_agents.runner import Runner
from intelligence_agents.settings import IntelligenceSettings
from intelligence_agents.fundamentals.provider import IntelligenceFundamentalProvider
from intelligence_agents.fundamentals.store import MemoryFundamentalStore

from intelligence_agents.testing import make_context, make_stores


class LeakingNews:
    def get_articles(self, symbol: str, as_of: datetime) -> list[NewsArticle]:
        future = datetime(2025, 1, 1, tzinfo=timezone.utc)
        return [
            NewsArticle(
                article_id="leak",
                source="wire",
                title="leak",
                url="https://example.test/leak",
                published_at=future,
                retrieved_at=future,
                content_hash=content_hash("leak"),
                symbols=[symbol],
                raw_text="leak",
                metadata={},
            )
        ]


def test_backtest_hard_stop_on_leakage():
    news, funds = make_stores()
    funds_provider = IntelligenceFundamentalProvider(funds)
    router = LLMRouter(FixtureLLMProvider(), None, CostTracker(0), tier2_enabled=False)
    agent = NewsAgent(ReplayClock(FIXTURE_AS_OF), router)
    sink = FakeSignalSink()

    def factory(symbol, as_of, horizon):
        return AgentContext(
            market_data_provider=FakeMarketDataProvider(),
            feature_provider=FakeFeatureProvider(),
            news_provider=LeakingNews(),
            fundamental_provider=funds_provider,
            configuration={"horizon": horizon.value},
        )

    runner = Runner([agent], sink, ReplayClock(FIXTURE_AS_OF), factory, TradingMode.BACKTEST)
    with pytest.raises(LeakageError):
        runner.run(["RELIANCE"], FIXTURE_AS_OF)


def test_backtest_plus_rss_refused(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "BACKTEST")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "rss")
    monkeypatch.setenv("NEWS_RSS_URLS", "https://example.test/rss")
    with pytest.raises(ConfigError):
        IntelligenceSettings.from_env()


def test_runner_submits_fixture_signals():
    news, funds = make_stores()
    router = LLMRouter(FixtureLLMProvider(), None, CostTracker(0), tier2_enabled=False)
    agent = NewsAgent(ReplayClock(FIXTURE_AS_OF), router)
    sink = FakeSignalSink()

    def factory(symbol, as_of, horizon):
        return make_context(news, funds, {"horizon": horizon.value})

    runner = Runner([agent], sink, ReplayClock(FIXTURE_AS_OF), factory, TradingMode.BACKTEST)
    produced = runner.run(["RELIANCE"], FIXTURE_AS_OF)
    assert produced
    assert sink.submitted

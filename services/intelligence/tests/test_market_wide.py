"""Market-wide headlines stay out of stock News scores unless the capture switch is on."""

from datetime import datetime, timezone

from contracts.fixtures import FIXTURE_AS_OF, content_hash
from contracts.schemas.news_article import NewsArticle

from intelligence_agents.agents.news import NewsAgent
from intelligence_agents.clock import ReplayClock
from intelligence_agents.llm.cost import CostTracker
from intelligence_agents.llm.fixture import FixtureLLMProvider
from intelligence_agents.llm.router import LLMRouter
from intelligence_agents.news.market_wide import categorise
from intelligence_agents.news.rss import RssPuller
from intelligence_agents.news.store import MemoryNewsStore
from intelligence_agents.testing import CLOCK, make_context, make_stores

FEED = """<?xml version="1.0"?>
<rss><channel>
<item>
  <title>{title}</title>
  <link>https://example.test/mw</link>
  <guid>https://example.test/mw</guid>
  <pubDate>Mon, 03 Jun 2024 04:00:00 GMT</pubDate>
  <description>{title}</description>
</item>
</channel></rss>
"""


def test_keyword_categories_on_real_looking_headlines() -> None:
    assert categorise("Israel strikes Iran") == "geopolitics_war"
    assert categorise("RBI holds repo rate") == "central_banks"
    assert categorise("Brent crude jumps 6%") == "crude_commodities"
    assert categorise("US announces new tariffs on China") == "trade_wars"
    assert categorise("new tariffs after the war") == "trade_wars"
    assert categorise("Local bakery opens a new branch") == "unclassified"


def test_switch_off_still_drops_a_headline_with_no_company() -> None:
    store = MemoryNewsStore()
    clock = ReplayClock(datetime(2024, 6, 3, 10, tzinfo=timezone.utc))
    puller = RssPuller(store, clock, ("RELIANCE",), interval_seconds=0, keep_market_wide=False)
    body = FEED.format(title="Israel strikes Iran").encode()
    inserted = puller.ingest_bytes(body, feed_url="https://example.test/rss", retrieved_at=clock.now())
    assert inserted == 0
    assert store.dropped_empty_symbols == 1
    assert store.articles_for("NIFTY50", clock.now()) == []


def test_switch_on_stores_nifty50_and_a_category() -> None:
    store = MemoryNewsStore()
    clock = ReplayClock(datetime(2024, 6, 3, 10, tzinfo=timezone.utc))
    puller = RssPuller(store, clock, ("RELIANCE",), interval_seconds=0, keep_market_wide=True)
    body = FEED.format(title="RBI holds repo rate").encode()
    assert puller.ingest_bytes(body, feed_url="https://example.test/rss", retrieved_at=clock.now()) == 1
    article = store.articles_for("NIFTY50", clock.now())[0]
    assert article.symbols == ["NIFTY50"]
    assert article.metadata["category"] == "central_banks"
    assert article.metadata["market_wide"] is True


def _router() -> LLMRouter:
    return LLMRouter(FixtureLLMProvider(), None, CostTracker(0), tier2_enabled=False)


def test_nifty50_article_does_not_change_a_stock_news_signal() -> None:
    news, funds = make_stores()
    agent = NewsAgent(CLOCK, _router())
    before = agent.evaluate("RELIANCE", FIXTURE_AS_OF, make_context(news, funds))
    article = NewsArticle(
        article_id="idx-1",
        source="wire",
        title="Israel strikes Iran",
        url="https://example.test/idx",
        published_at=FIXTURE_AS_OF,
        retrieved_at=FIXTURE_AS_OF,
        content_hash=content_hash("Israel strikes Iran"),
        symbols=["NIFTY50"],
        raw_text="Israel strikes Iran",
        metadata={"category": "geopolitics_war", "market_wide": True},
    )
    news.insert(article, now=FIXTURE_AS_OF)
    after = agent.evaluate("RELIANCE", FIXTURE_AS_OF, make_context(news, funds))
    assert after.signal_id == before.signal_id
    assert after.signal == before.signal
    empty = NewsAgent(CLOCK, _router()).evaluate("RELIANCE", FIXTURE_AS_OF, make_context(MemoryNewsStore(), funds))
    only_index = MemoryNewsStore()
    only_index.insert(article, now=FIXTURE_AS_OF)
    untouched = NewsAgent(CLOCK, _router()).evaluate("RELIANCE", FIXTURE_AS_OF, make_context(only_index, funds))
    assert untouched.signal_id == empty.signal_id
    assert "insufficient_data" in untouched.reason_codes

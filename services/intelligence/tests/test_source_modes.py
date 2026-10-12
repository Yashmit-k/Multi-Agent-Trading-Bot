from datetime import datetime, timezone

import httpx

from contracts.enums import TradingMode
from contracts.fixtures import FIXTURE_AS_OF
from intelligence_agents.agents.fundamental import FundamentalAgent
from intelligence_agents.agents.news import NewsAgent
from intelligence_agents.clock import ReplayClock
from intelligence_agents.errors import ConfigError
from intelligence_agents.fundamentals.csv_loader import load_csv_text
from intelligence_agents.fundamentals.store import MemoryFundamentalStore
from intelligence_agents.loop import refresh_sources
from intelligence_agents.news.rss import RssPuller
from intelligence_agents.news.store import MemoryNewsStore
from intelligence_agents.settings import IntelligenceSettings
from intelligence_agents.testing import make_context

from test_agents import _router

_RSS = b"""<?xml version="1.0"?>
<rss><channel><item>
<title>RELIANCE profit growth</title>
<link>https://example.test/reliance-note</link>
<description>steady profit growth</description>
<pubDate>Mon, 03 Jun 2024 04:00:00 GMT</pubDate>
</item></channel></rss>"""

_CSV = """symbol,metric,value,unit,period,announced_at,available_at,source,source_id
RELIANCE,eps,20,INR,FY2024,2024-04-20T10:00:00+00:00,2024-04-20T12:00:00+00:00,csv,rel-eps-1
RELIANCE,eps,nope,INR,FY2024,2024-04-20T10:00:00+00:00,2024-04-20T12:00:00+00:00,csv,rel-eps-bad
"""


def _paper_settings(monkeypatch, **env: str) -> IntelligenceSettings:
    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "PAPER")
    monkeypatch.setenv("INTELLIGENCE_SERVICE_MODE", "oneshot")
    monkeypatch.setenv("CORE_API_URL", "http://core-api:8000")
    monkeypatch.setenv("INTERNAL_SIGNAL_TOKEN", "write")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return IntelligenceSettings.from_env()


def test_fixture_mode_does_not_call_loaders(monkeypatch) -> None:
    monkeypatch.delenv("INTELLIGENCE_DATA_SOURCE", raising=False)

    def _boom(*_args, **_kwargs):
        raise AssertionError("loader called")

    monkeypatch.setattr("intelligence_agents.news.rss.RssPuller.pull", _boom)
    monkeypatch.setattr("intelligence_agents.fundamentals.csv_loader.load_csv", _boom)
    settings = IntelligenceSettings.from_env()
    assert settings.data_source == "fixtures"
    refresh_sources(settings, None, None)


def test_rss_item_reaches_the_news_agent() -> None:
    store = MemoryNewsStore()
    clock = ReplayClock(FIXTURE_AS_OF)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_RSS)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    puller = RssPuller(
        store,
        clock,
        ("RELIANCE",),
        interval_seconds=300,
        client=client,
        sleeper=lambda _delay: None,
    )
    assert puller.pull("https://example.test/feed") == 1
    signal = NewsAgent(clock, _router()).evaluate("RELIANCE", FIXTURE_AS_OF, make_context(store, MemoryFundamentalStore()))
    assert signal.features["article_count"] == 1
    assert puller.pull("https://example.test/feed") == 0
    again = NewsAgent(clock, _router()).evaluate("RELIANCE", FIXTURE_AS_OF, make_context(store, MemoryFundamentalStore()))
    assert again.signal_id == signal.signal_id


def test_rss_http_failure_is_contained() -> None:
    store = MemoryNewsStore()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    puller = RssPuller(
        store,
        ReplayClock(FIXTURE_AS_OF),
        ("RELIANCE",),
        retries=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=lambda _delay: None,
    )

    class _Runner:
        news_store = store

    settings = IntelligenceSettings(
        data_source="rss",
        trading_mode=TradingMode.PAPER,
        store="memory",
        sqlite_path="unused.db",
        log_level="INFO",
        symbols=("RELIANCE",),
        eval_interval_seconds=300,
        core_api_url="http://core-api:8000",
        internal_signal_token="write",
        llm_base_url="",
        llm_api_key="",
        llm_tier1_model="fixture",
        llm_tier2_model="fixture",
        llm_daily_budget_usd=0,
        llm_timeout_seconds=1,
        news_rss_urls=("https://example.test/feed",),
        tier2_enabled=False,
        rss_interval_seconds=300,
        rss_max_bytes=1024,
        rss_max_items=10,
        service_mode="oneshot",
    )
    refresh_sources(settings, _Runner(), puller)
    assert store.articles_for("RELIANCE", FIXTURE_AS_OF) == []


def test_csv_row_reaches_the_fundamental_agent() -> None:
    store = MemoryFundamentalStore()
    assert load_csv_text(store, _CSV) == 1
    assert load_csv_text(store, _CSV) == 0
    signal = FundamentalAgent(ReplayClock(FIXTURE_AS_OF), _router()).evaluate(
        "RELIANCE",
        FIXTURE_AS_OF,
        make_context(MemoryNewsStore(), store),
    )
    assert signal.features["metric_eps"] == "20"
    assert len(store.points_for("RELIANCE", datetime(2024, 8, 1, tzinfo=timezone.utc))) == 1


def test_csv_live_requires_a_path(monkeypatch) -> None:
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "csv-live")
    monkeypatch.delenv("INTELLIGENCE_FUNDAMENTALS_CSV", raising=False)
    try:
        _paper_settings(monkeypatch)
    except ConfigError as exc:
        assert "INTELLIGENCE_FUNDAMENTALS_CSV" in str(exc)
    else:
        raise AssertionError("csv-live without a path was accepted")


def test_backtest_still_rejects_csv_live(monkeypatch) -> None:
    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "BACKTEST")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "csv-live")
    monkeypatch.setenv("INTELLIGENCE_FUNDAMENTALS_CSV", "funds.csv")
    try:
        IntelligenceSettings.from_env()
    except ConfigError as exc:
        assert "BACKTEST" in str(exc)
    else:
        raise AssertionError("BACKTEST csv-live was accepted")

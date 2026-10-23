from datetime import datetime, timezone

import httpx

from intelligence_agents.news.ingest import NewsIngestHealth, apply_poll_stats, feeds_for_poll, run_poll
from intelligence_agents.news.interpret import interpret_text, interpretation_unavailable
from intelligence_agents.news.rss import IngestStats
from intelligence_agents.news.universe import NIFTY50_SYMBOLS, match_symbols
from intelligence_agents.settings import IntelligenceSettings


def test_sbi_life_does_not_map_to_sbin():
    universe = {"SBIN", "SBILIFE"}
    symbols, evidence = match_symbols("SBI Life launches a product", universe)
    assert symbols == ["SBILIFE"]
    assert "SBIN" not in evidence


def test_nifty_alias_and_hyphen_ticker():
    universe = {"BAJAJ-AUTO", "HDFCBANK", "RELIANCE"}
    symbols, evidence = match_symbols("Bajaj Auto and HDFC Bank rally", universe)
    assert symbols == ["BAJAJ-AUTO", "HDFCBANK"]
    assert evidence["BAJAJ-AUTO"].startswith("alias:")
    assert evidence["HDFCBANK"].startswith("alias:")


def test_rss_defaults_to_market_feeds_and_nifty(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "PAPER")
    monkeypatch.setenv("INTELLIGENCE_SERVICE_MODE", "oneshot")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "rss")
    monkeypatch.delenv("INTELLIGENCE_SYMBOLS", raising=False)
    monkeypatch.delenv("NEWS_RSS_URLS", raising=False)
    monkeypatch.delenv("INTERNAL_SIGNAL_TOKEN", raising=False)
    monkeypatch.delenv("INTELLIGENCE_NEWS_INGEST", raising=False)
    settings = IntelligenceSettings.from_env()
    assert settings.news_ingest is False  # opt-in: rss alone never starts the separate ingest loop
    assert settings.news_rss_urls
    assert settings.symbols == NIFTY50_SYMBOLS
    assert settings.rss_interval_seconds >= 30


def test_news_ingest_requires_rss(monkeypatch):
    from intelligence_agents.errors import ConfigError

    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "fixtures")
    monkeypatch.setenv("INTELLIGENCE_NEWS_INGEST", "true")
    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "BACKTEST")
    try:
        IntelligenceSettings.from_env()
        raised = False
    except ConfigError:
        raised = True
    assert raised


def test_symbol_batch_round_robin(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "PAPER")
    monkeypatch.setenv("INTELLIGENCE_SERVICE_MODE", "oneshot")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "rss")
    monkeypatch.setenv("INTELLIGENCE_SYMBOLS", "RELIANCE,TCS,INFY")
    monkeypatch.setenv("NEWS_RSS_SYMBOL_BATCH", "2")
    settings = IntelligenceSettings.from_env()
    first, cursor = feeds_for_poll(settings, 0)
    second, _cursor = feeds_for_poll(settings, cursor)
    assert any("Reliance" in url or "RELIANCE" in url for url in first)
    assert any("TCS" in url or "Tata+Consultancy" in url or "Tata Consultancy" in url for url in first)
    assert any("INFY" in url or "Infosys" in url for url in second)


def test_apply_poll_stats_failure_visible():
    health = NewsIngestHealth(interval_seconds=300)
    now = datetime(2024, 6, 3, 10, tzinfo=timezone.utc)
    apply_poll_stats(
        health,
        [IngestStats(fetch_failed=True, error="http_500:example.test")],
        now=now,
        latest_published=None,
    )
    assert health.polls == 1
    assert health.consecutive_failures == 1
    assert health.last_error == "http_500:example.test"
    assert health.last_successful_poll is None


def test_interpretation_unavailable_without_llm(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "PAPER")
    monkeypatch.setenv("INTELLIGENCE_SERVICE_MODE", "oneshot")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "rss")
    monkeypatch.setenv("INTELLIGENCE_NEWS_INTERPRET", "true")
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    settings = IntelligenceSettings.from_env()
    result = interpret_text(title="t", raw_text="r", url="https://example.test/", settings=settings)
    assert result["available"] is False
    assert result["model_generated"] is False
    assert interpretation_unavailable("x")["available"] is False


def test_oneshot_paper_starts_without_sink(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "PAPER")
    monkeypatch.setenv("INTELLIGENCE_SERVICE_MODE", "oneshot")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "rss")
    monkeypatch.setenv("INTELLIGENCE_NEWS_INGEST", "false")
    monkeypatch.setenv("INTELLIGENCE_STORE", "memory")
    monkeypatch.delenv("INTERNAL_SIGNAL_TOKEN", raising=False)
    from intelligence_agents.service import _require_live_sink

    settings = IntelligenceSettings.from_env()
    assert settings.news_ingest is False
    assert _require_live_sink(settings, None) is None


def test_news_limit_and_symbol_coverage():
    from contracts.fixtures import all_articles
    from intelligence_agents.news.store import MemoryNewsStore
    from intelligence_agents.service import _news_limit, _symbol_coverage

    assert _news_limit(None) == 100
    assert _news_limit(3) == 3
    store = MemoryNewsStore()
    for article in all_articles("RELIANCE"):
        store.insert(article, now=datetime(2024, 6, 3, 10, tzinfo=timezone.utc))
    coverage = _symbol_coverage(store, ("RELIANCE", "TATAMOTORS"))
    assert "RELIANCE" in coverage["symbols_with_articles"]
    assert "TATAMOTORS" in coverage["symbols_without_articles"]


def test_run_poll_graduates_quarantine(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "PAPER")
    monkeypatch.setenv("INTELLIGENCE_SERVICE_MODE", "oneshot")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "rss")
    monkeypatch.setenv("INTELLIGENCE_SYMBOLS", "RELIANCE")
    monkeypatch.setenv("INTELLIGENCE_NEWS_INGEST", "false")
    settings = IntelligenceSettings.from_env()
    graduated: list[datetime] = []

    class FakePuller:
        def pull_stats(self, url):
            return IngestStats(inserted=0)

    run_poll(
        settings,
        FakePuller(),
        NewsIngestHealth(interval_seconds=300),
        now=datetime(2024, 6, 3, 10, tzinfo=timezone.utc),
        latest_published_fn=lambda: None,
        graduate_fn=lambda now: graduated.append(now) or 0,
    )
    assert graduated


def test_interpret_success_and_failures(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "PAPER")
    monkeypatch.setenv("INTELLIGENCE_SERVICE_MODE", "oneshot")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "rss")
    monkeypatch.setenv("INTELLIGENCE_NEWS_INTERPRET", "true")
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    settings = IntelligenceSettings.from_env()

    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"summary":"Co filed results","company":"TCS","event_category":"earnings","relevance":"high"}'
                        }
                    }
                ]
            },
        )

    good = interpret_text(
        title="t",
        raw_text="r",
        url="https://example.test/a",
        settings=settings,
        client=httpx.Client(transport=httpx.MockTransport(ok)),
    )
    assert good["available"] is True
    assert good["model_generated"] is True
    assert good["original_url"] == "https://example.test/a"

    def bad_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})

    malformed = interpret_text(
        title="t",
        raw_text="r",
        url="https://example.test/a",
        settings=settings,
        client=httpx.Client(transport=httpx.MockTransport(bad_json)),
    )
    assert malformed["available"] is False
    assert malformed["model_generated"] is False

    def http_err(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    failed = interpret_text(
        title="t",
        raw_text="r",
        url="https://example.test/a",
        settings=settings,
        client=httpx.Client(transport=httpx.MockTransport(http_err)),
    )
    assert failed["available"] is False
    assert "llm_http_429" in str(failed["reason"])


def test_production_rss_settings_start_no_ingest_loop_and_stay_healthy(monkeypatch):
    """docker-compose.yml runs rss + serve without INTELLIGENCE_NEWS_INGEST: only the evaluation loop may pull feeds."""
    from fastapi.testclient import TestClient

    import intelligence_agents.service as service

    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "PAPER")
    monkeypatch.setenv("INTELLIGENCE_SERVICE_MODE", "oneshot")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "rss")
    monkeypatch.setenv("INTELLIGENCE_STORE", "memory")
    monkeypatch.setenv("INTELLIGENCE_SYMBOLS", "RELIANCE")
    monkeypatch.delenv("INTELLIGENCE_NEWS_INGEST", raising=False)
    started: list[str] = []

    async def refuse(*args, **kwargs):
        started.append("news_ingest_loop")

    monkeypatch.setattr(service, "news_ingest_loop", refuse)
    with TestClient(service.create_app(IntelligenceSettings.from_env())) as client:
        body = client.get("/health").json()
    assert started == []
    assert body.get("reason") not in {"news_stale", "news_ingest_failures"}


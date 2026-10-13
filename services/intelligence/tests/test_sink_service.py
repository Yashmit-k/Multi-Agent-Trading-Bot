from datetime import datetime, timezone

import httpx
from contracts.enums import TradingMode
from contracts.fixtures import sample_agent_signal

from intelligence_agents.sink.http import HttpSignalSink
from intelligence_agents.settings import IntelligenceSettings


def test_http_headers_auth_and_duplicate():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "accepted": False,
                "signal_id": sample_agent_signal().signal_id,
                "duplicate": True,
                "message": "already stored",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    as_of = datetime(2024, 6, 3, 10, tzinfo=timezone.utc)
    sink = HttpSignalSink(
        "http://core",
        "secret-token",
        TradingMode.BACKTEST,
        replay_as_of=as_of,
        retries=1,
        client=client,
    )
    result = sink.submit(sample_agent_signal())
    assert result.duplicate is True
    assert seen[0].headers["Authorization"] == "Bearer secret-token"
    assert seen[0].headers["X-Trading-Mode"] == "BACKTEST"
    assert seen[0].headers["X-Replay-As-Of"] == as_of.isoformat()


def test_http_retries_5xx():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "accepted": True,
                "signal_id": sample_agent_signal().signal_id,
                "duplicate": False,
                "message": "accepted",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sink = HttpSignalSink("http://core", "t", TradingMode.PAPER, retries=3, client=client, sleeper=lambda _: None)
    result = sink.submit(sample_agent_signal())
    assert result.accepted is True
    assert calls["n"] == 3


def test_health_degraded_without_sink_in_backtest(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "BACKTEST")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "fixtures")
    settings = IntelligenceSettings.from_env()
    assert settings.trading_mode.value == "BACKTEST"


def test_oneshot_paper_allows_ingest_without_sink(monkeypatch):
    from intelligence_agents.service import _require_live_sink

    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "PAPER")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "fixtures")
    monkeypatch.setenv("INTELLIGENCE_SERVICE_MODE", "oneshot")
    monkeypatch.delenv("INTERNAL_SIGNAL_TOKEN", raising=False)
    settings = IntelligenceSettings.from_env()
    assert _require_live_sink(settings, None) is None


def test_serve_paper_builds_http_sink_when_token_present(monkeypatch):
    from intelligence_agents.service import _require_live_sink
    from intelligence_agents.sink.http import HttpSignalSink

    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "PAPER")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "fixtures")
    monkeypatch.setenv("INTELLIGENCE_SERVICE_MODE", "serve")
    monkeypatch.setenv("INTERNAL_SIGNAL_TOKEN", "token")
    monkeypatch.setenv("CORE_API_URL", "http://core")
    settings = IntelligenceSettings.from_env()
    sink = _require_live_sink(settings, None)
    assert isinstance(sink, HttpSignalSink)


def test_serve_backtest_refused(monkeypatch):
    from intelligence_agents.errors import ConfigError

    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "BACKTEST")
    monkeypatch.setenv("INTELLIGENCE_SERVICE_MODE", "serve")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "fixtures")
    try:
        IntelligenceSettings.from_env()
        raised = False
    except ConfigError:
        raised = True
    assert raised


def test_serve_paper_requires_token(monkeypatch):
    from intelligence_agents.errors import ConfigError

    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "PAPER")
    monkeypatch.setenv("INTELLIGENCE_SERVICE_MODE", "serve")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "fixtures")
    monkeypatch.setenv("INTERNAL_SIGNAL_TOKEN", "")
    try:
        IntelligenceSettings.from_env()
        raised = False
    except ConfigError:
        raised = True
    assert raised


def test_health_reports_configured_ollama_before_cycle(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "BACKTEST")
    monkeypatch.setenv("INTELLIGENCE_SERVICE_MODE", "oneshot")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "fixtures")
    monkeypatch.setenv("LLM_BASE_URL", "http://host.docker.internal:11434/v1")
    monkeypatch.setenv("LLM_API_KEY", "ollama")
    monkeypatch.setenv("LLM_TIER1_MODEL", "phi3:mini")
    settings = IntelligenceSettings.from_env()
    assert settings.llm_provider() == "ollama"
    assert settings.llm_tier1_model == "phi3:mini"
    assert settings.llm_mode() == "openai"


def test_http_retries_then_raises():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sink = HttpSignalSink("http://core", "t", TradingMode.PAPER, retries=3, client=client, sleeper=lambda _: None)
    try:
        sink.submit(sample_agent_signal())
        raised = False
    except httpx.HTTPError:
        raised = True
    assert raised
    assert calls["n"] == 3

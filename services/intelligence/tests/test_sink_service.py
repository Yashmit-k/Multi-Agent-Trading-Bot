from datetime import datetime, timezone

import httpx
from contracts.enums import TradingMode
from contracts.fixtures import sample_agent_signal

from intelligence_agents.sink.http import HttpSignalSink
from intelligence_agents.service import create_app
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
    app = create_app(IntelligenceSettings.from_env(), sink=None)
    assert app.state.settings.trading_mode.value == "BACKTEST"


def test_refuse_live_without_sink(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "PAPER")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "fixtures")
    settings = IntelligenceSettings.from_env()
    try:
        create_app(settings, sink=None)
        raised = False
    except RuntimeError:
        raised = True
    assert raised

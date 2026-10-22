"""Real prices from Core for the valuation agent, and RSS plus a fundamentals file together."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from contracts.fakes import FakeMarketDataProvider
from intelligence_agents.fundamentals.store import MemoryFundamentalStore
from intelligence_agents.loop import refresh_sources
from intelligence_agents.market import CoreMarketDataProvider
from intelligence_agents.runtime import make_price_provider
from intelligence_agents.settings import IntelligenceSettings

AS_OF = datetime(2026, 10, 15, 6, 0, tzinfo=timezone.utc)


def _bar(timeframe: str, end: datetime, close: str) -> dict:
    span = timedelta(minutes=5) if timeframe == "5m" else timedelta(hours=6, minutes=15)
    return {"symbol": "INFY", "exchange": "NSE", "timeframe": timeframe, "open": close, "high": close, "low": close,
            "close": close, "volume": 1000, "start": (end - span).isoformat(), "end": end.isoformat()}


def _provider(handler) -> CoreMarketDataProvider:
    return CoreMarketDataProvider("http://core-api:8000", "token", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_uses_latest_five_minute_close_with_auth() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=[_bar("5m", AS_OF - timedelta(minutes=5), "1090.25")])

    quote = _provider(handler).get_quote("INFY", AS_OF)
    assert str(quote.last_price) == "1090.25"
    assert quote.timestamp == AS_OF - timedelta(minutes=5)
    assert seen["auth"] == "Bearer token"
    assert seen["params"]["timeframe"] == "5m" and seen["params"]["as_of"] == AS_OF.isoformat()


def test_falls_back_to_daily_close() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["timeframe"] == "5m":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[_bar("1d", AS_OF - timedelta(hours=20), "1088.00")])

    assert str(_provider(handler).get_quote("INFY", AS_OF).last_price) == "1088.00"


def test_never_returns_a_bar_after_as_of() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_bar(request.url.params["timeframe"], AS_OF + timedelta(minutes=5), "999.00")])

    with pytest.raises(LookupError):
        _provider(handler).get_quote("INFY", AS_OF)


def test_core_errors_become_lookup_errors() -> None:
    with pytest.raises(LookupError):
        _provider(lambda request: httpx.Response(503, json={})).get_quote("INFY", AS_OF)
    with pytest.raises(LookupError):
        _provider(lambda request: httpx.Response(404, json={})).get_quote("INFY", AS_OF)


def _settings(monkeypatch, **env: str) -> IntelligenceSettings:
    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "PAPER")
    monkeypatch.setenv("INTELLIGENCE_SERVICE_MODE", "oneshot")
    monkeypatch.setenv("CORE_API_URL", "http://core-api:8000")
    monkeypatch.setenv("INTERNAL_SIGNAL_TOKEN", "write")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return IntelligenceSettings.from_env()


def test_live_modes_use_core_prices_and_fixtures_stay_fake(monkeypatch) -> None:
    live = _settings(monkeypatch, INTELLIGENCE_DATA_SOURCE="rss", NEWS_RSS_URLS="https://example.test/rss", CORE_API_TOKEN="t")
    assert isinstance(make_price_provider(live), CoreMarketDataProvider)
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "fixtures")
    assert isinstance(make_price_provider(IntelligenceSettings.from_env()), FakeMarketDataProvider)


CSV = """symbol,metric,value,unit,period,announced_at,available_at,source,source_id
INFY,eps,17.25,INR,2026Q2,2026-10-16T16:00:00+05:30,2026-10-16T16:00:00+05:30,nse-results,INFY-2026Q2-eps
INFY,eps,16.40,INR,2026Q1,2026-07-17T16:00:00+05:30,2026-07-17T16:00:00+05:30,nse-results,INFY-2026Q1-eps
"""


class _Runner:
    def __init__(self) -> None:
        self.fund_store = MemoryFundamentalStore()


def test_rss_mode_also_loads_a_fundamentals_file(monkeypatch, tmp_path) -> None:
    path = tmp_path / "fundamentals.csv"
    path.write_text(CSV)
    settings = _settings(monkeypatch, INTELLIGENCE_DATA_SOURCE="rss", NEWS_RSS_URLS="https://example.test/rss", INTELLIGENCE_FUNDAMENTALS_CSV=str(path))

    class Puller:
        pulled: list[str] = []

        def pull(self, url: str) -> int:
            self.pulled.append(url)
            return 0

    runner, puller = _Runner(), Puller()
    refresh_sources(settings, runner, puller)
    assert puller.pulled == ["https://example.test/rss"]
    assert len(runner.fund_store.points_for("INFY", datetime(2026, 12, 1, tzinfo=timezone.utc))) == 2
    # Point-in-time: the Q2 figure is invisible before it was announced.
    assert len(runner.fund_store.points_for("INFY", datetime(2026, 10, 1, tzinfo=timezone.utc))) == 1
    refresh_sources(settings, runner, puller)  # reloading is idempotent
    assert len(runner.fund_store.points_for("INFY", datetime(2026, 12, 1, tzinfo=timezone.utc))) == 2


def test_missing_fundamentals_file_is_a_warning_not_a_crash(monkeypatch, tmp_path) -> None:
    settings = _settings(monkeypatch, INTELLIGENCE_DATA_SOURCE="rss", NEWS_RSS_URLS="https://example.test/rss", INTELLIGENCE_FUNDAMENTALS_CSV=str(tmp_path / "absent.csv"))

    class Puller:
        def pull(self, url: str) -> int:
            return 0

    runner = _Runner()
    refresh_sources(settings, runner, Puller())
    assert runner.fund_store.points_for("INFY", datetime(2026, 12, 1, tzinfo=timezone.utc)) == []

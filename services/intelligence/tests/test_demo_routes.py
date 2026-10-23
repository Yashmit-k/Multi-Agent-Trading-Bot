from datetime import datetime, timezone

from fastapi import HTTPException

from intelligence_agents.runtime import make_stores
from intelligence_agents.service import _data_origin, _origin_metadata, _parse_as_of
from intelligence_agents.settings import IntelligenceSettings


def _settings(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_TRADING_MODE", "BACKTEST")
    monkeypatch.setenv("INTELLIGENCE_SERVICE_MODE", "oneshot")
    monkeypatch.setenv("INTELLIGENCE_DATA_SOURCE", "fixtures")
    monkeypatch.setenv("INTELLIGENCE_STORE", "memory")
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    return IntelligenceSettings.from_env()


def test_news_fixture_labelled(monkeypatch):
    settings = _settings(monkeypatch)
    news, _funds = make_stores(settings)
    as_of = datetime(2024, 6, 3, 10, 0, tzinfo=timezone.utc)
    rows = news.articles_for("RELIANCE", as_of)
    assert rows
    tagged = _origin_metadata(rows[0].metadata, _data_origin(settings))
    assert tagged["fixture"] is True
    assert tagged["data_origin"] == "demo_fixture"
    assert tagged["live"] is False
    assert rows[0].title
    assert rows[0].source
    assert str(rows[0].url)
    assert "RELIANCE" in rows[0].symbols
    assert news.articles_for("TATAMOTORS", as_of) == []


def test_fundamentals_fixture_not_claimed_as_nse_vintage(monkeypatch):
    settings = _settings(monkeypatch)
    _news, funds = make_stores(settings)
    as_of = datetime(2024, 6, 3, 10, 0, tzinfo=timezone.utc)
    rows = funds.points_for("TCS", as_of)
    assert rows
    tagged = _origin_metadata(rows[0].metadata, _data_origin(settings))
    assert tagged["availability"] == "fixture_point_in_time"
    assert tagged["not_historical_nse_vintage"] is True
    assert tagged["fixture"] is True
    assert all(row.period != "Q1FY2025" for row in rows)
    assert all(row.available_at <= as_of for row in rows)


def test_invalid_as_of():
    try:
        _parse_as_of("not-a-time")
        raised = False
    except HTTPException as exc:
        raised = exc.status_code == 400
    assert raised
    try:
        _parse_as_of("2024-06-03T10:00:00")
        naive = False
    except HTTPException as exc:
        naive = exc.status_code == 400
    assert naive
    aware = _parse_as_of("2024-06-03T10:00:00+00:00")
    assert aware.tzinfo is not None

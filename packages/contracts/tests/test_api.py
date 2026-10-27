"""Vocabulary lock and reference HTTP contract."""

from fastapi.testclient import TestClient

from contracts.api import app
from contracts.enums import AgentName, Horizon, TradingMode
from contracts.fixtures import sample_agent_signal
from contracts.version import __version__


def test_closed_vocabularies() -> None:
    assert {item.value for item in AgentName} == {
        "technical",
        "momentum",
        "mean_reversion",
        "volume",
        "regime",
        "ml",
        "news",
        "fundamental",
        "valuation",
        "earnings",
        "global_markets",
    }
    assert {item.value for item in Horizon} == {"INTRADAY", "SWING", "LONG_TERM"}
    assert {item.value for item in TradingMode} == {"BACKTEST", "PAPER", "SHADOW", "LIVE"}
    assert __version__ == "1.2.0"


def test_signal_endpoint_and_catalog() -> None:
    client = TestClient(app)
    created = client.post("/api/v1/internal/signals", json=sample_agent_signal().model_dump(mode="json"))
    assert created.status_code == 200
    assert created.json()["accepted"] is True
    assert created.json()["signal_id"] == "sig-reliance-technical-20240603"

    rejected = client.post(
        "/api/v1/internal/signals",
        json=sample_agent_signal().model_dump(mode="json") | {"signal": 4},
    )
    assert rejected.status_code == 422

    catalog = client.get("/api/v1/system/contracts")
    assert catalog.status_code == 200
    body = catalog.json()
    assert body["contract_version"] == "1.2.0"
    assert body["schema_versions"]["AgentSignal"] == "1.0"
    assert body["event_versions"]["agent.signal"] == "1.0"
    assert "technical" in body["supported_agents"]
    assert "INTRADAY" in body["supported_horizons"]
    assert "BACKTEST" in body["supported_modes"]

from fastapi.testclient import TestClient

from app import app


def test_system_status() -> None:
    client = TestClient(app)
    body = client.get("/api/v1/system/status").json()
    assert body["trading_mode"] == "PAPER"
    assert body["live_enabled"] is False


def test_unknown_route_is_501() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/backtests")
    assert response.status_code == 501


def test_signals_are_contract_shaped() -> None:
    client = TestClient(app)
    rows = client.get("/api/v1/signals").json()
    assert rows[0]["schema_version"] == "1.0"
    assert rows[0]["agent_name"] == "technical"

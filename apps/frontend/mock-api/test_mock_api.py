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


def test_kill_switch_stub() -> None:
    client = TestClient(app)
    body = client.get("/api/v1/risk/status").json()
    assert body["kill_switch"] == "disarmed"
    armed = client.post("/api/v1/risk/kill-switch", json={"armed": True}).json()
    assert armed["kill_switch"] == "armed"
    client.post("/api/v1/risk/kill-switch", json={"armed": False})


def test_daily_performance_unavailable() -> None:
    client = TestClient(app)
    body = client.get("/api/v1/paper/daily-performance").json()
    assert body == {"status": "unavailable", "reason": "no_daily_equity_history"}


def test_signals_are_contract_shaped() -> None:
    client = TestClient(app)
    rows = client.get("/api/v1/signals").json()
    assert rows[0]["schema_version"] == "1.0"
    assert rows[0]["agent_name"] == "technical"

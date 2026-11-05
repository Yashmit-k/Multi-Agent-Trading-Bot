"""Momentum live, phase 1: read-only account view and settings. No route here may place an order."""

from fastapi.testclient import TestClient

from contracts.enums import TradingMode
from core_api.app import create_app
from core_api.live import summarize_account
from core_api.settings import Settings
from core_db.repository import CoreRepository
from core_db.session import create_schema

HEADERS = {"Authorization": "Bearer core"}


class TokenException(Exception):
    """Same name as kiteconnect's exception for an expired session."""


class AccountKite:
    def __init__(self, expired: bool = False) -> None:
        self.expired = expired
        self.calls: list[str] = []

    def login_url(self) -> str:
        return "https://kite.zerodha.com/connect/login?api_key=test"

    def generate_session(self, request_token: str) -> dict[str, object]:
        return {"access_token": "access-token"}

    def use_access_token(self, token: str) -> None:
        pass

    def _call(self, name: str) -> None:
        self.calls.append(name)
        if self.expired:
            raise TokenException("Incorrect `api_key` or `access_token`.")

    def holdings(self) -> list[dict]:
        self._call("holdings")
        return [
            {"tradingsymbol": "MTARTECH", "exchange": "NSE", "quantity": 4, "t1_quantity": 0, "average_price": 3100.0, "last_price": 3150.5, "close_price": 3140.0},
            {"tradingsymbol": "CUPID", "exchange": "NSE", "quantity": 0, "t1_quantity": 30, "average_price": 340.0, "last_price": 351.0, "close_price": 349.0},
            {"tradingsymbol": "SOLD", "exchange": "NSE", "quantity": 0, "t1_quantity": 0, "average_price": 10.0, "last_price": 11.0, "close_price": 11.0},
        ]

    def positions(self) -> dict:
        self._call("positions")
        return {"net": [{"tradingsymbol": "GCSL", "product": "CNC", "quantity": 12, "average_price": 820.0}, {"tradingsymbol": "FLAT", "product": "CNC", "quantity": 0}], "day": []}

    def equity_margins(self) -> dict:
        self._call("margins")
        return {"net": 5230.5, "available": {"live_balance": 5230.5, "opening_balance": 5000.0, "cash": 5000.0}}

    def orders(self) -> list[dict]:
        self._call("orders")
        return [{"order_id": "1", "tradingsymbol": "GCSL", "transaction_type": "BUY", "quantity": 12, "filled_quantity": 12, "price": 825.0, "average_price": 820.0, "status": "COMPLETE", "tag": None, "order_timestamp": "2026-11-05 09:15:02"}]

    # Order calls exist on the real client; phase 1 must never reach them.
    def place_order(self, **_: object) -> None:
        raise AssertionError("phase 1 must not place orders")


def _settings(collector: bool = False) -> Settings:
    return Settings(
        database_url="sqlite://",
        redis_url="redis://localhost:6379/0",
        core_api_token="core",
        internal_signal_token="internal",
        max_clock_skew_seconds=5,
        trading_mode=TradingMode.PAPER,
        market_data_collector=collector,
    )


def _client(kite=None) -> tuple[TestClient, object]:
    app = create_app(_settings(), CoreRepository(create_schema("sqlite://")), kite_client=kite)
    return TestClient(app), app


def test_settings_start_off_and_need_the_core_token() -> None:
    client, _ = _client()
    assert client.get("/api/v1/live/settings").status_code == 401
    view = client.get("/api/v1/live/settings", headers=HEADERS).json()
    assert view["settings"] == {"amount": 0, "stocks": 10, "mode": "off", "max_order": 25000, "funding": "fixed"}
    assert view["changes"] == []


def test_settings_save_validate_and_log_each_change() -> None:
    client, _ = _client()
    saved = client.post("/api/v1/live/settings", headers=HEADERS, json={"values": {"amount": "1,50,000", "stocks": 15, "mode": "dry_run"}, "operator": "web-operator"})
    assert saved.status_code == 200
    assert saved.json()["settings"] == {"amount": 150000, "stocks": 15, "mode": "dry_run", "max_order": 25000, "funding": "fixed"}
    change = saved.json()["changes"][0]
    assert change["by"] == "web-operator"
    assert change["changed"]["stocks"] == {"from": 10, "to": 15}
    assert "max_order" not in change["changed"]
    # Live mode is refused until order placement exists; out-of-range values are refused; nothing is half-saved.
    refused = client.post("/api/v1/live/settings", headers=HEADERS, json={"values": {"mode": "live", "stocks": 3}})
    assert refused.status_code == 422
    assert set(refused.json()["detail"]["errors"]) == {"mode", "stocks"}
    assert client.get("/api/v1/live/settings", headers=HEADERS).json()["settings"]["mode"] == "dry_run"
    # Saving the same values adds no log entry.
    client.post("/api/v1/live/settings", headers=HEADERS, json={"values": {"stocks": 15}})
    assert len(client.get("/api/v1/live/settings", headers=HEADERS).json()["changes"]) == 1


def test_account_needs_a_client_and_a_login() -> None:
    client, _ = _client()
    assert client.get("/api/v1/live/account", headers=HEADERS).json()["detail"] == "zerodha_not_configured"
    kite = AccountKite()
    client, _ = _client(kite)
    assert client.get("/api/v1/live/account").status_code == 401
    missing = client.get("/api/v1/live/account", headers=HEADERS)
    assert missing.status_code == 409 and missing.json()["detail"] == "zerodha_login_required"
    assert kite.calls == []


def test_login_without_collector_skips_the_history_seed_and_reads_the_account() -> None:
    kite = AccountKite()
    client, app = _client(kite)
    assert client.get("/api/v1/zerodha/callback", params={"request_token": "t"}).json() == {"authenticated": True, "live_enabled": False}
    assert app.state.historical_gate.mark_queued()  # nothing was queued by the login
    body = client.get("/api/v1/live/account", headers=HEADERS).json()
    assert [row["symbol"] for row in body["holdings"]] == ["MTARTECH", "CUPID"]
    assert body["holdings"][1]["t1_quantity"] == 30
    assert body["positions"] == [{"symbol": "GCSL", "product": "CNC", "quantity": 12, "average_price": 820.0}]
    assert body["cash"]["available"] == 5230.5
    assert body["orders"][0]["status"] == "COMPLETE"
    assert body["live_enabled"] is False


def test_an_expired_kite_session_asks_for_login_again() -> None:
    kite = AccountKite(expired=True)
    client, _ = _client(kite)
    client.get("/api/v1/zerodha/callback", params={"request_token": "t"})
    expired = client.get("/api/v1/live/account", headers=HEADERS)
    assert expired.status_code == 409 and expired.json()["detail"] == "zerodha_login_required"


def test_summary_drops_raw_fields() -> None:
    summary = summarize_account(
        [{"tradingsymbol": "X", "quantity": 1, "user_id": "AB1234", "isin": "INE000"}], {"net": []}, {"available": {}}, []
    )
    assert set(summary["holdings"][0]) == {"symbol", "exchange", "quantity", "t1_quantity", "average_price", "last_price", "close_price"}


def test_all_cash_funding_is_validated_and_back_to_fixed_resets_the_strategy_cash() -> None:
    from core_api.live import load_book, save_book

    client, app = _client()
    assert client.post("/api/v1/live/settings", headers=HEADERS, json={"values": {"funding": "everything"}}).status_code == 422
    client.post("/api/v1/live/settings", headers=HEADERS, json={"values": {"amount": 100000, "mode": "dry_run"}})
    repository = app.state.repository
    save_book(repository, {"shares": {"AAA": 10}, "cash": 4000.0, "contributed": 100000.0, "ref": {}})
    view = client.post("/api/v1/live/settings", headers=HEADERS, json={"values": {"funding": "all_cash", "amount": 50000}}).json()
    assert view["settings"]["funding"] == "all_cash" and view["book"]["cash"] == 4000.0  # amount changes do nothing in all-cash
    view = client.post("/api/v1/live/settings", headers=HEADERS, json={"values": {"funding": "fixed", "amount": 20000}}).json()
    assert view["book"]["cash"] == 20000.0 and view["book"]["shares"] == {"AAA": 10}
    assert load_book(repository)["contributed"] == 20000.0

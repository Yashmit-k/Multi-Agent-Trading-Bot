"""Manual paper orders: same risk checks as agents, portfolio limits overridable, never the order checks."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from contracts.enums import Exchange, Side, Timeframe
from contracts.schemas.market import Candle
from core_db.repository import CoreRepository
from core_ingestion.service import MemoryEventPublisher
from core_paper.manual import ManualOrderRejected, place_manual_order
from test_execution_policy import DECISION, _arm, _daily

UTC = timezone.utc


def _ready(repository: CoreRepository, symbol: str = "TCS") -> None:
    _arm(repository, Decimal("442"))
    _daily(repository, symbol, Decimal("400"))
    instrument = repository.get_by_symbol(symbol)
    assert instrument is not None
    repository.add_membership(instrument.instrument_id, "NIFTY50", datetime(2024, 1, 1, tzinfo=UTC), None)
    end = DECISION
    repository.upsert_candles([Candle(symbol=symbol, exchange=Exchange.NSE, timeframe=Timeframe.M5, open=Decimal("400"), high=Decimal("401"), low=Decimal("399"), close=Decimal("400"), volume=10, start=end - timedelta(minutes=5), end=end)])


def _place(repository: CoreRepository, **kwargs):  # type: ignore[no-untyped-def]
    args = {"symbol": "TCS", "side": Side.BUY, "quantity": None, "limit_price": None, "override_limits": False, "operator": "tester", "note": "", "now": DECISION}
    args.update(kwargs)
    return place_manual_order(repository, MemoryEventPublisher(), **args)


def test_manual_buy_is_sized_by_the_user_cap_and_tagged(repository: CoreRepository) -> None:
    _ready(repository)
    repository.save_setting("risk", {"max_order_notional": "8000"}, updated_by="t", now=DECISION)
    result = _place(repository, quantity=15, limit_price=Decimal("398"))
    order = result["order"]
    assert result["risk"]["status"] == "APPROVED" and order is not None
    assert order["quantity"] == 15 and Decimal(order["limit_price"]) == Decimal("398")
    assert result["proposal"]["strategy_id"] == "manual" and result["proposal"]["metadata"]["operator"] == "tester"


def test_order_checks_cannot_be_overridden(repository: CoreRepository) -> None:
    _ready(repository)
    result = _place(repository, quantity=10_000, override_limits=True)  # Rs 40 lakh: over cap and cash
    assert result["risk"]["status"] == "REJECTED" and result["order"] is None


def test_portfolio_limits_can_be_overridden(repository: CoreRepository) -> None:
    _ready(repository)
    repository.save_setting("risk", {"max_open_positions": 1, "max_per_stock": "1000"}, updated_by="t", now=DECISION)
    assert _place(repository, quantity=5)["risk"]["status"] == "REJECTED"  # per-stock Rs 1,000 < Rs 2,000
    assert _place(repository, quantity=5, override_limits=True, now=DECISION + timedelta(seconds=1))["risk"]["status"] == "APPROVED"


def test_sell_requires_a_holding(repository: CoreRepository) -> None:
    _ready(repository)
    try:
        _place(repository, side=Side.SELL)
    except ManualOrderRejected as exc:
        assert exc.code == "not_held"
    else:
        raise AssertionError("expected not_held")


def test_settings_api_validates(repository: CoreRepository) -> None:
    from contracts.enums import TradingMode
    from core_api.app import create_app
    from core_api.settings import Settings

    settings = Settings(database_url="sqlite://", redis_url="redis://localhost:6379/0", core_api_token="core", internal_signal_token="internal", max_clock_skew_seconds=5, trading_mode=TradingMode.PAPER)
    client = TestClient(create_app(settings, repository, MemoryEventPublisher()))
    auth = {"Authorization": "Bearer core"}
    ok = client.post("/api/v1/settings/risk", json={"values": {"daily_entry_limit": 3}}, headers=auth)
    assert ok.status_code == 200 and ok.json()["settings"]["daily_entry_limit"] == 3
    assert client.get("/api/v1/settings/risk", headers=auth).json()["settings"]["daily_entry_limit"] == 3
    bad = client.post("/api/v1/settings/risk", json={"values": {"max_order_notional": "999999"}}, headers=auth)
    assert bad.status_code == 422

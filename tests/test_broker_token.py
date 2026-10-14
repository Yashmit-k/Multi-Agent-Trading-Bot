"""A Zerodha login survives a Core restart until the 06:00 IST expiry."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from contracts.enums import TradingMode
from core_api.app import create_app, kite_token_cutoff
from core_api.settings import Settings
from core_db.repository import CoreRepository
from core_ingestion.service import MemoryEventPublisher


class FakeKite:
    def __init__(self) -> None:
        self.access_token = None

    def use_access_token(self, token: str) -> None:
        self.access_token = token

    def login_url(self) -> str:
        return "https://kite.example/login"


def _settings() -> Settings:
    return Settings(
        database_url="sqlite://", redis_url="redis://localhost:6379/0", core_api_token="core",
        internal_signal_token="internal", max_clock_skew_seconds=5, trading_mode=TradingMode.PAPER,
    )


def test_cutoff_is_the_latest_0600_ist() -> None:
    before_six = datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc)  # 05:30 IST
    after_six = datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc)  # 06:30 IST
    assert kite_token_cutoff(before_six) == datetime(2026, 10, 14, 0, 30, tzinfo=timezone.utc)
    assert kite_token_cutoff(after_six) == datetime(2026, 10, 15, 0, 30, tzinfo=timezone.utc)


def test_token_from_today_is_restored(repository: CoreRepository) -> None:
    repository.save_broker_token("zerodha", "tok-today", datetime.now(timezone.utc))
    kite = FakeKite()
    app = create_app(_settings(), repository, MemoryEventPublisher(), kite_client=kite)
    status = TestClient(app).get("/api/v1/zerodha/status", headers={"Authorization": "Bearer core"}).json()
    assert status["authenticated"] is True
    assert kite.access_token == "tok-today"


def test_expired_token_is_not_restored(repository: CoreRepository) -> None:
    repository.save_broker_token("zerodha", "tok-old", datetime.now(timezone.utc) - timedelta(days=2))
    kite = FakeKite()
    app = create_app(_settings(), repository, MemoryEventPublisher(), kite_client=kite)
    status = TestClient(app).get("/api/v1/zerodha/status", headers={"Authorization": "Bearer core"}).json()
    assert status["authenticated"] is False
    assert kite.access_token is None


def test_no_kite_client_means_no_restore(repository: CoreRepository) -> None:
    repository.save_broker_token("zerodha", "tok-today", datetime.now(timezone.utc))
    app = create_app(_settings(), repository, MemoryEventPublisher())
    assert app.state.zerodha_access_token is None

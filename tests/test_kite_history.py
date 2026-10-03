"""Kite login and historical candles. The fake client never opens a socket."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from contracts.enums import Timeframe, TradingMode
from core_api.app import create_app
from core_api.settings import Settings
from core_db.repository import CoreRepository
from core_db.session import create_schema
from core_market_data.kite_client import KiteConnectMarketClient
from core_market_data.zerodha import RequestPace, ZerodhaMarketDataProvider

UTC = timezone.utc
HEADERS = {"Authorization": "Bearer core"}


class FakeKite:
    def __init__(self) -> None:
        self.windows: list[tuple[int, str, datetime, datetime]] = []
        self.access_token: str | None = None
        self.historical_flags: list[tuple[bool, bool]] = []

    def login_url(self) -> str:
        return "https://kite.zerodha.com/connect/login?api_key=test"

    def generate_session(self, request_token: str) -> dict[str, object]:
        assert request_token == "request-token"
        self.access_token = "access-token"
        return {"access_token": self.access_token, "refresh_token": "refresh-token"}

    def instruments(self, exchange: str) -> list[dict[str, object]]:
        assert exchange == "NSE"
        return [
            {"tradingsymbol": "RELIANCE", "instrument_token": 738561},
            {"tradingsymbol": "INFY", "instrument_token": 408065},
        ]

    def quote(self, key: str) -> dict[str, object]:
        return {key: {"timestamp": "2024-06-03T10:00:00+05:30", "last_price": "2900.5", "volume": 12}}

    def historical_data(
        self,
        instrument_token: int,
        from_date: datetime,
        to_date: datetime,
        interval: str,
    ) -> list[dict[str, object]]:
        self.windows.append((instrument_token, interval, from_date, to_date))
        day = from_date.date()
        if interval == "day":
            return [
                {
                    "date": datetime(day.year, day.month, day.day),
                    "open": 2900,
                    "high": 2910,
                    "low": 2890,
                    "close": 2905,
                    "volume": 100,
                }
            ]
        return [
            {
                "date": datetime(day.year, day.month, day.day, 9, 15),
                "open": 2900,
                "high": 2902,
                "low": 2899,
                "close": 2901,
                "volume": 20,
            }
        ]


class RecordingKite:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def login_url(self) -> str:
        return "https://kite.example/login"

    def generate_session(self, request_token: str, api_secret: str) -> dict[str, str]:
        self.calls.append({"request_token": request_token, "api_secret": api_secret})
        return {"access_token": "token-1"}

    def set_access_token(self, access_token: str) -> None:
        self.calls.append({"access_token": access_token})

    def historical_data(self, instrument_token: int, from_date: datetime, to_date: datetime, interval: str, continuous: bool, oi: bool) -> list[dict[str, object]]:
        self.calls.append(
            {
                "instrument_token": instrument_token,
                "interval": interval,
                "continuous": continuous,
                "oi": oi,
            }
        )
        return []

    def instruments(self, exchange: str) -> list[dict[str, object]]:
        return []

    def quote(self, key: str) -> dict[str, object]:
        return {}


def _settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        redis_url="redis://localhost:6379/0",
        core_api_token="core",
        internal_signal_token="internal",
        max_clock_skew_seconds=5,
        trading_mode=TradingMode.PAPER,
    )


def _one_member() -> CoreRepository:
    repository = CoreRepository(create_schema("sqlite://"))
    instrument = repository.upsert_instrument(symbol="RELIANCE", exchange="NSE", trading_symbol="RELIANCE")
    repository.add_membership(
        instrument.instrument_id,
        "NIFTY50",
        datetime(2024, 1, 1, tzinfo=UTC),
        None,
    )
    return repository


def test_login_routes_keep_the_access_token_in_memory() -> None:
    repository = CoreRepository(create_schema("sqlite://"))
    fake = FakeKite()
    app = create_app(_settings(), repository, kite_client=fake)
    app.state.kite_pace = RequestPace(0)
    client = TestClient(app)
    assert client.get("/api/v1/zerodha/connect").status_code == 401
    denied = client.get("/api/v1/zerodha/status")
    assert denied.status_code == 401
    status = client.get("/api/v1/zerodha/status", headers=HEADERS)
    assert status.json() == {"configured": True, "authenticated": False, "live_enabled": False}
    connect = client.get("/api/v1/zerodha/connect", headers=HEADERS)
    assert connect.status_code == 200
    assert connect.json()["login_url"].startswith("https://kite.zerodha.com/")
    assert connect.json()["live_enabled"] is False
    callback = client.get("/api/v1/zerodha/callback", params={"request_token": "request-token"})
    assert callback.status_code == 200
    assert callback.json() == {"authenticated": True, "live_enabled": False}
    assert "access_token" not in callback.json()
    assert app.state.zerodha_access_token == "access-token"
    again = client.get("/api/v1/zerodha/status", headers=HEADERS)
    assert again.json()["authenticated"] is True
    assert again.json()["live_enabled"] is False


def test_connect_without_a_client_is_unavailable() -> None:
    app = create_app(_settings(), CoreRepository(create_schema("sqlite://")))
    client = TestClient(app)
    missing = client.get("/api/v1/zerodha/connect", headers=HEADERS)
    assert missing.status_code == 503
    assert missing.json()["detail"] == "zerodha_not_configured"


def test_seed_history_uses_stored_tokens_and_chunks() -> None:
    repository = _one_member()
    fake = FakeKite()
    pace = RequestPace(0)
    provider = ZerodhaMarketDataProvider(repository, fake, pace=pace)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 6, 3, tzinfo=UTC)
    written = provider.ingest_seed_history(start, end).written
    stored = repository.get_by_symbol("RELIANCE")
    assert stored is not None
    assert stored.instrument_id == "NSE:RELIANCE"
    assert stored.instrument_token == 738561
    assert repository.get_by_symbol("INFY") is None
    assert written == 3
    visible = datetime(2024, 6, 4, tzinfo=UTC)
    day = repository.candles_until("RELIANCE", Timeframe.D1, visible)
    five = repository.candles_until("RELIANCE", Timeframe.M5, visible)
    assert len(day) == 1
    assert len(five) == 2
    assert day[0].end > day[0].start
    assert five[0].timeframe == Timeframe.M5
    intervals = [item[1] for item in fake.windows]
    assert intervals.count("5minute") == 2
    assert intervals.count("day") == 1
    assert all(item[0] == 738561 for item in fake.windows)
    assert pace.waits == 4


def test_quote_reads_the_keyed_kite_payload() -> None:
    repository = _one_member()
    provider = ZerodhaMarketDataProvider(repository, FakeKite(), pace=RequestPace(0))
    quote = provider.get_quote("RELIANCE", datetime(2024, 6, 3, tzinfo=UTC))
    assert quote.last_price == Decimal("2900.5")
    assert quote.volume == 12
    assert quote.timestamp.tzinfo is not None


def test_real_client_forces_equity_historical_flags() -> None:
    recording = RecordingKite()
    client = KiteConnectMarketClient("key", "secret", kite=recording)
    client.generate_session("request-token")
    client.historical_data(1, datetime(2024, 1, 1), datetime(2024, 1, 2), "day")
    assert recording.calls[0]["api_secret"] == "secret"
    assert recording.calls[1] == {"access_token": "token-1"}
    assert recording.calls[2]["continuous"] is False
    assert recording.calls[2]["oi"] is False


def test_five_minute_window_is_one_hundred_days() -> None:
    repository = _one_member()
    repository.upsert_instrument(symbol="RELIANCE", exchange="NSE", trading_symbol="RELIANCE", instrument_token=738561)
    fake = FakeKite()
    provider = ZerodhaMarketDataProvider(repository, fake, pace=RequestPace(0))
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=150)
    provider.get_candles("RELIANCE", Timeframe.M5, start, end)
    five = [item for item in fake.windows if item[1] == "5minute"]
    assert len(five) == 2
    assert five[0][2] == start
    assert five[0][3] - five[0][2] == timedelta(days=100)
    assert five[1][3] == end

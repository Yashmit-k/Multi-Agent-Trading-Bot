"""Phase 1–2 checks. SQLite by default. Postgres when DATABASE_URL is set."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from contracts.enums import TradingMode
from contracts.events import EventType
from contracts.fakes import FakeMarketDataProvider
from contracts.fixtures import FIXTURE_AS_OF, sample_agent_signal
from contracts.schemas.agent_signal import AgentSignal
from core_api.app import create_app
from core_api.settings import Settings
from core_candles import build_candles
from core_db.records import TickRecord
from core_db.repository import CoreRepository
from core_db.seed import SEED_PATH, load_seed
from core_db.session import create_schema
from core_features import build_feature_set
from core_ingestion.service import MemoryEventPublisher, ingest_signal
from core_market_data import HistoricalReplayMarketDataProvider, ZerodhaMarketDataProvider, ZerodhaUnavailable
from core_worker import run_once

UTC = timezone.utc


def _tick(symbol: str, stamp: datetime, price: str, volume: int = 10) -> TickRecord:
    return TickRecord(
        instrument_id=f"NSE:{symbol}",
        exchange="NSE",
        symbol=symbol,
        timestamp=stamp,
        price=Decimal(price),
        volume=volume,
    )


def test_seed_has_fifty_nifty_symbols(repository: CoreRepository) -> None:
    as_of = datetime(2024, 6, 3, tzinfo=UTC)
    members = repository.members_at(as_of)
    assert len(members) == 50
    assert {item.symbol for item in members} >= {"RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"}
    assert all(item.exchange == "NSE" and item.instrument_id == f"NSE:{item.symbol}" for item in members)
    assert len(list(SEED_PATH.open(encoding="utf-8"))) == 51


def test_future_membership_is_hidden(repository: CoreRepository) -> None:
    repository.add_membership(
        "NSE:RELIANCE",
        "NIFTY50",
        datetime(2025, 1, 1, tzinfo=UTC),
        None,
    )
    early = repository.members_at(datetime(2024, 6, 1, tzinfo=UTC))
    assert sum(1 for item in early if item.symbol == "RELIANCE") == 1


def test_candle_hides_unfinished_bar() -> None:
    start = datetime(2024, 6, 3, 3, 45, 10, tzinfo=UTC)
    later = datetime(2024, 6, 3, 3, 45, 40, tzinfo=UTC)
    ticks = [_tick("RELIANCE", start, "100"), _tick("RELIANCE", later, "110", 5)]
    hidden = build_candles(ticks, "1m", datetime(2024, 6, 3, 3, 45, 50, tzinfo=UTC))
    visible = build_candles(ticks, "1m", datetime(2024, 6, 3, 3, 46, tzinfo=UTC))
    assert hidden == []
    assert visible[0].open == Decimal("100")
    assert visible[0].close == Decimal("110")
    assert visible[0].volume == 15
    assert build_candles(ticks, "1m", datetime(2024, 6, 3, 3, 46, tzinfo=UTC)) == visible


def test_features_are_deterministic_and_respect_as_of() -> None:
    stamps = [
        datetime(2024, 6, 3, 3, 45, 10, tzinfo=UTC),
        datetime(2024, 6, 3, 3, 46, 10, tzinfo=UTC),
        datetime(2024, 6, 3, 3, 47, 10, tzinfo=UTC),
    ]
    ticks = [_tick("TCS", stamp, str(100 + index)) for index, stamp in enumerate(stamps)]
    as_of = datetime(2024, 6, 3, 3, 48, tzinfo=UTC)
    bars = build_candles(ticks, "1m", as_of)
    first = build_feature_set("TCS", "1m", bars, as_of)
    second = build_feature_set("TCS", "1m", bars, as_of)
    assert first == second
    assert first is not None
    earlier = build_feature_set("TCS", "1m", bars, datetime(2024, 6, 3, 3, 47, tzinfo=UTC))
    assert earlier is not None
    assert earlier.features["last_close"] != first.features["last_close"]


def test_ingestion_accepts_fixture_once(repository: CoreRepository) -> None:
    publisher = MemoryEventPublisher()
    signal = sample_agent_signal("RELIANCE")
    first = ingest_signal(
        repository,
        publisher,
        signal,
        mode=TradingMode.BACKTEST,
        now=datetime(2026, 9, 29, tzinfo=UTC),
        replay_as_of=signal.timestamp,
        skew_seconds=5,
    )
    second = ingest_signal(
        repository,
        publisher,
        signal,
        mode=TradingMode.BACKTEST,
        now=datetime(2026, 9, 29, tzinfo=UTC),
        replay_as_of=signal.timestamp,
        skew_seconds=5,
    )
    assert first.accepted and not first.duplicate
    assert second.duplicate and not second.accepted
    assert repository.signal_count() == 1
    assert len(publisher.events) == 1
    assert publisher.events[0][0] == "agent.events"


def test_live_clock_and_backtest_clock_differ(repository: CoreRepository) -> None:
    publisher = MemoryEventPublisher()
    signal = sample_agent_signal("INFY")
    backtest = ingest_signal(
        repository,
        publisher,
        signal,
        mode=TradingMode.BACKTEST,
        now=datetime(2026, 9, 29, tzinfo=UTC),
        replay_as_of=signal.timestamp,
        skew_seconds=5,
    )
    assert backtest.accepted
    future = signal.model_copy(update={"signal_id": "sig-future", "timestamp": datetime(2026, 9, 29, 0, 0, 10, tzinfo=UTC), "as_of": datetime(2026, 9, 29, tzinfo=UTC), "valid_until": datetime(2026, 9, 29, 1, tzinfo=UTC)})
    rejected = ingest_signal(
        repository,
        publisher,
        future,
        mode=TradingMode.PAPER,
        now=datetime(2026, 9, 29, tzinfo=UTC),
        replay_as_of=None,
        skew_seconds=5,
    )
    assert rejected.message == "future_timestamp"


def test_unknown_symbol_and_bad_agent(repository: CoreRepository) -> None:
    publisher = MemoryEventPublisher()
    missing = sample_agent_signal("RELIANCE").model_copy(update={"signal_id": "sig-missing", "symbol": "NOTREAL"})
    result = ingest_signal(
        repository,
        publisher,
        missing,
        mode=TradingMode.BACKTEST,
        now=FIXTURE_AS_OF,
        replay_as_of=FIXTURE_AS_OF,
        skew_seconds=5,
    )
    assert result.message == "unknown_symbol"
    with pytest.raises(Exception):
        AgentSignal.model_validate(sample_agent_signal().model_dump() | {"agent_name": "rsi"})


def test_worker_replay_and_api(repository: CoreRepository) -> None:
    as_of = datetime(2024, 6, 3, 3, 48, tzinfo=UTC)
    repository.insert_ticks(
        [
            _tick("HDFCBANK", datetime(2024, 6, 3, 3, 45, 5, tzinfo=UTC), "100", 20),
            _tick("HDFCBANK", datetime(2024, 6, 3, 3, 46, 5, tzinfo=UTC), "102", 20),
            _tick("HDFCBANK", datetime(2024, 6, 3, 10, 30, tzinfo=UTC), "999", 20),
        ]
    )
    assert run_once(repository, as_of) > 0
    replay = HistoricalReplayMarketDataProvider(repository, as_of)
    quote = replay.get_quote("HDFCBANK", as_of)
    assert quote.last_price == Decimal("102")
    assert replay.get_quote("HDFCBANK", datetime(2024, 6, 3, 12, tzinfo=UTC)).last_price == Decimal("102")
    feature = repository.feature_at("HDFCBANK", "1m", as_of, "1.0.0")
    assert feature is not None
    assert feature.features["last_close"] == build_feature_set("HDFCBANK", "1m", replay.get_candles("HDFCBANK", "1m", datetime(2024, 6, 3, tzinfo=UTC), as_of), as_of).features["last_close"]

    publisher = MemoryEventPublisher()
    settings = Settings(
        database_url="sqlite://",
        redis_url="redis://localhost:6379/0",
        core_api_token="core",
        internal_signal_token="internal",
        max_clock_skew_seconds=5,
        trading_mode=TradingMode.PAPER,
    )
    app = create_app(settings, repository, publisher)
    client = TestClient(app)
    assert client.get("/api/v1/system/status").status_code == 401
    status = client.get("/api/v1/system/status", headers={"Authorization": "Bearer core"})
    assert status.status_code == 200
    assert status.json()["live_enabled"] is False
    assert status.json()["exchange_scope"] == "NSE"
    portfolio = client.get("/api/v1/portfolio", headers={"Authorization": "Bearer core"})
    assert portfolio.status_code == 200
    assert portfolio.json()["snapshot"] is None
    later = client.get("/api/v1/performance", headers={"Authorization": "Bearer core"})
    assert later.status_code == 501
    signal = sample_agent_signal("HDFCBANK")
    created = client.post(
        "/api/v1/internal/signals",
        headers={"Authorization": "Bearer internal", "X-Trading-Mode": "BACKTEST", "X-Replay-As-Of": signal.timestamp.isoformat()},
        json=signal.model_dump(mode="json"),
    )
    assert created.status_code == 200
    assert created.json()["accepted"] is True
    again = client.post(
        "/api/v1/internal/signals",
        headers={"Authorization": "Bearer internal", "X-Trading-Mode": "BACKTEST", "X-Replay-As-Of": signal.timestamp.isoformat()},
        json=signal.model_dump(mode="json"),
    )
    assert again.json()["duplicate"] is True
    assert len(publisher.events) == 1


def test_fake_provider_and_contract_type() -> None:
    provider = FakeMarketDataProvider()
    assert provider.get_quote("RELIANCE", FIXTURE_AS_OF).symbol == "RELIANCE"
    assert AgentSignal.__module__.startswith("contracts.")
    assert EventType.AGENT_SIGNAL.value == "agent.signal"


def test_zerodha_preserves_instrument_id(repository: CoreRepository) -> None:
    bare = ZerodhaMarketDataProvider.from_env(repository)
    assert bare.available() is False
    with pytest.raises(ZerodhaUnavailable):
        bare.sync_instruments()

    class FakeKite:
        def instruments(self, exchange: str) -> list[dict[str, object]]:
            assert exchange == "NSE"
            return [{"tradingsymbol": "RELIANCE", "instrument_token": 738561}]

        def quote(self, key: str) -> dict[str, object]:
            return {"timestamp": "2024-06-03T10:00:00+00:00", "last_price": "2900", "volume": 10}

    provider = ZerodhaMarketDataProvider(repository, FakeKite())
    assert provider.sync_instruments() == 1
    assert repository.get_by_symbol("RELIANCE").instrument_id == "NSE:RELIANCE"
    assert repository.get_by_symbol("RELIANCE").instrument_token == 738561
    provider.sync_instruments()
    assert repository.get_by_symbol("RELIANCE").instrument_id == "NSE:RELIANCE"


def test_postgres_round_trip_when_configured() -> None:
    url = __import__("os").environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("plain Postgres is not configured")
    repository = CoreRepository(create_schema(url))
    load_seed(repository)
    assert len(repository.members_at(datetime(2024, 6, 3, tzinfo=UTC))) == 50

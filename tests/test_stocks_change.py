"""The stocks list carries the previous close and the day change."""

from decimal import Decimal

from fastapi.testclient import TestClient

from contracts.enums import Timeframe, TradingMode
from contracts.fixtures import FIXTURE_AS_OF, candles_for
from core_api.app import create_app
from core_api.settings import Settings
from core_db.repository import CoreRepository
from core_ingestion.service import MemoryEventPublisher


def test_stocks_include_day_change(repository: CoreRepository) -> None:
    repository.upsert_candles(list(candles_for("RELIANCE")))
    app = create_app(
        Settings(
            database_url="sqlite://",
            redis_url="redis://localhost:6379/0",
            core_api_token="core",
            internal_signal_token="internal",
            max_clock_skew_seconds=5,
            trading_mode=TradingMode.PAPER,
        ),
        repository,
        MemoryEventPublisher(),
    )
    rows = TestClient(app).get("/api/v1/stocks", params={"as_of": FIXTURE_AS_OF.isoformat()}, headers={"Authorization": "Bearer core"}).json()
    row = next(item for item in rows if item["symbol"] == "RELIANCE")
    bars = repository.candles_until("RELIANCE", Timeframe.D1, FIXTURE_AS_OF, last=2)
    assert row["last_price"] == str(bars[-1].close)
    assert row["prev_close"] == str(bars[-2].close)
    expected = ((bars[-1].close / bars[-2].close) - 1) * 100
    assert abs(Decimal(row["change_pct"]) - expected) < Decimal("0.0001")


def test_candles_until_last_keeps_newest_bars_in_order(repository: CoreRepository) -> None:
    repository.upsert_candles(list(candles_for("RELIANCE")))
    every = repository.candles_until("RELIANCE", Timeframe.D1, FIXTURE_AS_OF)
    newest = repository.candles_until("RELIANCE", Timeframe.D1, FIXTURE_AS_OF, last=2)
    assert newest == every[-2:]
    assert repository.latest_candle("RELIANCE", Timeframe.D1) == max(
        repository.stored_candles("RELIANCE", Timeframe.D1), key=lambda bar: bar.end
    )

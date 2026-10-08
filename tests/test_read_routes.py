"""Read routes the dashboard and quant service use. LIVE stays off."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from contracts.enums import TradingMode
from contracts.fixtures import FIXTURE_AS_OF, candles_for, sample_agent_signal
from core_api.app import create_app
from core_api.settings import Settings
from core_db.repository import CoreRepository
from core_ingestion.service import MemoryEventPublisher


def test_features_overview_and_signals_come_from_stored_rows(repository: CoreRepository) -> None:
    repository.upsert_candles(list(candles_for("RELIANCE")))
    signal = sample_agent_signal("RELIANCE")
    assert repository.insert_signal(
        signal.signal_id,
        signal.symbol,
        signal.exchange.value,
        signal.model_dump(mode="json"),
        datetime.now(timezone.utc),
    )
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
    client = TestClient(app)
    headers = {"Authorization": "Bearer core"}
    features = client.get("/api/v1/features/RELIANCE", params={"timeframe": "1d", "as_of": FIXTURE_AS_OF.isoformat()}, headers=headers)
    assert features.status_code == 200
    body = features.json()
    assert body["symbol"] == "RELIANCE"
    assert body["timeframe"] == "1d"
    assert "return_1" in body["features"]
    assert "last_close" in body["features"]
    overview = client.get("/api/v1/market/overview", params={"as_of": FIXTURE_AS_OF.isoformat()}, headers=headers)
    assert overview.status_code == 200
    assert overview.json()["breadth_advancers"] >= 1
    listed = client.get("/api/v1/signals", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["symbol"] == "RELIANCE"
    portfolio = client.get("/api/v1/portfolio", headers=headers)
    assert portfolio.json()["snapshot"] is None
    assert portfolio.json()["equity"] == "1000000"
    assert client.get("/api/v1/features/RELIANCE").status_code == 401

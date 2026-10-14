"""The System page's health check names every pipeline component."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from contracts.enums import TradingMode
from contracts.fixtures import sample_agent_signal
from core_api.app import create_app
from core_api.settings import Settings
from core_db.repository import CoreRepository
from core_ingestion.service import MemoryEventPublisher


def test_health_lists_each_component(repository: CoreRepository) -> None:
    signal = sample_agent_signal("RELIANCE")
    repository.insert_signal(signal.signal_id, signal.symbol, signal.exchange.value, signal.model_dump(mode="json"), datetime.now(timezone.utc))
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
    assert client.get("/api/v1/system/health").status_code == 401
    body = client.get("/api/v1/system/health", headers={"Authorization": "Bearer core"}).json()
    assert body["live_enabled"] is False
    names = [item["component"] for item in body["checks"]]
    for name in ("Core API", "PostgreSQL", "Redis event bus", "Zerodha Kite", "Market-data collector", "Quant agents",
                 "Intelligence agents", "Intelligence service", "Trace recorder", "Paper worker (orchestrator)", "Paper session"):
        assert name in names
    statuses = {item["component"]: item["status"] for item in body["checks"]}
    assert statuses["Core API"] == "ok"
    assert statuses["Paper worker (orchestrator)"] == "idle"
    assert statuses["Intelligence service"] == "down"


def test_decision_chain_joins_risk_and_order(repository: CoreRepository) -> None:
    from datetime import timedelta
    from decimal import Decimal

    from contracts.enums import Horizon
    from contracts.fixtures import FIXTURE_AS_OF, candles_for
    from core_ingestion.service import ingest_signal
    from core_paper import run_paper_cycle

    repository.upsert_candles(list(candles_for("RELIANCE")))
    signal = sample_agent_signal("RELIANCE").model_copy(
        update={"signal_id": "sig-chain", "horizon": Horizon.SWING, "signal": 0.5, "confidence": 0.8,
                "timestamp": FIXTURE_AS_OF, "as_of": FIXTURE_AS_OF, "valid_until": FIXTURE_AS_OF + timedelta(hours=6)}
    )
    ingest_signal(repository, MemoryEventPublisher(), signal, mode=TradingMode.BACKTEST, now=FIXTURE_AS_OF, replay_as_of=FIXTURE_AS_OF, skew_seconds=5)
    repository.open_paper_session(Decimal("1000000"))
    run_paper_cycle(repository, MemoryEventPublisher(), mode=TradingMode.PAPER, starting_cash=Decimal("1000000"), now=FIXTURE_AS_OF, enforce_entry_window=False)
    app = create_app(
        Settings(database_url="sqlite://", redis_url="redis://localhost:6379/0", core_api_token="core",
                 internal_signal_token="internal", max_clock_skew_seconds=5, trading_mode=TradingMode.PAPER),
        repository,
        MemoryEventPublisher(),
    )
    rows = TestClient(app).get("/api/v1/decisions/chain", headers={"Authorization": "Bearer core"}).json()
    assert len(rows) == 1
    assert rows[0]["proposal"]["symbol"] == "RELIANCE"
    assert rows[0]["risk"]["status"] == "APPROVED"
    assert rows[0]["order"]["proposal_id"] == rows[0]["proposal"]["proposal_id"]

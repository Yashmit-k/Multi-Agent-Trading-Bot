"""Active-session reads stay separate from a closed session. In-process only."""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from contracts.schemas.portfolio import PortfolioSnapshot
from contracts.schemas.position import Position
from core_db.seed import load_seed
from test_checkpoint3 import HEADERS, _app

WHEN = datetime(2026, 10, 13, 5, 0, tzinfo=timezone.utc)


def test_active_session_metrics_omit_a_closed_session() -> None:
    app = _app()
    repository = app.state.repository
    load_seed(repository)
    closed = repository.open_paper_session(Decimal("1000000"))
    repository.save_position(
        Position(
            symbol="RELIANCE",
            quantity=1,
            average_price=Decimal("100"),
            market_price=Decimal("100"),
            market_value=Decimal("100"),
            realized_pnl=Decimal("5"),
            unrealized_pnl=Decimal("0"),
            opened_at=WHEN,
            updated_at=WHEN,
        )
    )
    repository.insert_snapshot(
        "closed-session-snapshot",
        PortfolioSnapshot(
            timestamp=WHEN,
            cash=Decimal("999900"),
            equity=Decimal("1000000"),
            market_value=Decimal("100"),
            gross_exposure=Decimal("100"),
            net_exposure=Decimal("100"),
            realized_pnl=Decimal("5"),
            unrealized_pnl=Decimal("0"),
            total_pnl=Decimal("5"),
            drawdown=Decimal("0"),
        ),
    )
    repository.close_paper_session(closed.session_id)
    active = repository.open_paper_session(Decimal("1000000"))
    client = TestClient(app)

    daily = client.get("/api/v1/paper/daily-performance", headers=HEADERS)
    assert daily.status_code == 200
    assert daily.json() == {"status": "unavailable", "reason": "no_daily_equity_history"}

    current = client.get("/api/v1/portfolio", headers=HEADERS)
    assert current.status_code == 200
    body = current.json()
    assert body["session_id"] == active.session_id
    assert body["snapshot"] is None
    assert body["total_pnl"] is None
    assert body["gross_exposure"] is None
    assert client.get("/api/v1/positions", headers=HEADERS).json() == []

    previous = client.get("/api/v1/portfolio", params={"session_id": closed.session_id}, headers=HEADERS)
    assert previous.json()["session_id"] == closed.session_id
    assert previous.json()["snapshot"]["total_pnl"] == "5"
    held = client.get("/api/v1/positions", params={"session_id": closed.session_id}, headers=HEADERS)
    assert [item["symbol"] for item in held.json()] == ["RELIANCE"]

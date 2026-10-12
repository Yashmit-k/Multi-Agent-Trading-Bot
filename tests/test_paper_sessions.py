"""Paper sessions isolate cash, positions, and proposal identity. Storage is SQLite."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from contracts.enums import Exchange, OrderStatus, OrderType, Side, Timeframe, TradingMode
from contracts.fixtures import FIXTURE_AS_OF, candles_for
from contracts.schemas.execution import Execution
from contracts.schemas.order import Order
from contracts.schemas.portfolio import PortfolioSnapshot
from contracts.schemas.position import Position
from core_api.app import create_app
from core_api.settings import Settings
from core_db.models import AuditLogRow, ExecutionRow, OrderRow, PortfolioSnapshotRow, PositionRow, RuntimeFlagRow
from core_db.paper_sessions import (
    LEGACY_ASSESSMENT_AUDIT_ID,
    LEGACY_SESSION_ID,
    ActivePaperSessionError,
    assess_legacy_book,
)
from core_db.repository import CoreRepository
from core_decision import proposal_id_for
from core_ingestion.service import MemoryEventPublisher, ingest_signal
from core_paper import run_paper_cycle
from test_phase4 import _signal, _store

UTC = timezone.utc
CASH = Decimal("1000000")
FILL_AT = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


def test_fresh_session_uses_configured_cash_and_inherits_nothing(repository: CoreRepository) -> None:
    _stage_kotak(repository)
    assert repository.assign_legacy_paper_session(now=FILL_AT) == LEGACY_SESSION_ID
    legacy = repository.active_paper_session()
    assert legacy is not None
    assert legacy.session_id == LEGACY_SESSION_ID
    assert legacy.status == "active"
    assert legacy.starting_cash == Decimal("100000.0000")
    assert legacy.peak_equity == Decimal("100000")
    assert _assessment(repository)["peak_complete"] is False
    assert any("historical peak is incomplete" in item for item in _assessment(repository)["diagnostics"])
    assert repository.list_orders()[0].symbol == "KOTAKBANK"
    assert repository.position_for("KOTAKBANK") is not None
    assert repository.position_for("KOTAKBANK").quantity == 1
    try:
        repository.open_paper_session(CASH)
    except ActivePaperSessionError:
        pass
    else:
        raise AssertionError("a second active session was accepted")
    closed = repository.close_paper_session(LEGACY_SESSION_ID, closed_at=FILL_AT + timedelta(days=1))
    assert closed.status == "closed"
    assert closed.closed_at == FILL_AT + timedelta(days=1)
    opened = repository.open_paper_session(CASH, created_at=FILL_AT + timedelta(days=2))
    assert opened.session_id != LEGACY_SESSION_ID
    assert opened.starting_cash == CASH
    assert repository.list_orders() == []
    assert repository.list_positions() == []
    assert repository.list_executions() == []
    assert repository.cash_balance(CASH) == CASH
    assert repository.latest_snapshot() is None
    assert repository.list_orders(LEGACY_SESSION_ID)[0].symbol == "KOTAKBANK"
    assert repository.position_for("KOTAKBANK", LEGACY_SESSION_ID).quantity == 1
    assert repository.list_executions(LEGACY_SESSION_ID)[0].price == Decimal("418.3500")
    again = repository.assign_legacy_paper_session()
    assert again == LEGACY_SESSION_ID
    assert repository.active_paper_session().session_id == opened.session_id


def test_old_proposal_does_not_block_a_new_session(repository: CoreRepository) -> None:
    repository.upsert_candles(list(candles_for("RELIANCE")))
    _store(repository, _signal(signal_id="sig-session", timestamp=FIXTURE_AS_OF))
    first = repository.open_paper_session(CASH)
    publisher = MemoryEventPublisher()
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=CASH)
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=CASH)
    assert len(repository.list_orders()) == 1
    old_id = proposal_id_for("RELIANCE", repository.list_proposals()[0].horizon, FIXTURE_AS_OF, session_id=first.session_id)
    assert repository.get_proposal(old_id) is not None
    repository.close_paper_session(first.session_id)
    second = repository.open_paper_session(CASH)
    run_paper_cycle(repository, publisher, mode=TradingMode.PAPER, starting_cash=CASH)
    new_id = proposal_id_for("RELIANCE", repository.list_proposals()[0].horizon, FIXTURE_AS_OF, session_id=second.session_id)
    assert new_id != old_id
    assert repository.get_proposal(new_id) is not None
    assert len(repository.list_orders()) == 1
    assert repository.list_orders()[0].proposal_id == new_id
    assert repository.list_orders(first.session_id)[0].proposal_id == old_id


def test_rejected_risk_does_not_change_session_cash(repository: CoreRepository) -> None:
    repository.open_paper_session(Decimal("1"))
    repository.upsert_candles(list(candles_for("RELIANCE")))
    _store(repository, _signal(signal_id="sig-poor", timestamp=FIXTURE_AS_OF))
    run_paper_cycle(repository, MemoryEventPublisher(), mode=TradingMode.PAPER, starting_cash=Decimal("1"))
    assert repository.list_orders() == []
    assert repository.latest_snapshot() is None
    assert repository.cash_balance(Decimal("1")) == Decimal("1")


def test_cycle_without_a_session_does_not_trade(repository: CoreRepository) -> None:
    repository.upsert_candles(list(candles_for("RELIANCE")))
    _store(repository, _signal(signal_id="sig-none", timestamp=FIXTURE_AS_OF))
    assert run_paper_cycle(repository, MemoryEventPublisher(), mode=TradingMode.PAPER, starting_cash=CASH) == 0
    assert repository.list_proposals() == []
    assert repository.list_orders() == []


def test_session_api_identifies_the_book_and_stays_paper(repository: CoreRepository) -> None:
    settings = Settings(
        database_url="sqlite://",
        redis_url="redis://localhost:6379/0",
        core_api_token="core",
        internal_signal_token="internal",
        max_clock_skew_seconds=5,
        trading_mode=TradingMode.PAPER,
        paper_starting_cash=CASH,
    )
    client = TestClient(create_app(settings, repository, MemoryEventPublisher()))
    headers = {"Authorization": "Bearer core"}
    opened = client.post("/api/v1/paper/sessions", headers=headers)
    assert opened.status_code == 200
    body = opened.json()
    assert Decimal(body["starting_cash"]) == CASH
    assert body["status"] == "active"
    assert body["live_enabled"] is False
    assert body["session_id"]
    assert client.post("/api/v1/paper/sessions", headers=headers).status_code == 409
    listed = client.get("/api/v1/paper/sessions", headers=headers).json()
    assert [item["session_id"] for item in listed] == [body["session_id"]]
    detail = client.get(f"/api/v1/paper/sessions/{body['session_id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["orders"] == []
    assert detail.json()["positions"] == []
    status = client.get("/api/v1/paper/status", headers=headers).json()
    assert status["session_id"] == body["session_id"]
    assert Decimal(status["session_starting_cash"]) == CASH
    assert status["live_enabled"] is False
    assert Decimal(status["starting_cash"]) == CASH
    portfolio = client.get("/api/v1/portfolio", headers=headers).json()
    assert portfolio["session_id"] == body["session_id"]
    assert portfolio["snapshot"] is None
    assert Decimal(portfolio["equity"]) == CASH
    assert portfolio["live_enabled"] is False
    closed = client.post(f"/api/v1/paper/sessions/{body['session_id']}/close", headers=headers)
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert client.post(f"/api/v1/paper/sessions/{body['session_id']}/activate", headers=headers).status_code == 409
    assert "open_paper_session" not in Path("services/core/worker/src/core_worker/__main__.py").read_text(encoding="utf-8")
    assert ingest_signal is not None


def test_runtime_peak_is_copied_when_it_matches_the_snapshot(repository: CoreRepository) -> None:
    _stage_kotak(repository)
    _set_peak(repository, Decimal("100000"))
    repository.assign_legacy_paper_session(now=FILL_AT)
    legacy = repository.paper_session(LEGACY_SESSION_ID)
    assert legacy is not None
    assert legacy.status == "active"
    assert legacy.peak_equity == Decimal("100000")
    assessment = _assessment(repository)
    assert assessment["peak_complete"] is True
    assert assessment["peak_source"] == "runtime_flag"
    assert assessment["diagnostics"] == []
    assert _paper_peak(repository) == Decimal("100000")
    repository.note_peak_equity(Decimal("100100"))
    assert repository.paper_session(LEGACY_SESSION_ID).peak_equity == Decimal("100100")
    assert _paper_peak(repository) == Decimal("100000")


def test_invalid_runtime_peak_is_not_treated_as_the_historical_maximum(repository: CoreRepository) -> None:
    _stage_kotak(repository)
    _set_peak(repository, Decimal("50"))
    repository.assign_legacy_paper_session(now=FILL_AT)
    legacy = repository.paper_session(LEGACY_SESSION_ID)
    assert legacy is not None
    assert legacy.peak_equity == Decimal("100000")
    assessment = _assessment(repository)
    assert assessment["peak_complete"] is False
    assert assessment["peak_source"] == "snapshot_equity"
    assert any("historical peak is incomplete" in item for item in assessment["diagnostics"])
    assert _paper_peak(repository) == Decimal("50")


def test_positive_drawdown_without_a_runtime_peak_stays_empty(repository: CoreRepository) -> None:
    _stage_kotak(repository)
    _rewrite_snapshot(repository, drawdown="0.10000000")
    repository.assign_legacy_paper_session(now=FILL_AT)
    legacy = repository.paper_session(LEGACY_SESSION_ID)
    assert legacy is not None
    assert legacy.status == "active"
    assert legacy.starting_cash == Decimal("100000")
    assert legacy.peak_equity is None
    assessment = _assessment(repository)
    assert assessment["peak_complete"] is False
    assert assessment["peak_source"] == "unavailable"
    assert any("left empty" in item for item in assessment["diagnostics"])


def test_inconsistent_legacy_books_stay_inactive(repository: CoreRepository) -> None:
    _stage_kotak(repository)
    _rewrite_snapshot(repository, equity="1")
    repository.assign_legacy_paper_session(now=FILL_AT)
    legacy = repository.paper_session(LEGACY_SESSION_ID)
    assert legacy is not None
    assert legacy.status == "closed"
    assert legacy.starting_cash is None
    assert repository.active_paper_session() is None
    assert repository.position_for("KOTAKBANK", LEGACY_SESSION_ID).quantity == 1
    assert any("equity" in item for item in _assessment(repository)["diagnostics"])


def test_fill_later_than_the_snapshot_is_not_activated(repository: CoreRepository) -> None:
    _stage_kotak(repository)
    later = (FILL_AT + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    with repository._session_factory() as session:
        row = session.get(ExecutionRow, "kotak-fill")
        body = dict(row.payload)
        body["executed_at"] = later
        row.payload = body
        session.commit()
    repository.assign_legacy_paper_session(now=FILL_AT)
    legacy = repository.paper_session(LEGACY_SESSION_ID)
    assert legacy.status == "closed"
    assert legacy.starting_cash is None
    assert any("later than the latest snapshot" in item for item in _assessment(repository)["diagnostics"])


def test_fill_without_an_order_is_not_activated(repository: CoreRepository) -> None:
    _stage_kotak(repository)
    with repository._session_factory() as session:
        session.delete(session.get(OrderRow, "kotak-order"))
        session.commit()
    repository.assign_legacy_paper_session(now=FILL_AT)
    legacy = repository.paper_session(LEGACY_SESSION_ID)
    assert legacy.status == "closed"
    assert legacy.starting_cash is None
    assert any("no matching order" in item for item in _assessment(repository)["diagnostics"])
    assert repository.list_executions(LEGACY_SESSION_ID)[0].price == Decimal("418.3500")


def test_buy_and_sell_reconstruction_uses_price_and_fees_once() -> None:
    moment = datetime(2026, 10, 2, 10, tzinfo=UTC)
    assessment = assess_legacy_book(
        snapshots=[
            {
                "snapshot_id": "book",
                "timestamp": moment,
                "payload": {
                    "timestamp": moment.isoformat().replace("+00:00", "Z"),
                    "cash": "99908.5000",
                    "equity": "100018.5000",
                    "market_value": "110",
                    "gross_exposure": "110",
                    "net_exposure": "110",
                    "realized_pnl": "10",
                    "unrealized_pnl": "10",
                    "total_pnl": "20",
                    "drawdown": "0",
                },
            }
        ],
        orders=[
            {"order_id": "buy", "payload": {"side": "BUY", "quantity": 2, "symbol": "RELIANCE"}},
            {"order_id": "sell", "payload": {"side": "SELL", "quantity": 1, "symbol": "RELIANCE"}},
        ],
        executions=[
            {
                "execution_id": "buy-fill",
                "order_id": "buy",
                "payload": {
                    "order_id": "buy",
                    "symbol": "RELIANCE",
                    "quantity": 2,
                    "price": "100",
                    "fees": "1",
                    "slippage": "0.25",
                    "executed_at": moment.isoformat().replace("+00:00", "Z"),
                },
            },
            {
                "execution_id": "sell-fill",
                "order_id": "sell",
                "payload": {
                    "order_id": "sell",
                    "symbol": "RELIANCE",
                    "quantity": 1,
                    "price": "110",
                    "fees": "0.5",
                    "slippage": "0",
                    "executed_at": moment.isoformat().replace("+00:00", "Z"),
                },
            },
        ],
        positions=[
            {
                "instrument_id": "NSE:RELIANCE",
                "symbol": "RELIANCE",
                "payload": {
                    "symbol": "RELIANCE",
                    "quantity": 1,
                    "average_price": "100",
                    "market_price": "110",
                    "market_value": "110",
                    "realized_pnl": "10",
                    "unrealized_pnl": "10",
                },
            }
        ],
        runtime_peak=Decimal("100018.5"),
    )
    assert assessment.consistent is True
    assert assessment.starting_cash == Decimal("100000")
    assert assessment.peak_equity == Decimal("100018.5")
    assert assessment.peak_complete is True


def _assessment(repository: CoreRepository) -> dict:
    with repository._session_factory() as session:
        row = session.get(AuditLogRow, LEGACY_ASSESSMENT_AUDIT_ID)
        assert row is not None
        return dict(row.payload)


def _paper_peak(repository: CoreRepository) -> Decimal | None:
    with repository._session_factory() as session:
        row = session.get(RuntimeFlagRow, "paper")
        assert row is not None
        return row.peak_equity


def _set_peak(repository: CoreRepository, peak: Decimal) -> None:
    with repository._session_factory() as session:
        session.add(RuntimeFlagRow(flag_id="paper", paper_running=True, peak_equity=peak))
        session.commit()


def _rewrite_snapshot(repository: CoreRepository, **changes: str) -> None:
    with repository._session_factory() as session:
        row = session.get(PortfolioSnapshotRow, "kotak-fill")
        body = dict(row.payload)
        body.update(changes)
        row.payload = body
        session.commit()


def _stage_kotak(repository: CoreRepository) -> None:
    repository.upsert_instrument(symbol="KOTAKBANK", exchange="NSE", trading_symbol="KOTAKBANK")
    order = Order(
        order_id="kotak-order",
        client_order_id="kotak-order",
        proposal_id="kotak-proposal",
        symbol="KOTAKBANK",
        exchange=Exchange.NSE,
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        limit_price=None,
        stop_price=None,
        trading_mode=TradingMode.PAPER,
        status=OrderStatus.FILLED,
        created_at=FILL_AT,
        updated_at=FILL_AT,
        metadata={"reason": "entry"},
    )
    execution = Execution(
        execution_id="kotak-fill",
        order_id="kotak-order",
        symbol="KOTAKBANK",
        quantity=1,
        price=Decimal("418.3500"),
        executed_at=FILL_AT,
        fees=Decimal("0"),
        slippage=Decimal("0"),
        venue="PAPER",
        metadata={"reason": "entry"},
    )
    position = Position(
        symbol="KOTAKBANK",
        quantity=1,
        average_price=Decimal("418.3500"),
        market_price=Decimal("418.3500"),
        market_value=Decimal("418.3500"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        opened_at=FILL_AT,
        updated_at=FILL_AT,
    )
    snapshot = PortfolioSnapshot(
        timestamp=FILL_AT,
        cash=Decimal("99581.6500"),
        equity=Decimal("100000.0000"),
        market_value=Decimal("418.3500"),
        gross_exposure=Decimal("418.3500"),
        net_exposure=Decimal("418.3500"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        total_pnl=Decimal("0"),
        drawdown=Decimal("0"),
    )
    with repository._session_factory() as session:
        session.add(
            OrderRow(
                order_id=order.order_id,
                session_id=None,
                proposal_id=order.proposal_id,
                instrument_id="NSE:KOTAKBANK",
                payload=order.model_dump(mode="json"),
            )
        )
        session.add(
            ExecutionRow(
                execution_id=execution.execution_id,
                session_id=None,
                order_id=execution.order_id,
                instrument_id="NSE:KOTAKBANK",
                payload=execution.model_dump(mode="json"),
            )
        )
        session.add(
            PositionRow(
                position_id="unassigned:NSE:KOTAKBANK",
                session_id=None,
                instrument_id="NSE:KOTAKBANK",
                symbol="KOTAKBANK",
                payload=position.model_dump(mode="json"),
            )
        )
        session.add(
            PortfolioSnapshotRow(
                snapshot_id=execution.execution_id,
                session_id=None,
                timestamp=FILL_AT,
                payload=snapshot.model_dump(mode="json"),
            )
        )
        session.commit()

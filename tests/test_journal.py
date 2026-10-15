"""The trade journal joins agent votes, fusion, risk, order, fill, exit, and P&L for each entry."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from contracts.enums import Exchange, OrderStatus, OrderType, Side, TradingMode
from contracts.fixtures import sample_agent_signal
from contracts.schemas.execution import Execution
from contracts.schemas.order import Order
from core_api.app import _journal
from core_db.repository import CoreRepository
from core_risk import assess
from tests.test_portfolio_risk import _proposal

NOW = datetime(2026, 10, 15, 4, 0, tzinfo=timezone.utc)


def _order(order_id: str, proposal_id: str, side: Side, reason: str, at: datetime) -> Order:
    return Order(order_id=order_id, client_order_id=order_id, proposal_id=proposal_id, symbol="INFY", exchange=Exchange.NSE, side=side,
                 order_type=OrderType.LIMIT, quantity=19, limit_price=Decimal("1000"), stop_price=None, trading_mode=TradingMode.PAPER,
                 status=OrderStatus.FILLED, created_at=at, updated_at=at, metadata={"reason": reason})


def _fill(execution_id: str, order_id: str, price: str, fees: str, at: datetime) -> Execution:
    return Execution(execution_id=execution_id, order_id=order_id, symbol="INFY", quantity=19, price=Decimal(price), executed_at=at,
                     fees=Decimal(fees), slippage=Decimal("0"), venue="PAPER", metadata={})


def test_closed_trade_shows_votes_risk_and_net_pnl(repository: CoreRepository) -> None:
    repository.open_paper_session(Decimal("1000000"))
    signal = sample_agent_signal("INFY").model_copy(update={"signal_id": "sig-journal"})
    repository.insert_signal(signal.signal_id, "INFY", "NSE", signal.model_dump(mode="json"), NOW)
    proposal = _proposal("INFY").model_copy(update={"proposal_id": "p-entry", "supporting_signal_ids": ["sig-journal"]})
    repository.insert_proposal(proposal)
    repository.insert_risk_decision(assess(proposal, mode=TradingMode.PAPER, in_universe=True, cash=Decimal("1000000"), held_quantity=0, timestamp=NOW))
    repository.insert_order(_order("o-entry", "p-entry", Side.BUY, "entry", NOW))
    repository.insert_execution(_fill("e-entry", "o-entry", "1000", "22.50", NOW + timedelta(minutes=5)))
    exit_proposal = _proposal("INFY", side=Side.SELL).model_copy(update={"proposal_id": "p-exit"})
    repository.insert_proposal(exit_proposal)
    repository.insert_order(_order("o-exit", "p-exit", Side.SELL, "take_profit", NOW + timedelta(hours=2)))
    repository.insert_execution(_fill("e-exit", "o-exit", "1040", "35.10", NOW + timedelta(hours=2, minutes=5)))
    trades = _journal(repository, 10)
    assert len(trades) == 1
    trade = trades[0]
    assert trade["status"] == "closed"
    assert trade["votes"][0]["agent_name"] == signal.agent_name.value
    assert trade["risk"]["status"] == "APPROVED" and len(trade["risk"]["checks"]) == 6
    assert trade["exit"]["reason"] == "take_profit"
    assert Decimal(trade["pnl"]) == Decimal("40") * 19 - Decimal("22.50") - Decimal("35.10")


def test_bearish_signal_on_a_held_stock_queues_a_full_sell(repository: CoreRepository) -> None:
    from contracts.enums import Horizon
    from contracts.fixtures import FIXTURE_AS_OF, candles_for
    from contracts.schemas.position import Position
    from core_ingestion.service import MemoryEventPublisher, ingest_signal
    from core_paper import run_paper_cycle

    repository.upsert_candles(list(candles_for("RELIANCE")))
    session = repository.open_paper_session(Decimal("1000000"))
    repository.save_position(Position(symbol="RELIANCE", quantity=7, average_price=Decimal("2900"), market_price=Decimal("2900"),
                                      market_value=Decimal("20300"), realized_pnl=Decimal("0"), unrealized_pnl=Decimal("0"),
                                      opened_at=FIXTURE_AS_OF, updated_at=FIXTURE_AS_OF))
    bearish = sample_agent_signal("RELIANCE").model_copy(update={"signal_id": "sig-bear", "horizon": Horizon.SWING, "signal": -0.9, "confidence": 0.9,
                                                               "timestamp": FIXTURE_AS_OF, "as_of": FIXTURE_AS_OF, "valid_until": FIXTURE_AS_OF + timedelta(hours=6)})
    ingest_signal(repository, MemoryEventPublisher(), bearish, mode=TradingMode.BACKTEST, now=FIXTURE_AS_OF, replay_as_of=FIXTURE_AS_OF, skew_seconds=5)
    run_paper_cycle(repository, MemoryEventPublisher(), mode=TradingMode.PAPER, starting_cash=Decimal("1000000"), now=FIXTURE_AS_OF, enforce_entry_window=False)
    sells = [order for order in repository.list_orders() if order.side == Side.SELL]
    assert len(sells) == 1
    assert sells[0].quantity == 7
    assert sells[0].metadata["reason"] == "signal"
    del session

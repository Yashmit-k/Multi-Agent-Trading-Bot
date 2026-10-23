"""A stock bought again must use its new entry's stop and target, never an earlier closed trade's."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from contracts.enums import Exchange, OrderStatus, OrderType, Side, Timeframe, TradingMode
from contracts.schemas.execution import Execution
from contracts.schemas.market import Candle
from contracts.schemas.order import Order
from contracts.schemas.position import Position
from contracts.schemas.trade_proposal import TradeProposal
from core_db.repository import CoreRepository
from core_ingestion.service import MemoryEventPublisher
from core_paper.cycle import _entry_execution, _monitor_brackets
from core_paper.costs import CostSchedule

UTC = timezone.utc
CASH = Decimal("1000000")
OLD = datetime(2026, 10, 15, 3, 55, tzinfo=UTC)
NEW = datetime(2026, 10, 23, 4, 0, tzinfo=UTC)


def _fill(repository: CoreRepository, execution_id: str, at: datetime, price: str, stop: str, target: str, side: Side = Side.BUY, reason: str = "entry") -> None:
    order_id = f"order-{execution_id}"
    instrument = repository.get_by_symbol("RELIANCE")
    entry = Decimal(price)
    repository.insert_proposal(TradeProposal(proposal_id=f"p-{execution_id}", symbol="RELIANCE", timestamp=at, horizon="SWING", side=side, quantity=16, entry_price=entry,
                                             stop_loss=(entry * Decimal("0.98")).quantize(Decimal("0.01")) if side == Side.BUY else (entry * Decimal("1.02")).quantize(Decimal("0.01")),
                                             take_profit=(entry * Decimal("1.04")).quantize(Decimal("0.01")) if side == Side.BUY else (entry * Decimal("0.96")).quantize(Decimal("0.01")),
                                             strategy_id="paper-fusion", strategy_version="1.0.0", aggregated_signal=0.5, aggregated_confidence=0.5,
                                             supporting_signal_ids=["sig"], metadata={}))
    repository.insert_order(Order(order_id=order_id, client_order_id=order_id, proposal_id=f"p-{execution_id}", symbol="RELIANCE", exchange=Exchange.NSE, side=side,
                                  order_type=OrderType.LIMIT, quantity=16, limit_price=Decimal(price), stop_price=None, trading_mode=TradingMode.PAPER,
                                  status=OrderStatus.FILLED, created_at=at, updated_at=at, metadata={"reason": reason}))
    repository.insert_execution(Execution(execution_id=execution_id, order_id=order_id, symbol="RELIANCE", quantity=16, price=Decimal(price), executed_at=at,
                                          fees=Decimal("8"), slippage=Decimal("0"), venue="PAPER",
                                          metadata={"reason": reason, "stop_loss": stop, "take_profit": target, "decision_end": at.isoformat()}))
    assert instrument is not None


def test_the_newest_entry_is_found_by_time_not_by_hash_order(repository: CoreRepository) -> None:
    repository.open_paper_session(CASH)
    # The NESTLEIND case of 23 Oct 2026: the OLD entry's id sorts last.
    _fill(repository, "ffff-old", OLD, "1377.30", "1355.54", "1438.53")
    _fill(repository, "aaaa-exit", OLD + timedelta(hours=3), "1355.54", "0", "0", side=Side.SELL, reason="stop")
    _fill(repository, "0000-new", NEW, "1188.15", "1164.39", "1235.68")
    assert [item.execution_id for item in repository.list_executions()] == ["ffff-old", "aaaa-exit", "0000-new"]
    assert _entry_execution(repository, "RELIANCE").execution_id == "0000-new"


def test_brackets_never_use_an_entry_from_before_the_position_opened(repository: CoreRepository) -> None:
    repository.open_paper_session(CASH)
    _fill(repository, "only-old", OLD, "1377.30", "1355.54", "1438.53")
    repository.save_position(Position(symbol="RELIANCE", quantity=16, average_price=Decimal("1188.15"), market_price=Decimal("1188"), market_value=Decimal("19008"),
                                      realized_pnl=Decimal("0"), unrealized_pnl=Decimal("0"), opened_at=NEW, updated_at=NEW))
    bar = NEW + timedelta(minutes=5)
    repository.upsert_candles([Candle(symbol="RELIANCE", exchange=Exchange.NSE, timeframe=Timeframe.M5, open=Decimal("1187.7"), high=Decimal("1188.2"),
                                      low=Decimal("1183.3"), close=Decimal("1184.9"), volume=1000, start=bar - timedelta(minutes=5), end=bar)])
    _monitor_brackets(repository, MemoryEventPublisher(), CostSchedule.research(Decimal("2"), Decimal("0")), CASH, TradingMode.PAPER)
    assert [order for order in repository.list_orders() if order.side == Side.SELL and order.metadata.get("reason") == "stop"] == []

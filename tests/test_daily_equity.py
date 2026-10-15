"""End-of-day book: written once after the close, provisional while trading, unavailable with no activity."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from contracts.enums import Exchange, OrderStatus, OrderType, Side, Timeframe, TradingMode
from contracts.schemas.execution import Execution
from contracts.schemas.market import Candle
from contracts.schemas.order import Order
from core_api.app import _daily_performance, create_app
from core_api.settings import Settings
from core_db.repository import CoreRepository
from core_ingestion.service import MemoryEventPublisher
from core_paper.daily import book_for_day, write_daily_if_due
from tests.test_portfolio_risk import _proposal

CASH = Decimal("1000000")
DAY = datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc).date()
FILL = datetime(2026, 10, 15, 4, 0, tzinfo=timezone.utc)  # 09:30 IST
CLOSE = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)  # 15:30 IST


def _buy(repository: CoreRepository, symbol: str, price: str, quantity: int, fees: str) -> None:
    index = symbol
    repository.insert_proposal(_proposal(symbol).model_copy(update={"proposal_id": f"p-{index}"}))
    repository.insert_order(Order(order_id=f"o-{index}", client_order_id=f"o-{index}", proposal_id=f"p-{index}", symbol=symbol, exchange=Exchange.NSE,
                                  side=Side.BUY, order_type=OrderType.LIMIT, quantity=quantity, limit_price=Decimal(price), stop_price=None,
                                  trading_mode=TradingMode.PAPER, status=OrderStatus.FILLED, created_at=FILL, updated_at=FILL, metadata={}))
    repository.insert_execution(Execution(execution_id=f"e-{index}", order_id=f"o-{index}", symbol=symbol, quantity=quantity, price=Decimal(price),
                                          executed_at=FILL, fees=Decimal(fees), slippage=Decimal("0"), venue="PAPER", metadata={}))


def _bar(symbol: str, end: datetime, close: str) -> Candle:
    return Candle(symbol=symbol, exchange=Exchange.NSE, timeframe=Timeframe.M5, open=Decimal(close), high=Decimal(close), low=Decimal(close),
                  close=Decimal(close), volume=10, start=end - timedelta(minutes=5), end=end)


def test_no_activity_is_unavailable_not_zero(repository: CoreRepository) -> None:
    repository.open_paper_session(CASH)
    assert book_for_day(repository, CASH, DAY) is None
    assert _daily_performance(repository, CLOSE)["status"] == "unavailable"


def test_book_marks_holdings_at_the_close_and_splits_pnl(repository: CoreRepository) -> None:
    repository.open_paper_session(CASH)
    _buy(repository, "INFY", "1000", 10, "22.50")
    repository.upsert_candles([_bar("INFY", CLOSE, "1050"), _bar("INFY", CLOSE + timedelta(minutes=5), "999")])  # bar after close ignored
    book = book_for_day(repository, CASH, DAY)
    assert book is not None
    assert Decimal(book["cash"]) == CASH - Decimal("10022.50")
    assert Decimal(book["market_value"]) == Decimal("10500")
    assert Decimal(book["unrealized_pnl"]) == Decimal("500")
    assert Decimal(book["total_pnl"]) == Decimal("477.50")
    assert Decimal(book["realized_pnl"]) == Decimal("-22.50")
    assert book["fills_today"] == 1 and book["complete"] is True


def test_writer_waits_for_the_close_and_writes_once(repository: CoreRepository) -> None:
    session = repository.open_paper_session(CASH)
    _buy(repository, "INFY", "1000", 10, "22.50")
    repository.upsert_candles([_bar("INFY", CLOSE, "1050")])
    assert write_daily_if_due(repository, CLOSE) is False  # before close + 90 s
    assert write_daily_if_due(repository, CLOSE + timedelta(minutes=2)) is True
    assert write_daily_if_due(repository, CLOSE + timedelta(minutes=3)) is False
    rows = repository.list_daily_equity(session.session_id)
    assert len(rows) == 1 and Decimal(rows[0]["day_pnl"]) == Decimal("477.50")


def test_route_returns_provisional_today_then_the_stored_day(repository: CoreRepository) -> None:
    repository.open_paper_session(CASH)
    _buy(repository, "INFY", "1000", 10, "22.50")
    repository.upsert_candles([_bar("INFY", FILL + timedelta(hours=1), "1010"), _bar("INFY", CLOSE, "1050")])
    live = _daily_performance(repository, FILL + timedelta(hours=1, minutes=1))
    assert live["status"] == "available"
    day = live["days"][-1]
    assert day["complete"] is False and day["net_pnl_inr"] == 77.5  # 10 x 10 gain minus 22.50 charges
    write_daily_if_due(repository, CLOSE + timedelta(minutes=2))
    stored = _daily_performance(repository, CLOSE + timedelta(hours=1))["days"]
    assert len(stored) == 1 and stored[0]["complete"] is True and stored[0]["net_pnl_inr"] == 477.5
    assert stored[0]["realized_pnl_inr"] + stored[0]["unrealized_change_inr"] == 477.5

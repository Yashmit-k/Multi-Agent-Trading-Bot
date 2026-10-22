"""Portfolio limits on new BUYs: positions, sector, exposure, per stock, entries per day."""

from datetime import datetime, timezone
from decimal import Decimal

from contracts.enums import Horizon, Side, TradingMode
from contracts.schemas.trade_proposal import TradeProposal
from core_risk import assess
from core_risk.portfolio import PortfolioContext, sector_of

NOW = datetime(2026, 10, 15, 4, 0, tzinfo=timezone.utc)
CASH = Decimal("1000000")


def _proposal(symbol: str = "INFY", side: Side = Side.BUY, price: str = "1000", quantity: int = 19) -> TradeProposal:
    entry = Decimal(price)
    stop, target = (entry * Decimal("0.98"), entry * Decimal("1.04")) if side == Side.BUY else (entry * Decimal("1.02"), entry * Decimal("0.96"))
    return TradeProposal(
        proposal_id=f"p-{symbol}-{side.value}", symbol=symbol, timestamp=NOW, horizon=Horizon.SWING, side=side, quantity=quantity,
        entry_price=entry, stop_loss=stop.quantize(Decimal("0.01")), take_profit=target.quantize(Decimal("0.01")),
        strategy_id="paper-fusion", strategy_version="1.0.0", aggregated_signal=0.3, aggregated_confidence=0.4,
        supporting_signal_ids=["s1"], metadata={},
    )


def _decide(proposal: TradeProposal, portfolio: PortfolioContext | None, held: int = 0):
    return assess(proposal, mode=TradingMode.PAPER, in_universe=True, cash=CASH, held_quantity=held, timestamp=NOW, portfolio=portfolio)


def _failed(decision) -> set[str]:
    return {check.name for check in decision.checks if not check.passed}


def test_empty_book_approves_and_names_all_eleven_checks() -> None:
    decision = _decide(_proposal(), PortfolioContext(starting_cash=CASH))
    assert decision.status.value == "APPROVED"
    assert {check.name for check in decision.checks} >= {"max_open_positions", "sector_concentration", "exposure_cap", "per_stock_cap", "daily_entry_cap"}
    assert len(decision.checks) == 11


def test_eleventh_name_is_rejected() -> None:
    book = {f"S{i}": Decimal("19000") for i in range(10)}
    decision = _decide(_proposal("NTPC"), PortfolioContext(starting_cash=CASH, exposure=book))
    assert decision.status.value == "REJECTED"
    assert "max_open_positions" in _failed(decision)


def test_third_stock_in_a_sector_is_rejected() -> None:
    book = {"TCS": Decimal("19000"), "WIPRO": Decimal("19000")}
    decision = _decide(_proposal("INFY"), PortfolioContext(starting_cash=CASH, exposure=book))
    assert _failed(decision) == {"sector_concentration"}
    other = _decide(_proposal("NTPC"), PortfolioContext(starting_cash=CASH, exposure=book))
    assert other.status.value == "APPROVED"


def test_exposure_cap_is_thirty_percent_of_starting_cash() -> None:
    book = {f"S{i}": Decimal("36000") for i in range(8)}  # 2.88 lakh deployed; +19k = 3.07 lakh > 3 lakh
    decision = _decide(_proposal("NTPC"), PortfolioContext(starting_cash=CASH, exposure=book))
    assert "exposure_cap" in _failed(decision)


def test_per_stock_cap_is_forty_thousand() -> None:
    decision = _decide(_proposal("INFY"), PortfolioContext(starting_cash=CASH, exposure={"INFY": Decimal("25000")}))
    assert _failed(decision) == {"per_stock_cap"}


def test_seventh_entry_of_the_day_is_rejected() -> None:
    decision = _decide(_proposal(), PortfolioContext(starting_cash=CASH, entries_today=6))
    assert _failed(decision) == {"daily_entry_cap"}
    assert "6 entries already today" in (decision.rejection_reason or "")


def test_sells_and_callers_without_a_book_are_unchanged() -> None:
    sell = _decide(_proposal(side=Side.SELL), PortfolioContext(starting_cash=CASH, entries_today=99), held=19)
    assert sell.status.value == "APPROVED" and len(sell.checks) == 6
    legacy = _decide(_proposal(), None)
    assert legacy.status.value == "APPROVED" and len(legacy.checks) == 6


def test_unknown_stocks_are_their_own_sector() -> None:
    assert sector_of("ZOMATO") == "OWN:ZOMATO" and sector_of("INFY") == "NIFTY IT"


def test_every_nifty_constituent_has_a_sector() -> None:
    import csv

    from core_db.seed import SEED_PATH

    with SEED_PATH.open(newline="", encoding="utf-8") as handle:
        symbols = {row["symbol"] for row in csv.DictReader(handle) if row["universe"].strip() == "NIFTY50"}
    assert symbols and sorted(symbol for symbol in symbols if sector_of(symbol).startswith("OWN:")) == []
    assert sector_of("LT") == sector_of("BEL") and sector_of("ULTRACEMCO") == sector_of("GRASIM")


def test_positions_and_portfolio_are_marked_to_the_latest_bar(repository) -> None:
    from datetime import timedelta

    from fastapi.testclient import TestClient

    from contracts.enums import Exchange, Timeframe
    from contracts.schemas.market import Candle
    from contracts.schemas.portfolio import PortfolioSnapshot
    from contracts.schemas.position import Position
    from core_api.app import create_app
    from core_api.settings import Settings
    from core_ingestion.service import MemoryEventPublisher

    repository.open_paper_session(CASH)
    repository.save_position(Position(symbol="INFY", quantity=10, average_price=Decimal("1000"), market_price=Decimal("1000"),
                                      market_value=Decimal("10000"), realized_pnl=Decimal("0"), unrealized_pnl=Decimal("0"),
                                      opened_at=NOW, updated_at=NOW))
    repository.insert_snapshot("s1", PortfolioSnapshot(timestamp=NOW, cash=Decimal("989990"), equity=Decimal("999990"),
                                                       market_value=Decimal("10000"), gross_exposure=Decimal("10000"), net_exposure=Decimal("10000"),
                                                       realized_pnl=Decimal("-10"), unrealized_pnl=Decimal("0"), total_pnl=Decimal("-10"), drawdown=Decimal("0")))
    repository.upsert_candles([Candle(symbol="INFY", exchange=Exchange.NSE, timeframe=Timeframe.M5, open=Decimal("1040"), high=Decimal("1052"),
                                      low=Decimal("1039"), close=Decimal("1050"), volume=100, start=NOW, end=NOW + timedelta(minutes=5))])
    app = create_app(Settings(database_url="sqlite://", redis_url="redis://localhost:6379/0", core_api_token="core",
                              internal_signal_token="internal", max_clock_skew_seconds=5, trading_mode=TradingMode.PAPER),
                     repository, MemoryEventPublisher())
    client = TestClient(app)
    headers = {"Authorization": "Bearer core"}
    position = client.get("/api/v1/positions", headers=headers).json()[0]
    assert Decimal(position["market_price"]) == Decimal("1050")
    assert Decimal(position["unrealized_pnl"]) == Decimal("500")
    portfolio = client.get("/api/v1/portfolio", headers=headers).json()
    # No fills were recorded here, so ledger cash is the starting cash; holdings are marked at 1050.
    assert Decimal(portfolio["equity"]) == CASH + Decimal("10500")
    assert Decimal(portfolio["snapshot"]["cash"]) == CASH
    assert Decimal(portfolio["snapshot"]["unrealized_pnl"]) == Decimal("500")


def test_intraday_entries_are_priced_off_the_five_minute_close(repository) -> None:
    from datetime import timedelta

    from contracts.enums import Exchange, Timeframe
    from contracts.schemas.market import Candle
    from core_paper.execute import INTRADAY_REFERENCE_RULE, _reference
    from core_paper.limits import REFERENCE_RULE

    day_end = NOW - timedelta(hours=20)
    bar_end = NOW
    repository.upsert_candles([
        Candle(symbol="INFY", exchange=Exchange.NSE, timeframe=Timeframe.D1, open=Decimal("1000"), high=Decimal("1010"), low=Decimal("990"),
               close=Decimal("1000"), volume=10, start=day_end - timedelta(hours=6, minutes=15), end=day_end),
        Candle(symbol="INFY", exchange=Exchange.NSE, timeframe=Timeframe.M5, open=Decimal("1019"), high=Decimal("1021"), low=Decimal("1018"),
               close=Decimal("1020"), volume=10, start=bar_end - timedelta(minutes=5), end=bar_end),
    ])
    intraday = _proposal("INFY").model_copy(update={"horizon": Horizon.INTRADAY})
    bar, _, rule = _reference(repository, intraday, NOW)
    assert bar.close == Decimal("1020") and rule == INTRADAY_REFERENCE_RULE
    swing = _proposal("INFY")
    bar, _, rule = _reference(repository, swing, NOW)
    assert bar.close == Decimal("1000") and rule == REFERENCE_RULE



def test_same_bar_fills_are_all_debited_from_cash(repository) -> None:
    """Regression: five buys filled on one 5m bar must all reduce cash (snapshot ties lost two on 15 Oct)."""
    from contracts.enums import Exchange, OrderStatus, OrderType
    from contracts.schemas.execution import Execution
    from contracts.schemas.order import Order

    repository.open_paper_session(CASH)
    expected = CASH
    for index, symbol in enumerate(("INFY", "TCS", "HDFCBANK", "ITC", "NTPC")):
        repository.insert_proposal(_proposal(symbol).model_copy(update={"proposal_id": f"p{index}"}))
        order = Order(order_id=f"o{index}", client_order_id=f"o{index}", proposal_id=f"p{index}", symbol=symbol, exchange=Exchange.NSE,
                      side=Side.BUY, order_type=OrderType.LIMIT, quantity=10, limit_price=Decimal("1000"), stop_price=None,
                      trading_mode=TradingMode.PAPER, status=OrderStatus.FILLED, created_at=NOW, updated_at=NOW, metadata={})
        repository.insert_order(order)
        repository.insert_execution(Execution(execution_id=f"e{index}", order_id=f"o{index}", symbol=symbol, quantity=10, price=Decimal("1000"),
                                              executed_at=NOW, fees=Decimal("22.50"), slippage=Decimal("0"), venue="PAPER", metadata={}))
        expected -= Decimal("10000") + Decimal("22.50")
    assert repository.cash_balance(CASH) == expected


def test_a_morning_order_on_yesterdays_bar_is_stamped_and_counted_today(repository) -> None:
    """The decision bar (yesterday 15:30) assigns the window; the placement time stamps created_at."""
    from datetime import timedelta

    from contracts.enums import Exchange, Timeframe
    from contracts.schemas.market import Candle
    from core_paper.execute import queue_entry

    repository.open_paper_session(CASH)
    bar_end = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)
    placed = datetime(2026, 10, 15, 3, 55, tzinfo=timezone.utc)  # 09:25 IST
    repository.upsert_candles([Candle(symbol="INFY", exchange=Exchange.NSE, timeframe=Timeframe.D1, open=Decimal("1000"), high=Decimal("1010"),
                                      low=Decimal("990"), close=Decimal("1000"), volume=10, start=bar_end - timedelta(hours=6, minutes=15), end=bar_end)])
    proposal = _proposal("INFY").model_copy(update={"proposal_id": "morning", "timestamp": bar_end})
    repository.insert_proposal(proposal)
    order = queue_entry(repository, proposal, bar_end, placed_at=placed)
    assert order is not None and order.created_at == placed
    assert order.metadata["entry_session_date"] == "2026-10-15"
    assert order.metadata["activation_at"] == bar_end.isoformat()
    assert repository.daily_entry_count(placed) == 1
    assert repository.daily_entry_count(bar_end) == 0


def test_target_exit_above_the_buy_cap_is_not_blocked() -> None:
    """A 19,000 buy that reaches +4% is worth about 19,760; a full-size buy at +4% is over 20,000 and must still sell."""
    sell = _proposal("INFY", side=Side.SELL, price="1040", quantity=20)  # 20,800 notional
    decision = _decide(sell, None, held=20)
    assert decision.status.value == "APPROVED"
    buy = _proposal("INFY", price="1040", quantity=20)
    assert "notional_cap" in _failed(_decide(buy, None))

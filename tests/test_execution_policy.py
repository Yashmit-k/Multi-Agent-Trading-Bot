"""CNC limit policy. Storage is SQLite. No worker and no production database."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from contracts.enums import Exchange, Horizon, OrderStatus, OrderType, Side, Timeframe, TradingMode
from contracts.schemas.market import Candle
from contracts.schemas.order import Order
from contracts.schemas.trade_proposal import TradeProposal
from core_api.app import create_app
from core_api.settings import Settings
from core_db.models import AuditLogRow, ChargeLedgerRow, DpChargeRow
from core_db.repository import CoreRepository
from core_paper.charges import ChargeConfigError, EquityChargeSchedule, ZERODHA_EQUITY_RI, delivery_buy, require_schedule
from core_paper.cycle import run_paper_cycle
from core_paper.execute import affordable_quantity, queue_entry, settle_entries
from core_paper.limits import buy_limit, limit_fill_price
from core_paper.operator import OperatorRejected, cancel_order
from core_paper.trading_calendar import (
    CalendarUnverified,
    assign_entry_window,
    expected_bar_starts,
    session_block_reason,
    session_for,
)
from test_phase4 import _signal, _store

UTC = timezone.utc
IST_OFFSET = timedelta(hours=5, minutes=30)
CASH = Decimal("1000000")
DECISION = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)


def test_reference_limit_and_window_rules() -> None:
    assert buy_limit(Decimal("442.00"), Decimal("0.05")) == Decimal("443.10")
    assert buy_limit(Decimal("442.00"), Decimal("0.01")) == Decimal("443.10")
    limit = Decimal("443.10")
    below = _bar(datetime(2026, 10, 13, 3, 50, tzinfo=UTC), open_=Decimal("440"), low=Decimal("439"))
    assert limit_fill_price(limit, below) == Decimal("440")
    exact = _bar(datetime(2026, 10, 13, 3, 50, tzinfo=UTC), open_=limit, low=limit)
    assert limit_fill_price(limit, exact) == limit
    through = _bar(datetime(2026, 10, 13, 3, 50, tzinfo=UTC), open_=Decimal("444.21"), low=Decimal("443.05"))
    assert limit_fill_price(limit, through) == limit
    touch = _bar(datetime(2026, 10, 13, 3, 50, tzinfo=UTC), open_=Decimal("444.21"), low=limit)
    assert limit_fill_price(limit, touch) is None
    missed = _bar(datetime(2026, 10, 13, 3, 50, tzinfo=UTC), open_=Decimal("444.21"), low=Decimal("443.20"))
    assert limit_fill_price(limit, missed) is None
    opening = _bar(datetime(2026, 10, 13, 3, 45, tzinfo=UTC), open_=Decimal("440"), low=Decimal("439"))
    created = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
    window = assign_entry_window(created)
    assert window.session_date.isoformat() == "2026-10-13"
    assert opening.start.astimezone(timezone.utc) not in expected_bar_starts(window, created)
    first = expected_bar_starts(window, created)[0]
    assert first == datetime(2026, 10, 13, 3, 50, tzinfo=UTC)
    late = datetime(2026, 10, 13, 3, 53, tzinfo=UTC)
    late_window = assign_entry_window(late)
    assert expected_bar_starts(late_window, late)[0] == datetime(2026, 10, 13, 3, 55, tzinfo=UTC)
    at_end = datetime(2026, 10, 13, 5, 0, tzinfo=UTC)
    rolled = assign_entry_window(at_end)
    assert rolled.session_date.isoformat() == "2026-10-14"
    assert at_end not in expected_bar_starts(session_for(datetime(2026, 10, 13, tzinfo=UTC).date()), at_end)  # type: ignore[union-attr]


def test_saturday_special_session_and_unpublished_dates() -> None:
    friday_close = datetime(2024, 5, 17, 10, 0, tzinfo=UTC)
    window = assign_entry_window(friday_close)
    assert window.session_date.isoformat() == "2024-05-18"
    assert window.entry_end.isoformat() == "10:00:00"
    assert window.market_close.isoformat() == "10:00:00"
    assert session_block_reason(datetime(2026, 7, 25, tzinfo=UTC).date()) == "mock_or_drill_not_a_cash_session"
    assert session_for(datetime(2026, 7, 25, tzinfo=UTC).date()) is None
    assert session_block_reason(datetime(2026, 11, 8, tzinfo=UTC).date()) == "muhurat_timings_not_published"
    with pytest.raises(CalendarUnverified):
        assign_entry_window(datetime(2026, 12, 31, 5, 0, tzinfo=UTC))


def test_exact_charges_require_provenance_and_delivery_brokerage_is_zero() -> None:
    blank = EquityChargeSchedule(
        version="",
        broker="zerodha",
        account_category="resident_individual",
        exchange="NSE",
        segment="equity",
        effective_from=None,
        effective_to=None,
        accessed_on=None,
        source_urls=(),
        delivery_brokerage=Decimal("0"),
        intraday_brokerage_rate=Decimal("0.0003"),
        intraday_brokerage_cap=Decimal("20"),
        delivery_stt_rate=Decimal("0.001"),
        intraday_stt_rate=Decimal("0.00025"),
        transaction_rate=Decimal("0.0000307"),
        sebi_inr_per_crore=Decimal("10"),
        delivery_stamp_rate=Decimal("0.00015"),
        intraday_stamp_rate=Decimal("0.00003"),
        gst_rate=Decimal("0.18"),
        ipft_inr_per_crore=Decimal("0.01"),
        dp_inr_per_scrip=Decimal("15.34"),
        stt_rounding="nearest_rupee_half_up",
        component_rounding="paise_half_up",
    )
    with pytest.raises(ChargeConfigError):
        require_schedule(blank)
    quote = delivery_buy(Decimal("1000"), ZERODHA_EQUITY_RI)
    assert quote.lines[0] == ("brokerage", "0.00")
    assert ZERODHA_EQUITY_RI.accessed_on.isoformat() == "2026-10-12"
    assert ZERODHA_EQUITY_RI.effective_from is not None
    assert ZERODHA_EQUITY_RI.source_urls


def test_gap_does_not_fill_and_a_later_trade_through_does(repository: CoreRepository) -> None:
    _arm(repository, Decimal("442"))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION)
    order = repository.list_orders()[0]
    assert Decimal(order.metadata["reference_price"]) == Decimal("442.00")
    assert order.limit_price == Decimal("443.10")
    assert order.metadata["product_type"] == "CNC"
    start = datetime(2026, 10, 13, 3, 50, tzinfo=UTC)
    repository.upsert_candles([_bar(start, open_=Decimal("444.21"), low=Decimal("443.10"))])
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=start + timedelta(minutes=5))
    assert repository.list_orders()[0].status == OrderStatus.OPEN
    nxt = start + timedelta(minutes=5)
    repository.upsert_candles([_bar(nxt, open_=Decimal("444.21"), low=Decimal("443.00"))])
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=nxt + timedelta(minutes=5))
    filled = repository.list_orders()[0]
    assert filled.status == OrderStatus.FILLED
    assert repository.list_executions()[0].price == Decimal("443.10")
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=nxt + timedelta(minutes=5))
    assert repository.execution_count() == 1


def test_open_below_limit_fills_at_the_open(repository: CoreRepository) -> None:
    _arm(repository, Decimal("442"))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION)
    start = datetime(2026, 10, 13, 3, 50, tzinfo=UTC)
    repository.upsert_candles([_bar(start, open_=Decimal("440"), low=Decimal("439"))])
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=start + timedelta(minutes=5))
    assert repository.list_executions()[0].price == Decimal("440")


def test_missing_bar_expires_without_data_and_a_complete_miss_expires(repository: CoreRepository) -> None:
    _arm(repository, Decimal("442"))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION)
    expiry = datetime(2026, 10, 13, 5, 0, tzinfo=UTC)
    settle_entries(repository, starting_cash=CASH, now=expiry)
    assert repository.list_orders()[0].status == OrderStatus.EXPIRED_NO_DATA
    assert repository.available_cash(CASH) == CASH


def test_complete_window_without_a_trade_expires(repository: CoreRepository) -> None:
    _arm(repository, Decimal("442"))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION)
    order = repository.list_orders()[0]
    window = assign_entry_window(DECISION)
    bars = []
    for start in expected_bar_starts(window, datetime.fromisoformat(order.metadata["activation_at"])):
        bars.append(_bar(start, open_=Decimal("450"), low=Decimal("446")))
    repository.upsert_candles(bars)
    settle_entries(repository, starting_cash=CASH, now=datetime(2026, 10, 13, 5, 0, tzinfo=UTC))
    expired = repository.list_orders()[0]
    assert expired.status == OrderStatus.EXPIRED
    assert expired.metadata["terminal_reason"] == "limit_not_reached"
    assert repository.available_cash(CASH) == CASH


def test_two_buys_cannot_reserve_the_same_cash(repository: CoreRepository) -> None:
    repository.open_paper_session(Decimal("100000"))
    _daily(repository, "RELIANCE", Decimal("442"))
    _daily(repository, "TCS", Decimal("442"))
    _store(repository, _signal(signal_id="sig-rel", timestamp=DECISION, valid_until=DECISION + timedelta(days=2)))
    _store(repository, _signal(signal_id="sig-tcs", symbol="TCS", timestamp=DECISION, valid_until=DECISION + timedelta(days=2)))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=Decimal("100000"), now=DECISION)
    orders = [item for item in repository.list_orders() if item.status == OrderStatus.OPEN]
    assert len(orders) == 1
    assert repository.available_cash(Decimal("100000")) < Decimal("100000")
    assert repository.cash_balance(Decimal("100000")) == Decimal("100000")


def test_quantity_respects_cap_after_fees() -> None:
    limit = Decimal("443.10")
    quantity = affordable_quantity(Decimal("1000000"), limit, ZERODHA_EQUITY_RI)
    notional = limit * quantity
    fees = delivery_buy(notional, ZERODHA_EQUITY_RI, ceiling=True).total
    assert notional + fees <= Decimal("100000")
    assert affordable_quantity(Decimal("10"), Decimal("100"), ZERODHA_EQUITY_RI) == 0


def test_restart_does_not_double_fill(repository: CoreRepository) -> None:
    _arm(repository, Decimal("442"))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION)
    first = datetime(2026, 10, 13, 3, 50, tzinfo=UTC)
    repository.upsert_candles([_bar(first, open_=Decimal("450"), low=Decimal("446"))])
    settle_entries(repository, starting_cash=CASH, now=first + timedelta(minutes=5))
    second = first + timedelta(minutes=5)
    repository.upsert_candles([_bar(second, open_=Decimal("440"), low=Decimal("439"))])
    settle_entries(repository, starting_cash=CASH, now=second + timedelta(minutes=5))
    settle_entries(repository, starting_cash=CASH, now=second + timedelta(minutes=5))
    assert repository.execution_count() == 1
    assert repository.list_executions()[0].price == Decimal("440")


def test_same_day_reclass_and_single_dp_charge(repository: CoreRepository) -> None:
    _arm(repository, Decimal("100"))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION)
    start = datetime(2026, 10, 13, 3, 50, tzinfo=UTC)
    repository.upsert_candles([_bar(start, open_=Decimal("100"), low=Decimal("99"))])
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=start + timedelta(minutes=5))
    buy = repository.list_executions()[0]
    before = buy.fees
    position = repository.position_for("RELIANCE")
    assert position is not None
    nxt = start + timedelta(minutes=5)
    repository.upsert_candles([_bar(nxt, open_=Decimal("101"), low=Decimal("100"))])
    _sell(repository, position.quantity, nxt, Decimal("101"))
    from core_paper.execute import settle_sell

    sell = [item for item in repository.list_orders() if item.side == Side.SELL][0]
    settle_sell(repository, sell, starting_cash=CASH, now=nxt + timedelta(minutes=5))
    revised = [item for item in repository.list_executions() if item.order_id == buy.order_id][0]
    assert revised.fees != before
    assert revised.metadata["reclassified_to"] == "same_day_buy_reclass"
    cash_after = repository.cash_balance(CASH)
    settle_sell(repository, repository.list_orders()[-1], starting_cash=CASH, now=start + timedelta(minutes=10))
    assert repository.cash_balance(CASH) == cash_after
    assert repository.position_for("RELIANCE") is None
    with repository._session_factory() as session:
        dp_rows = list(session.scalars(__import__("sqlalchemy").select(DpChargeRow)))
        reclass = list(session.scalars(__import__("sqlalchemy").select(ChargeLedgerRow).where(ChargeLedgerRow.kind == "reclass")))
    assert len(dp_rows) == 1
    assert dp_rows[0].amount == Decimal("15.34")
    assert len(reclass) == 1


def test_second_sell_does_not_charge_dp_again(repository: CoreRepository) -> None:
    _arm(repository, Decimal("100"))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION)
    start = datetime(2026, 10, 13, 3, 50, tzinfo=UTC)
    repository.upsert_candles([_bar(start, open_=Decimal("100"), low=Decimal("99"))])
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=start + timedelta(minutes=5))
    held = repository.position_for("RELIANCE").quantity
    later = datetime(2026, 10, 14, 3, 50, tzinfo=UTC)
    repository.upsert_candles(
        [
            _bar(later, open_=Decimal("101"), low=Decimal("100")),
            _bar(later + timedelta(minutes=5), open_=Decimal("101"), low=Decimal("100")),
        ]
    )
    _sell(repository, 1, later, Decimal("101"), name="sell-a")
    _sell(repository, 1, later + timedelta(minutes=5), Decimal("101"), name="sell-b")
    from core_paper.execute import settle_sell

    orders = {item.metadata["reason"]: item for item in repository.list_orders() if item.side == Side.SELL}
    settle_sell(repository, orders["sell-a"], starting_cash=CASH, now=later + timedelta(minutes=10))
    settle_sell(repository, orders["sell-b"], starting_cash=CASH, now=later + timedelta(minutes=10))
    sells = [item for item in repository.list_executions() if item.metadata.get("reason") != "entry"]
    assert len(sells) == 2
    assert sum(Decimal(str(dict(item.metadata).get("fees", item.fees))) for item in sells) > 0
    with repository._session_factory() as session:
        rows = list(session.scalars(__import__("sqlalchemy").select(DpChargeRow)))
    assert len(rows) == 1
    assert repository.held_quantity("RELIANCE") == held - 2


def test_legacy_open_market_order_is_not_filled(repository: CoreRepository) -> None:
    session = repository.open_paper_session(CASH)
    _daily(repository, "KOTAKBANK", Decimal("442"))
    proposal = _proposal("KOTAKBANK", DECISION)
    repository.insert_proposal(proposal)
    order = Order(
        order_id="legacy-kotak",
        client_order_id="legacy-kotak",
        proposal_id=proposal.proposal_id,
        symbol="KOTAKBANK",
        exchange=Exchange.NSE,
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=226,
        limit_price=None,
        stop_price=None,
        trading_mode=TradingMode.PAPER,
        status=OrderStatus.OPEN,
        created_at=DECISION,
        updated_at=DECISION,
        metadata={"reason": "entry", "fill_at": "next_open", "decision_end": DECISION.isoformat()},
    )
    repository.insert_order(order)
    before = order.model_dump(mode="json")
    start = datetime(2026, 10, 13, 3, 50, tzinfo=UTC)
    repository.upsert_candles([_bar(start, open_=Decimal("400"), low=Decimal("399"), symbol="KOTAKBANK")])
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=start + timedelta(hours=6))
    after = repository.list_orders(session.session_id)
    legacy = [item for item in after if item.order_id == "legacy-kotak"][0]
    assert legacy.model_dump(mode="json") == before
    assert legacy.status == OrderStatus.OPEN
    assert repository.list_executions() == []
    from core_paper.execute import legacy_review_required, settle_entries

    assert legacy_review_required(legacy) is True
    assert settle_entries(repository, starting_cash=CASH, now=start + timedelta(hours=6)) == ["legacy-kotak"]
    assert repository.list_orders(session.session_id)[0].model_dump(mode="json") == before


def test_partial_same_day_sell_uses_the_whole_buy_order_for_brokerage() -> None:
    from core_paper.charges import intraday_brokerage, reclassified_buy

    quote = reclassified_buy(Decimal("100"), 10, 4, ZERODHA_EQUITY_RI)
    whole_order = intraday_brokerage(Decimal("1000"), ZERODHA_EQUITY_RI)
    four_shares = intraday_brokerage(Decimal("400"), ZERODHA_EQUITY_RI)
    assert quote.lines[0] == ("brokerage", f"{whole_order:.2f}")
    assert whole_order != four_shares


def test_rejected_fill_commit_does_not_move_peak(repository: CoreRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    _arm(repository, Decimal("442"))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION)
    order = repository.list_orders()[0]
    start = datetime(2026, 10, 13, 3, 50, tzinfo=UTC)
    repository.upsert_candles([_bar(start, open_=Decimal("440"), low=Decimal("439"))])
    monkeypatch.setattr(repository, "commit_policy_transition", lambda *args, **kwargs: False)
    from core_paper.execute import _fill_buy

    assert _fill_buy(repository, order, _bar(start, open_=Decimal("440"), low=Decimal("439")), Decimal("440"), CASH, ZERODHA_EQUITY_RI, "bar", []) is False
    assert repository.active_paper_session().peak_equity is None
    assert repository.execution_count() == 0
    assert repository.list_orders()[0].status == OrderStatus.OPEN


def test_cancel_releases_once_and_conflict_does_not_change_the_order(repository: CoreRepository) -> None:
    book = _arm(repository, Decimal("442"))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION)
    order = repository.list_orders()[0]
    reserved = repository.available_cash(CASH)
    assert reserved < CASH
    with pytest.raises(OperatorRejected):
        cancel_order(
            repository,
            session_id=book.session_id,
            order_id=order.order_id,
            operator_id="diva",
            reason="wrong status",
            expected_status="FILLED",
        )
    assert repository.list_orders()[0].status == OrderStatus.OPEN
    result = cancel_order(
        repository,
        session_id=book.session_id,
        order_id=order.order_id,
        operator_id="diva",
        reason="superseded policy",
        expected_status="OPEN",
    )
    assert result["status"] == "CANCELLED"
    assert repository.available_cash(CASH) == CASH
    again = repository.available_cash(CASH)
    with pytest.raises(OperatorRejected):
        cancel_order(
            repository,
            session_id=book.session_id,
            order_id=order.order_id,
            operator_id="diva",
            reason="again",
            expected_status="OPEN",
        )
    assert repository.available_cash(CASH) == again
    with repository._session_factory() as session:
        audits = list(session.scalars(__import__("sqlalchemy").select(AuditLogRow)))
    assert any(row.action == "paper_order_cancel" for row in audits)


def test_cancel_route_is_paper_only(repository: CoreRepository) -> None:
    book = _arm(repository, Decimal("442"))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION)
    order = repository.list_orders()[0]
    client = TestClient(
        create_app(
            Settings(
                database_url="sqlite://",
                redis_url="redis://localhost:6379/0",
                core_api_token="core",
                internal_signal_token="internal",
                max_clock_skew_seconds=5,
                trading_mode=TradingMode.PAPER,
            ),
            repository,
            _sink(),
        )
    )
    response = client.post(
        f"/api/v1/paper/sessions/{book.session_id}/orders/{order.order_id}/cancel",
        headers={"Authorization": "Bearer core"},
        json={"operator_id": "diva", "reason": "operator cancel", "expected_status": "OPEN"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert repository.list_orders()[0].status == OrderStatus.CANCELLED


def _arm(repository: CoreRepository, close: Decimal):
    repository.open_paper_session(CASH)
    _daily(repository, "RELIANCE", close)
    _store(repository, _signal(signal_id="sig-policy", timestamp=DECISION, valid_until=DECISION + timedelta(days=2)))
    return repository.active_paper_session()


def _daily(repository: CoreRepository, symbol: str, close: Decimal) -> None:
    repository.upsert_instrument(symbol=symbol, exchange="NSE", trading_symbol=symbol)
    repository.upsert_candles(
        [
            Candle(
                symbol=symbol,
                exchange=Exchange.NSE,
                timeframe=Timeframe.D1,
                open=close - Decimal("1"),
                high=close + Decimal("1"),
                low=close - Decimal("2"),
                close=close,
                volume=1000,
                start=DECISION - timedelta(hours=6),
                end=DECISION,
            )
        ]
    )


def _bar(start: datetime, *, open_: Decimal, low: Decimal, symbol: str = "RELIANCE") -> Candle:
    return Candle(
        symbol=symbol,
        exchange=Exchange.NSE,
        timeframe=Timeframe.M5,
        open=open_,
        high=max(open_, low) + Decimal("1"),
        low=low,
        close=open_,
        volume=100,
        start=start,
        end=start + timedelta(minutes=5),
    )


def _proposal(symbol: str, moment: datetime) -> TradeProposal:
    return TradeProposal(
        proposal_id=f"proposal-{symbol}",
        symbol=symbol,
        timestamp=moment,
        horizon=Horizon.SWING,
        side=Side.BUY,
        quantity=1,
        entry_price=Decimal("442"),
        stop_loss=Decimal("430"),
        take_profit=Decimal("460"),
        strategy_id="paper-fusion",
        strategy_version="1.0.0",
        aggregated_signal=1,
        aggregated_confidence=1,
        supporting_signal_ids=["legacy"],
        metadata={},
    )


def _sell(repository: CoreRepository, quantity: int, moment: datetime, price: Decimal, name: str = "sell-round") -> None:
    from core_paper.cycle import _queue

    proposal = TradeProposal(
        proposal_id=name,
        symbol="RELIANCE",
        timestamp=moment,
        horizon=Horizon.SWING,
        side=Side.SELL,
        quantity=quantity,
        entry_price=price,
        stop_loss=price + Decimal("1"),
        take_profit=price - Decimal("1"),
        strategy_id="paper-fusion",
        strategy_version="1.0.0",
        aggregated_signal=-1,
        aggregated_confidence=1,
        supporting_signal_ids=[name],
        metadata={"reason": name},
    )
    repository.insert_proposal(proposal)
    _queue(repository, proposal, moment, reason=name, fill_at="next_open")


class _Publisher:
    def publish(self, channel: str, payload: str) -> None:
        return None


def _sink() -> _Publisher:
    return _Publisher()

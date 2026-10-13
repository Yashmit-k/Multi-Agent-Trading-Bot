"""₹20,000 per-order notional. Fees sit on top. No worker and no production database."""

from datetime import timedelta
from decimal import Decimal

import pytest

from contracts.enums import OrderStatus, RiskStatus, Side, TradingMode
from core_db.repository import CoreRepository
from core_paper.charges import ZERODHA_EQUITY_RI, delivery_buy, reservation_buy
from core_paper.cycle import run_paper_cycle
from core_paper.execute import MAX_NOTIONAL, affordable_quantity, queue_entry
from core_paper.limits import buy_limit
from core_risk import assess
from test_execution_policy import CASH, DECISION, _arm, _daily, _proposal, _sink

CAP = Decimal("20000")


def test_constant_is_twenty_thousand() -> None:
    assert MAX_NOTIONAL == CAP


def test_quantity_bounds_and_rounding() -> None:
    cash = Decimal("1000000")
    at_cap = affordable_quantity(cash, Decimal("100"), ZERODHA_EQUITY_RI)
    assert at_cap == 200
    assert Decimal("100") * at_cap == CAP
    below = affordable_quantity(cash, Decimal("19999.99"), ZERODHA_EQUITY_RI)
    assert below == 1
    assert Decimal("19999.99") * below < CAP
    exact = affordable_quantity(cash, CAP, ZERODHA_EQUITY_RI)
    assert exact == 1
    assert CAP * exact == CAP
    above = affordable_quantity(cash, Decimal("20000.01"), ZERODHA_EQUITY_RI)
    assert above == 0
    rounded = affordable_quantity(cash, Decimal("100.01"), ZERODHA_EQUITY_RI)
    assert Decimal("100.01") * rounded <= CAP
    assert Decimal("100.01") * (rounded + 1) > CAP


def test_fees_are_reserved_above_the_notional_cap() -> None:
    limit = Decimal("100")
    quantity = affordable_quantity(Decimal("1000000"), limit, ZERODHA_EQUITY_RI)
    notional = limit * quantity
    fees = delivery_buy(notional, ZERODHA_EQUITY_RI, ceiling=True).total
    assert fees > 0
    assert reservation_buy(notional, ZERODHA_EQUITY_RI) == notional + fees
    tight = affordable_quantity(notional, limit, ZERODHA_EQUITY_RI)
    assert tight < quantity
    tight_notional = limit * tight
    assert tight_notional + delivery_buy(tight_notional, ZERODHA_EQUITY_RI, ceiling=True).total <= notional
    covered = affordable_quantity(notional + fees, limit, ZERODHA_EQUITY_RI)
    assert covered == quantity


def test_a_larger_cap_or_missing_schedule_cannot_raise_the_limit() -> None:
    assert affordable_quantity(Decimal("1000000"), Decimal("100"), ZERODHA_EQUITY_RI, Decimal("100000")) == 200
    with pytest.raises(Exception):
        affordable_quantity(Decimal("1000000"), Decimal("100"), None, Decimal("100000"))


def test_queue_entry_persists_the_limit_price_times_quantity(repository: CoreRepository) -> None:
    repository.open_paper_session(CASH)
    _daily(repository, "RELIANCE", Decimal("99.76"))
    proposal = _proposal("RELIANCE", DECISION).model_copy(update={"quantity": 100000, "entry_price": Decimal("99.76")})
    repository.insert_proposal(proposal)
    order = queue_entry(repository, proposal, DECISION, schedule=ZERODHA_EQUITY_RI, cap=Decimal("100000"))
    assert order is not None
    assert order.status == OrderStatus.OPEN
    assert order.limit_price is not None
    notional = order.limit_price * order.quantity
    assert notional <= CAP
    assert order.limit_price * (order.quantity + 1) > CAP
    reserved = Decimal(order.metadata["reserved_amount"])
    assert reserved == reservation_buy(notional, ZERODHA_EQUITY_RI)
    assert reserved > notional


def test_missing_schedule_rejects_before_an_open_order(repository: CoreRepository) -> None:
    repository.open_paper_session(CASH)
    _daily(repository, "RELIANCE", Decimal("99.76"))
    proposal = _proposal("RELIANCE", DECISION).model_copy(update={"quantity": 100000})
    repository.insert_proposal(proposal)
    order = queue_entry(repository, proposal, DECISION, schedule=None, cap=Decimal("100000"))
    assert order is not None
    assert order.status == OrderStatus.REJECTED
    assert order.metadata["reason"] == "charge_config_missing"
    assert repository.open_reservation_total() == 0


def test_cycle_and_replace_paths_use_the_same_cap(repository: CoreRepository) -> None:
    _arm(repository, Decimal("99.76"))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION, enforce_entry_window=False, schedule=None)
    opened = [item for item in repository.list_orders() if item.status == OrderStatus.OPEN]
    assert len(opened) == 1
    first = opened[0]
    assert first.limit_price is not None
    assert first.limit_price * first.quantity <= CAP
    from core_paper.operator import replace_order

    fresh = DECISION + timedelta(days=1)
    _daily(repository, "RELIANCE", Decimal("99.76"))
    replaced = replace_order(
        repository,
        session_id=repository.active_paper_session().session_id,  # type: ignore[union-attr]
        order_id=first.order_id,
        operator_id="tester",
        reason="resize",
        expected_status="OPEN",
        decision_at=fresh,
        now=fresh,
    )
    assert replaced["status"] == "CANCELLED" or replaced["order_id"] == first.order_id
    live = [item for item in repository.list_orders() if item.status == OrderStatus.OPEN and item.side == Side.BUY]
    assert live
    for item in live:
        assert item.limit_price is not None
        assert item.limit_price * item.quantity <= CAP


def test_risk_notional_boundary() -> None:
    under = _proposal("RELIANCE", DECISION).model_copy(
        update={"entry_price": CAP, "quantity": 1, "stop_loss": Decimal("19000"), "take_profit": Decimal("21000")}
    )
    over = under.model_copy(update={"entry_price": Decimal("20000.01"), "stop_loss": Decimal("19000"), "take_profit": Decimal("21001")})
    approved = assess(under, mode=TradingMode.PAPER, in_universe=True, cash=CASH, held_quantity=0, timestamp=DECISION)
    rejected = assess(over, mode=TradingMode.PAPER, in_universe=True, cash=CASH, held_quantity=0, timestamp=DECISION)
    assert approved.status == RiskStatus.APPROVED
    assert rejected.status == RiskStatus.REJECTED
    assert any(check.name == "notional_cap" and not check.passed for check in rejected.checks)


def test_buy_limit_used_by_the_cycle_is_the_priced_cap(repository: CoreRepository) -> None:
    _arm(repository, Decimal("99.76"))
    run_paper_cycle(repository, _sink(), mode=TradingMode.PAPER, starting_cash=CASH, now=DECISION, enforce_entry_window=False)
    order = repository.list_orders()[0]
    assert order.limit_price == buy_limit(Decimal("99.76"), Decimal("0.05"))
    assert order.limit_price * order.quantity == CAP

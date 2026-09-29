"""Order and risk decision constraints."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from contracts.enums import Exchange, OrderStatus, OrderType, RiskStatus, Side, TradingMode
from contracts.schemas.order import Order
from contracts.schemas.risk_decision import RiskCheck, RiskDecision

NOW = datetime(2024, 6, 3, 10, 0, tzinfo=timezone.utc)


def _order(**overrides: object) -> Order:
    data: dict[str, object] = {
        "order_id": "ord-1",
        "client_order_id": "cli-1",
        "proposal_id": "prop-1",
        "symbol": "TCS",
        "exchange": Exchange.NSE,
        "side": Side.BUY,
        "order_type": OrderType.MARKET,
        "quantity": 10,
        "limit_price": None,
        "stop_price": None,
        "trading_mode": TradingMode.PAPER,
        "status": OrderStatus.CREATED,
        "created_at": NOW,
        "updated_at": NOW,
        "metadata": {},
    }
    data.update(overrides)
    return Order.model_validate(data)


def _decision(**overrides: object) -> RiskDecision:
    data: dict[str, object] = {
        "risk_decision_id": "risk-1",
        "proposal_id": "prop-1",
        "timestamp": NOW,
        "status": RiskStatus.APPROVED,
        "risk_version": "1.0.0",
        "checks": [RiskCheck(name="max_position", passed=True, detail="within limit")],
        "rejection_reason": None,
        "approved_quantity": 10,
        "approved_price": Decimal("3850.00"),
        "metadata": {},
    }
    data.update(overrides)
    return RiskDecision.model_validate(data)


def test_valid_order_and_risk_decision() -> None:
    assert _order().status == OrderStatus.CREATED
    assert _decision().status == RiskStatus.APPROVED


def test_invalid_order_state_fails() -> None:
    with pytest.raises(ValidationError):
        _order(status="PENDING")


def test_invalid_risk_decision_fails() -> None:
    with pytest.raises(ValidationError):
        _decision(status="MAYBE")
    with pytest.raises(ValidationError):
        _decision(status=RiskStatus.APPROVED, rejection_reason="nope")
    with pytest.raises(ValidationError):
        _decision(
            status=RiskStatus.REJECTED,
            rejection_reason=None,
            approved_quantity=5,
            approved_price=Decimal("3850.00"),
        )


def test_rejected_risk_decision_succeeds() -> None:
    decision = _decision(
        status=RiskStatus.REJECTED,
        rejection_reason="position limit",
        approved_quantity=0,
        approved_price=None,
        checks=[RiskCheck(name="max_position", passed=False, detail="over limit")],
    )
    assert decision.status == RiskStatus.REJECTED
    assert decision.approved_quantity == 0

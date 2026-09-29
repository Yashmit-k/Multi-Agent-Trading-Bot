"""Canonical order. A proposal becomes an order only after risk approval."""

from decimal import Decimal
from typing import Self

from pydantic import AwareDatetime, model_validator

from contracts.enums import Exchange, OrderStatus, OrderType, Side, TradingMode
from contracts.schemas.common import ContractModel, JsonObject, NonEmptyStr, PositiveInt, Symbol


class Order(ContractModel):
    """Broker-facing order state. Prices that do not apply to the type are null."""

    order_id: NonEmptyStr
    client_order_id: NonEmptyStr
    proposal_id: NonEmptyStr
    symbol: Symbol
    exchange: Exchange
    side: Side
    order_type: OrderType
    quantity: PositiveInt
    limit_price: Decimal | None
    stop_price: Decimal | None
    trading_mode: TradingMode
    status: OrderStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime
    metadata: JsonObject

    @model_validator(mode="after")
    def _price_and_time_rules(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        limit_price = self.limit_price
        stop_price = self.stop_price
        if self.order_type == OrderType.MARKET:
            if limit_price is not None or stop_price is not None:
                raise ValueError("MARKET orders cannot include limit_price or stop_price")
        elif self.order_type == OrderType.LIMIT:
            if limit_price is None or limit_price <= 0 or stop_price is not None:
                raise ValueError("LIMIT orders require a positive limit_price and no stop_price")
        elif self.order_type == OrderType.STOP_LOSS:
            if limit_price is None or limit_price <= 0 or stop_price is None or stop_price <= 0:
                raise ValueError("STOP_LOSS orders require positive limit_price and stop_price")
        elif stop_price is None or stop_price <= 0 or limit_price is not None:
            raise ValueError("STOP_LOSS_MARKET orders require a positive stop_price and no limit_price")
        return self

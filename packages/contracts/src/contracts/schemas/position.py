"""Net position in one symbol. Quantity may be negative for an intraday short."""

from typing import Self

from pydantic import AwareDatetime, model_validator

from contracts.schemas.common import ContractModel, PositiveDecimal, Symbol
from decimal import Decimal


class Position(ContractModel):
    """Holdings and pnl for one symbol."""

    symbol: Symbol
    quantity: int
    average_price: PositiveDecimal
    market_price: PositiveDecimal
    market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    opened_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def _updated_after_open(self) -> Self:
        if self.updated_at < self.opened_at:
            raise ValueError("updated_at cannot precede opened_at")
        return self

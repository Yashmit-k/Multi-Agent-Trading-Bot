"""A fill against an order."""

from pydantic import AwareDatetime

from contracts.schemas.common import (
    ContractModel,
    JsonObject,
    NonEmptyStr,
    NonNegativeDecimal,
    PositiveDecimal,
    PositiveInt,
    Symbol,
)


class Execution(ContractModel):
    """One fill. Fees and slippage are non-negative."""

    execution_id: NonEmptyStr
    order_id: NonEmptyStr
    symbol: Symbol
    quantity: PositiveInt
    price: PositiveDecimal
    executed_at: AwareDatetime
    fees: NonNegativeDecimal
    slippage: NonNegativeDecimal
    venue: NonEmptyStr
    metadata: JsonObject

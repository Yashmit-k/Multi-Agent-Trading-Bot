"""A proposed trade. Risk must approve it before any order exists."""

from pydantic import AwareDatetime, Field

from contracts.enums import Horizon, Side
from contracts.schemas.common import (
    ContractModel,
    JsonObject,
    NonEmptyStr,
    PositiveDecimal,
    PositiveInt,
    Score,
    Symbol,
    UnitFloat,
)


class TradeProposal(ContractModel):
    """An intent to trade. This is not an order and cannot be sent to a broker."""

    proposal_id: NonEmptyStr
    symbol: Symbol
    timestamp: AwareDatetime
    horizon: Horizon
    side: Side
    quantity: PositiveInt
    entry_price: PositiveDecimal
    stop_loss: PositiveDecimal
    take_profit: PositiveDecimal
    strategy_id: NonEmptyStr
    strategy_version: NonEmptyStr
    aggregated_signal: Score
    aggregated_confidence: UnitFloat
    supporting_signal_ids: list[NonEmptyStr] = Field(min_length=1)
    metadata: JsonObject

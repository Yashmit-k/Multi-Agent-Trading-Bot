"""Point-in-time fundamental observation."""

from decimal import Decimal
from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from contracts.schemas.common import ContractModel, JsonObject, NonEmptyStr, Symbol


class FundamentalDataPoint(ContractModel):
    """A reported metric that becomes usable at available_at, not announced_at."""

    symbol: Symbol
    metric: NonEmptyStr
    value: Decimal
    unit: NonEmptyStr
    period: NonEmptyStr
    announced_at: AwareDatetime
    available_at: AwareDatetime = Field(
        description="First time a backtest may observe this point. Require available_at <= as_of."
    )
    source: NonEmptyStr
    source_id: NonEmptyStr
    metadata: JsonObject

    @model_validator(mode="after")
    def _availability_follows_announcement(self) -> Self:
        if self.available_at < self.announced_at:
            raise ValueError("available_at cannot precede announced_at")
        return self

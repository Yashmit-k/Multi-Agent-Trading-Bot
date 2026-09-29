"""News interpretation produced from one article."""

from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from contracts.enums import AgentName, Horizon
from contracts.schemas.common import (
    ContractModel,
    JsonObject,
    NonEmptyStr,
    ReasonCode,
    Score,
    Symbol,
    UnitFloat,
)


class NewsSignal(ContractModel):
    """Sentiment and impact for one symbol, derived from one article."""

    signal_id: NonEmptyStr
    article_id: NonEmptyStr
    symbol: Symbol
    timestamp: AwareDatetime
    as_of: AwareDatetime
    agent_name: AgentName
    agent_version: NonEmptyStr
    sentiment: Score
    impact: UnitFloat
    confidence: UnitFloat
    event_type: ReasonCode
    horizon: Horizon
    reason_codes: list[ReasonCode] = Field(min_length=1)
    metadata: JsonObject

    @model_validator(mode="after")
    def _check_times(self) -> Self:
        if self.as_of > self.timestamp:
            raise ValueError("as_of cannot be after timestamp")
        return self

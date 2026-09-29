"""Authoritative agent signal."""

from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from contracts.enums import AgentName, Exchange, Horizon
from contracts.schemas.common import (
    ContractModel,
    Features,
    JsonObject,
    NonEmptyStr,
    ReasonCode,
    Score,
    Symbol,
    UnitFloat,
)


class AgentSignal(ContractModel):
    """A directional view from one agent. It is not an order."""

    signal_id: NonEmptyStr
    symbol: Symbol
    exchange: Exchange
    agent_name: AgentName
    agent_version: NonEmptyStr
    timestamp: AwareDatetime
    as_of: AwareDatetime
    horizon: Horizon
    signal: Score = Field(description="Directional score in [-1, 1].")
    confidence: UnitFloat
    valid_until: AwareDatetime
    reason_codes: list[ReasonCode] = Field(min_length=1)
    features: Features
    metadata: JsonObject = Field(description="Enough context to reproduce why the signal was generated.")
    schema_version: Literal["1.0"] = "1.0"

    @model_validator(mode="after")
    def _check_times(self) -> Self:
        if self.as_of > self.timestamp:
            raise ValueError("as_of cannot be after timestamp")
        if self.valid_until < self.timestamp:
            raise ValueError("valid_until cannot precede timestamp")
        return self

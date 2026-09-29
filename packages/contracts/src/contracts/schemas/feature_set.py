"""Features produced by the Core Feature Engine.

Agents consume this object. They do not recompute indicators from raw candles.
"""

from pydantic import AwareDatetime

from contracts.enums import Timeframe
from contracts.schemas.common import ContractModel, Features, NonEmptyStr, Symbol


class FeatureSet(ContractModel):
    """Versioned features for one symbol and timeframe."""

    symbol: Symbol
    timestamp: AwareDatetime
    timeframe: Timeframe
    feature_version: NonEmptyStr
    features: Features
    source_data_timestamp: AwareDatetime

"""Time-varying synthetic features for ML training (not scanned as an agent)."""

from __future__ import annotations

from datetime import datetime

from contracts.enums import Timeframe
from contracts.schemas.feature_set import FeatureSet
from contracts.time import require_aware

from quant_agents.testing.core_compatible import CoreCompatibleFeatureProvider


class HistoryFeatureProvider:
    """last_close walks with the UTC date so labels are not constant."""

    def __init__(self) -> None:
        self._core = CoreCompatibleFeatureProvider()

    def get_feature_set(self, symbol: str, timeframe: Timeframe | str, as_of: datetime) -> FeatureSet:
        base = self._core.get_feature_set(symbol, timeframe, as_of)
        aware = require_aware(as_of, "as_of")
        ordinal = aware.date().toordinal()
        close = 100.0 + float((ordinal + len(symbol)) % 23)
        features = dict(base.features)
        features["last_close"] = close
        features["return_1"] = 0.01 if ordinal % 2 == 0 else -0.01
        features["momentum_10"] = features["return_1"]
        parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
        return FeatureSet(
            symbol=base.symbol,
            timestamp=aware,
            timeframe=parsed,
            feature_version=base.feature_version,
            features=features,
            source_data_timestamp=aware,
        )

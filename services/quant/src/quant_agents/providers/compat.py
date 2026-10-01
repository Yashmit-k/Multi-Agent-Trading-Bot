"""Temporary rename of contracts fixture feature names. Warn once per process."""

from __future__ import annotations

import logging
from datetime import datetime

from contracts.enums import Timeframe
from contracts.fakes import FakeFeatureProvider
from contracts.schemas.feature_set import FeatureSet

logger = logging.getLogger(__name__)

_WARNED = False

RENAMES = {"return_1d": "return_1", "volume": "last_volume"}


def reset_compat_warning() -> None:
    global _WARNED
    _WARNED = False


class FixtureCompatibilityFeatureProvider:
    """Maps fixture names onto the engine vocabulary. Remove after the contracts rename PR."""

    def __init__(self, inner: FakeFeatureProvider | None = None) -> None:
        self._inner = inner or FakeFeatureProvider()

    def get_feature_set(self, symbol: str, timeframe: Timeframe | str, as_of: datetime) -> FeatureSet:
        global _WARNED
        if not _WARNED:
            logger.warning(
                "FixtureCompatibilityFeatureProvider is a temporary name bridge; "
                "remove after contracts fixture keys match the Feature Engine"
            )
            _WARNED = True
        raw = self._inner.get_feature_set(symbol, timeframe, as_of)
        features = dict(raw.features)
        for old, new in RENAMES.items():
            if old in features and new not in features:
                features[new] = features[old]
                del features[old]
        return FeatureSet(
            symbol=raw.symbol,
            timestamp=raw.timestamp,
            timeframe=raw.timeframe,
            feature_version=raw.feature_version,
            features=features,
            source_data_timestamp=raw.source_data_timestamp,
        )

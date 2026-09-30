"""Proposed 1.1.0 FeatureSets including index symbols."""

from __future__ import annotations

from datetime import datetime

from contracts.enums import Timeframe
from contracts.schemas.feature_set import FeatureSet
from contracts.time import require_aware

from quant_agents.testing.core_compatible import CoreCompatibleFeatureProvider

FEATURE_VERSION = "1.1.0-proposed"

_EXTENDED = {
    "uptrend": {
        "bollinger_pct_b": 0.85,
        "distance_from_mean": 0.1,
        "zscore_20": 1.8,
        "reversion_half_life": 8.0,
        "relative_volume": 1.4,
        "volume_acceleration": 0.2,
        "volume_imbalance": 0.15,
        "price_volume_corr": 0.6,
        "roc_10": 0.04,
        "trend_strength_adx": 32.0,
        "relative_strength_nifty": 1.1,
        "volume_confirmation": 1.0,
        "support_level": 95.0,
        "resistance_level": 115.0,
        "trend_slope": 0.4,
        "volatility_percentile": 55.0,
        "close_vs_vwap": 1.0,
    },
    "oversold": {
        "bollinger_pct_b": 0.08,
        "distance_from_mean": -0.09,
        "zscore_20": -2.1,
        "reversion_half_life": 5.0,
        "relative_volume": 0.7,
        "volume_acceleration": -0.1,
        "volume_imbalance": -0.2,
        "price_volume_corr": 0.1,
        "roc_10": -0.05,
        "trend_strength_adx": 18.0,
        "relative_strength_nifty": 0.8,
        "volume_confirmation": 0.0,
        "support_level": 88.0,
        "resistance_level": 105.0,
        "trend_slope": -0.3,
        "volatility_percentile": 40.0,
        "close_vs_vwap": -1.0,
    },
    "high_vol": {
        "bollinger_pct_b": 0.5,
        "distance_from_mean": 0.0,
        "zscore_20": 0.1,
        "reversion_half_life": 3.0,
        "relative_volume": 2.5,
        "volume_acceleration": 0.8,
        "volume_imbalance": 0.0,
        "price_volume_corr": 0.0,
        "roc_10": 0.0,
        "trend_strength_adx": 12.0,
        "relative_strength_nifty": 1.0,
        "volume_confirmation": 0.0,
        "support_level": 70.0,
        "resistance_level": 130.0,
        "trend_slope": 0.0,
        "volatility_percentile": 92.0,
        "close_vs_vwap": 0.0,
    },
    "range": {
        "bollinger_pct_b": 0.52,
        "distance_from_mean": 0.005,
        "zscore_20": 0.2,
        "reversion_half_life": 12.0,
        "relative_volume": 1.0,
        "volume_acceleration": 0.0,
        "volume_imbalance": 0.0,
        "price_volume_corr": 0.2,
        "roc_10": 0.002,
        "trend_strength_adx": 14.0,
        "relative_strength_nifty": 1.0,
        "volume_confirmation": 0.0,
        "support_level": 98.0,
        "resistance_level": 102.0,
        "trend_slope": 0.02,
        "volatility_percentile": 25.0,
        "close_vs_vwap": 0.0,
    },
}

_SYMBOL_SCENARIO = {
    "RELIANCE": "uptrend",
    "TCS": "oversold",
    "INFY": "range",
    "HDFCBANK": "high_vol",
    "ICICIBANK": "uptrend",
    "NIFTY50": "uptrend",
    "INDIAVIX": "high_vol",
}


class ExtendedFeatureProvider:
    def __init__(self, *, omit_index: bool = False) -> None:
        self._core = CoreCompatibleFeatureProvider()
        self.omit_index = omit_index

    def get_feature_set(self, symbol: str, timeframe: Timeframe | str, as_of: datetime) -> FeatureSet:
        name = symbol.strip().upper()
        if self.omit_index and name in {"NIFTY50", "INDIAVIX"}:
            raise LookupError(name)
        base = self._core.get_feature_set(symbol, timeframe, as_of)
        scenario = _SYMBOL_SCENARIO.get(name, "range")
        features = dict(base.features)
        features.update(_EXTENDED[scenario])
        parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
        aware = require_aware(as_of, "as_of")
        return FeatureSet(
            symbol=name,
            timestamp=aware,
            timeframe=parsed,
            feature_version=FEATURE_VERSION,
            features=features,
            source_data_timestamp=base.source_data_timestamp,
        )

"""FeatureSets whose keys match the Core Feature Engine 1.0.0 snapshot."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from contracts.enums import Timeframe
from contracts.schemas.feature_set import FeatureSet
from contracts.time import require_aware

_KEYS = json.loads((Path(__file__).with_name("core_engine_keys.json")).read_text(encoding="utf-8"))
FEATURE_VERSION = "1.0.0"

_SCENARIOS = {
    "uptrend": {
        "last_close": 110.0,
        "period_high": 112.0,
        "period_low": 90.0,
        "last_volume": 120000,
        "volume_mean": 100000,
        "sma_10": 108.0,
        "sma_20": 100.0,
        "ema_12": 107.0,
        "ema_26": 101.0,
        "macd": 1.2,
        "macd_signal": 0.4,
        "rsi_14": 62.0,
        "atr_14": 2.0,
        "vwap": 105.0,
        "bollinger_mid": 100.0,
        "bollinger_upper": 108.0,
        "bollinger_lower": 92.0,
        "return_1": 0.01,
        "volatility": 0.012,
        "momentum_10": 8.0,
    },
    "oversold": {
        "last_close": 91.0,
        "period_high": 112.0,
        "period_low": 90.0,
        "last_volume": 80000,
        "volume_mean": 100000,
        "sma_10": 98.0,
        "sma_20": 100.0,
        "ema_12": 96.0,
        "ema_26": 101.0,
        "macd": -0.8,
        "macd_signal": -0.2,
        "rsi_14": 22.0,
        "atr_14": 3.0,
        "vwap": 99.0,
        "bollinger_mid": 100.0,
        "bollinger_upper": 108.0,
        "bollinger_lower": 92.0,
        "return_1": -0.02,
        "volatility": 0.02,
        "momentum_10": -9.0,
    },
    "high_vol": {
        "last_close": 100.0,
        "period_high": 130.0,
        "period_low": 70.0,
        "last_volume": 200000,
        "volume_mean": 100000,
        "sma_10": 100.0,
        "sma_20": 100.0,
        "ema_12": 100.0,
        "ema_26": 100.0,
        "macd": 0.0,
        "macd_signal": 0.0,
        "rsi_14": 50.0,
        "atr_14": 8.0,
        "vwap": 100.0,
        "bollinger_mid": 100.0,
        "bollinger_upper": 120.0,
        "bollinger_lower": 80.0,
        "return_1": 0.0,
        "volatility": 0.08,
        "momentum_10": 0.0,
    },
    "range": {
        "last_close": 100.5,
        "period_high": 102.0,
        "period_low": 98.0,
        "last_volume": 100000,
        "volume_mean": 100000,
        "sma_10": 100.2,
        "sma_20": 100.0,
        "ema_12": 100.1,
        "ema_26": 100.0,
        "macd": 0.05,
        "macd_signal": 0.04,
        "rsi_14": 51.0,
        "atr_14": 0.8,
        "vwap": 100.0,
        "bollinger_mid": 100.0,
        "bollinger_upper": 102.0,
        "bollinger_lower": 98.0,
        "return_1": 0.001,
        "volatility": 0.004,
        "momentum_10": 0.4,
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


class CoreCompatibleFeatureProvider:
    def __init__(self, *, poison_after: datetime | None = None, poison_value: float = 999.0, source_lag_sessions: int = 0) -> None:
        self.poison_after = poison_after
        self.poison_value = poison_value
        self.source_lag_sessions = source_lag_sessions
        self._overrides: dict[tuple[str, str], dict[str, str | int | float | bool]] = {}
        self._source_override: dict[tuple[str, str], datetime] = {}

    def set_source(self, symbol: str, as_of: datetime, source: datetime) -> None:
        self._source_override[(symbol.upper(), as_of.isoformat())] = source

    def set_features(self, symbol: str, as_of: datetime, features: dict[str, str | int | float | bool]) -> None:
        self._overrides[(symbol.upper(), as_of.isoformat())] = features

    def get_feature_set(self, symbol: str, timeframe: Timeframe | str, as_of: datetime) -> FeatureSet:
        parsed = timeframe if isinstance(timeframe, Timeframe) else Timeframe(timeframe)
        aware = require_aware(as_of, "as_of")
        name = symbol.strip().upper()
        key = (name, aware.isoformat())
        if key in self._overrides:
            features = dict(self._overrides[key])
        else:
            scenario = _SYMBOL_SCENARIO.get(name, "range")
            features = dict(_SCENARIOS[scenario])
        if self.poison_after is not None and aware > self.poison_after:
            features["last_close"] = self.poison_value
        source = self._source_override.get((name, aware.isoformat()), aware)
        return FeatureSet(
            symbol=name,
            timestamp=aware,
            timeframe=parsed,
            feature_version=FEATURE_VERSION,
            features=features,
            source_data_timestamp=source,
        )


def engine_key_snapshot() -> list[str]:
    return list(_KEYS)

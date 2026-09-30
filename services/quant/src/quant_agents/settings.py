"""Environment for the quant health service. No broker credentials."""

from __future__ import annotations

import os
from dataclasses import dataclass

from contracts.enums import TradingMode


@dataclass(frozen=True, slots=True)
class QuantSettings:
    data_source: str
    trading_mode: TradingMode
    log_level: str
    artifact_dir: str | None
    horizons_path: str | None

    @classmethod
    def from_env(cls) -> QuantSettings:
        mode_raw = os.environ.get("QUANT_TRADING_MODE", "BACKTEST")
        artifact = os.environ.get("QUANT_ARTIFACT_DIR") or None
        horizons = os.environ.get("QUANT_HORIZONS_PATH") or None
        return cls(
            data_source=os.environ.get("QUANT_DATA_SOURCE", "fixtures"),
            trading_mode=TradingMode(mode_raw),
            log_level=os.environ.get("QUANT_LOG_LEVEL", "INFO"),
            artifact_dir=artifact,
            horizons_path=horizons,
        )

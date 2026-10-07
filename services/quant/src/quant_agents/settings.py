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
    core_api_url: str = ""
    core_api_token: str = ""
    internal_signal_token: str = ""
    symbols: tuple[str, ...] = ()
    eval_interval_seconds: int = 300
    snapshot_path: str = ""
    horizon: str = "SWING"
    timeframe: str = "1d"

    @classmethod
    def from_env(cls) -> QuantSettings:
        mode_raw = os.environ.get("QUANT_TRADING_MODE", "BACKTEST")
        artifact = os.environ.get("QUANT_ARTIFACT_DIR") or None
        horizons = os.environ.get("QUANT_HORIZONS_PATH") or None
        symbols = tuple(
            part.strip().upper()
            for part in os.environ.get("QUANT_SYMBOLS", "").split(",")
            if part.strip()
        )
        return cls(
            data_source=os.environ.get("QUANT_DATA_SOURCE", "fixtures"),
            trading_mode=TradingMode(mode_raw),
            log_level=os.environ.get("QUANT_LOG_LEVEL", "INFO"),
            artifact_dir=artifact,
            horizons_path=horizons,
            core_api_url=os.environ.get("CORE_API_URL", "").rstrip("/"),
            core_api_token=os.environ.get("CORE_API_TOKEN", ""),
            internal_signal_token=os.environ.get("INTERNAL_SIGNAL_TOKEN", ""),
            symbols=symbols,
            eval_interval_seconds=int(os.environ.get("QUANT_EVAL_INTERVAL_SECONDS", "300")),
            snapshot_path=os.environ.get("QUANT_SNAPSHOT_PATH", ""),
            horizon=os.environ.get("QUANT_HORIZON", "SWING"),
            timeframe=os.environ.get("QUANT_TIMEFRAME", "1d"),
        )

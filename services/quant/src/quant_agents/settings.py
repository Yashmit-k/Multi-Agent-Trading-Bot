"""Environment for the quant health service. No broker credentials."""

from __future__ import annotations

import os
from dataclasses import dataclass

from contracts.enums import TradingMode

from quant_agents.errors import ConfigError


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
    ml_demo: bool = False
    ml_demo_dir: str | None = None
    global_markets: bool = True

    @classmethod
    def from_env(cls) -> QuantSettings:
        mode_raw = os.environ.get("QUANT_TRADING_MODE", "BACKTEST")
        artifact = os.environ.get("QUANT_ARTIFACT_DIR") or None
        demo_raw = os.environ.get("QUANT_ML_DEMO", "false").strip().lower()
        if demo_raw in {"1", "true", "yes"}:
            ml_demo = True
        elif demo_raw in {"0", "false", "no", ""}:
            ml_demo = False
        else:
            raise ConfigError("QUANT_ML_DEMO must be true or false")
        horizons = os.environ.get("QUANT_HORIZONS_PATH") or None
        symbols = tuple(
            part.strip().upper()
            for part in os.environ.get("QUANT_SYMBOLS", "").split(",")
            if part.strip()
        )
        settings = cls(
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
            ml_demo=ml_demo,
            ml_demo_dir=os.environ.get("QUANT_ML_DEMO_DIR") or None,
            global_markets=os.environ.get("QUANT_GLOBAL_MARKETS", "true").strip().lower() not in {"0", "false", "no"},
        )
        _reject_bad_ml(settings)
        return settings


def _reject_bad_ml(settings: QuantSettings) -> None:
    if settings.ml_demo and settings.artifact_dir:
        raise ConfigError("QUANT_ML_DEMO and QUANT_ARTIFACT_DIR cannot both be set")
    if settings.ml_demo and settings.trading_mode is not TradingMode.PAPER:
        raise ConfigError("QUANT_ML_DEMO is allowed only when the trading mode is PAPER")
    if settings.ml_demo and not settings.ml_demo_dir:
        raise ConfigError("QUANT_ML_DEMO_DIR is required when QUANT_ML_DEMO is set")
